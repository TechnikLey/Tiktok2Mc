import asyncio
import html
import json
import logging
import time

from fastapi import APIRouter, HTTPException
from starlette.responses import HTMLResponse, StreamingResponse

from core.api.eventbus import event_bus
from core.api.plugin_overlay import (
    command_queue,
    overlay_html_store,
    state_store,
)

log = logging.getLogger(__name__)

router = APIRouter(tags=["Plugin Overlay"])

# TTL cache for declared accepted_commands (J.3 #12 delivery validation).
# Manifest scans are only needed to produce warnings; the cache keeps the
# command route cheap even under frequent reaction triggers.
_ACCEPTED_COMMANDS_TTL = 30.0
_accepted_commands_cache: dict[str, tuple[float, set[str] | None]] = {}


def _accepted_commands_for(name: str) -> set[str] | None:
    """Return the plugin's declared command names, or None when unknown.

    ``None`` means "no declaration available" (missing manifest or scan
    error) — validation is skipped in that case so nothing breaks for
    plugins without an ``accepted_commands`` section.
    """
    now = time.monotonic()
    cached = _accepted_commands_cache.get(name)
    if cached and now - cached[0] < _ACCEPTED_COMMANDS_TTL:
        return cached[1]
    try:
        from core.plugin_config import discover_plugins_dir, load_plugin_manifest

        plugin_dir = discover_plugins_dir() / name
        manifest = load_plugin_manifest(plugin_dir) if plugin_dir.is_dir() else None
        raw = (manifest or {}).get("accepted_commands")
        result: set[str] | None = (
            set(raw.keys()) if isinstance(raw, dict) and raw else None
        )
    except Exception as exc:  # validation is best-effort, never blocking
        log.debug("accepted_commands lookup failed for '%s': %s", name, exc)
        result = None
    _accepted_commands_cache[name] = (now, result)
    return result


def invalidate_accepted_commands_cache(name: str | None = None) -> None:
    """Drop cached declarations (call after plugin installs/updates)."""
    if name is None:
        _accepted_commands_cache.clear()
    else:
        _accepted_commands_cache.pop(name, None)


@router.post("/plugins/{name}/overlay-html")
async def register_overlay_html(name: str, body: dict):
    """Register the rendered overlay HTML for a plugin.

    Called by the plugin process on startup so the Main API
    can serve the overlay at ``GET /plugins/{name}/overlay``.
    """
    html = body.get("html")
    if not html:
        raise HTTPException(status_code=422, detail="Missing 'html' field")
    overlay_html_store.set_html(name, html)
    log.info("Overlay HTML registered for plugin '%s' (%d bytes)", name, len(html))
    return {"status": "ok"}


@router.get("/plugins/{name}/overlay")
async def serve_overlay(name: str):
    """Serve the overlay HTML for a plugin.

    Intended for use as an OBS Browser Source or pywebview URL.
    """
    html = overlay_html_store.get_html(name)
    if html is None:
        raise HTTPException(
            status_code=404,
            detail=f"No overlay registered for plugin '{name}' — is the plugin running?",
        )
    return HTMLResponse(html)


@router.get("/plugins/{name}/stream")
async def plugin_event_stream(name: str):
    """SSE endpoint for a single plugin's state stream.

    Clients (OBS browser sources, pywebview) connect here
    and receive real-time state updates pushed by the plugin.
    On connection the client receives the latest cached state.
    """

    async def generate():
        q = event_bus.subscribe(f"plugin.{name}.state_update")
        try:
            # Send latest cached state immediately
            cached = state_store.get_state(name)
            if cached is not None:
                yield f"data: {json.dumps(cached)}\n\n"
            # Stream real-time updates
            while True:
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=30)
                    yield f"data: {json.dumps(msg['data'])}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                except (ConnectionResetError, ConnectionAbortedError, OSError) as exc:
                    log.debug("Plugin SSE client disconnected abruptly: %s", exc)
                    break
        except asyncio.CancelledError:
            pass
        except (ConnectionResetError, ConnectionAbortedError, OSError) as exc:
            log.debug("Plugin SSE transport closed: %s", exc)
        finally:
            event_bus.unsubscribe(q)

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/plugins/{name}/command")
async def enqueue_command(name: str, body: dict):
    """Enqueue a command for a plugin.

    Other components (main.py, event hooks, other plugins) call
    this to send a command to a plugin.  The plugin picks it up
    via ``GET /plugins/{name}/commands``.
    """
    cmd = body.get("command")
    if not cmd:
        raise HTTPException(status_code=422, detail="Missing 'command' field")
    declared = _accepted_commands_for(name)
    if declared and cmd not in declared:
        log.warning(
            "[CMD-QUEUE] Command '%s' not in accepted_commands of plugin '%s' "
            "(declared: %s) — delivering anyway",
            cmd,
            name,
            ", ".join(sorted(declared)),
        )
    cmd_id = command_queue.enqueue(name, cmd, **body.get("args", {}))
    log.info("Command '%s' enqueued for plugin '%s' (id=%s)", cmd, name, cmd_id)
    return {"status": "ok", "command_id": cmd_id}


@router.get("/plugins/{name}/commands")
async def poll_commands(name: str, wait: int = 0):
    """Poll (or long-poll) and clear pending commands for a plugin.

    Called periodically by the plugin process to receive
    commands from other components.

    * ``wait=0`` (default): returns immediately, same as before.
    * ``wait=1``: blocks up to 30 s until at least one command is
      available, then returns all pending commands.  Zero latency,
      no CPU wasted on polling.

    Also records a heartbeat timestamp so the health monitor can
    track liveness.
    """
    if wait:
        try:
            await command_queue.wait_for_commands(name, timeout=30.0)
        except asyncio.TimeoutError:
            pass
    cmds = command_queue.dequeue_all(name)
    # Record heartbeat for health monitoring
    try:
        from core.api.registry import get_registry

        get_registry().update(name, last_heartbeat=time.time())
    except Exception:  # heartbeat reporting is best-effort
        pass
    return {"commands": cmds}


@router.get("/plugins/{name}/state")
async def get_plugin_state(name: str):
    """Return the latest cached state for a plugin."""
    state = state_store.get_state(name)
    if state is None:
        return {"state": None}
    return {"state": state}


@router.post("/plugins/{name}/state")
async def update_plugin_state(name: str, body: dict):
    """Post a state update for a plugin.

    Called by the plugin process whenever its state changes.
    The state is cached for late-joining SSE clients and also
    published to the EventBus for real-time SSE streaming.
    Also records a heartbeat for health monitoring.
    """
    state = body.get("state", {})
    state_store.set_state(name, state)
    # Record heartbeat for health monitoring
    try:
        from core.api.registry import get_registry

        get_registry().update(name, last_heartbeat=__import__("time").time())
    except Exception:  # heartbeat reporting is best-effort
        pass
    await event_bus.publish(f"plugin.{name}.state_update", state)
    return {"status": "ok"}


OAUTH_SUCCESS_HTML = """<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><title>Authorization Complete</title></head>
<body style="font-family:sans-serif;display:flex;justify-content:center;align-items:center;height:100vh;background:#111;color:#fff;">
<div style="text-align:center;">
<h1>Authorization Complete</h1>
<p>You have successfully authenticated. You can close this window.</p>
</div>
</body>
</html>"""


@router.get("/plugins/oauth/callback")
async def oauth_callback(name: str, code: str = "", state: str = "", error: str = ""):
    """Generic OAuth callback handler for plugins.

    Plugins that need OAuth (e.g. spotify-control) configure
    their redirect URI to point here.  The auth code is forwarded
    to the plugin as a command.
    """
    if error:
        return HTMLResponse(
            f"<h1>Authorization failed</h1><p>{html.escape(error)}</p>",
            status_code=400,
        )
    if not code:
        return HTMLResponse("<h1>Missing authorization code</h1>", status_code=400)
    command_queue.enqueue(name, "oauth_callback", code=code, state=state)
    log.info("OAuth callback forwarded to plugin '%s'", name)
    return HTMLResponse(OAUTH_SUCCESS_HTML)
