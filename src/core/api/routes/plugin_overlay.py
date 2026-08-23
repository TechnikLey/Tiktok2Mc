import asyncio
import html
import json
import logging
import time
import uuid

from fastapi import APIRouter, HTTPException
from starlette.responses import HTMLResponse, StreamingResponse

from core.api.eventbus import event_bus
from core.api.plugin_overlay import (
    command_queue,
    dashboard_html_store,
    overlay_html_store,
    query_store,
    state_store,
)
from core.error_codes import PLUGIN_0018, PLUGIN_0019

log = logging.getLogger(__name__)

router = APIRouter(tags=["Plugin Overlay"])

# TTL cache for declared accepted_commands (delivery validation).
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


@router.post("/plugins/{name}/dashboard-html")
async def register_dashboard_html(name: str, body: dict):
    """Register the dashboard page HTML for a plugin.

    Called by the plugin process on startup when its manifest declares
    ``dashboard_ui: true``.  The Main API serves the page at
    ``GET /plugins/{name}/dashboard`` and the GUI embeds it as a tab.
    """
    html = body.get("html")
    if not html:
        raise HTTPException(status_code=422, detail="Missing 'html' field")
    dashboard_html_store.set_html(name, html)
    log.info("Dashboard HTML registered for plugin '%s' (%d bytes)", name, len(html))
    return {"status": "ok"}


@router.get("/plugins/{name}/dashboard")
async def serve_dashboard(name: str):
    """Serve the dashboard page HTML for a plugin.

    Embedded as an iframe tab in the web dashboard; same origin as the
    API, so the page can use relative ``/api/v1/...`` calls (state SSE,
    commands, store).
    """
    html = dashboard_html_store.get_html(name)
    if html is None:
        raise HTTPException(
            status_code=404,
            detail=f"No dashboard registered for plugin '{name}' — is the plugin running?",
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
    if declared and cmd not in declared and cmd != "__query__":
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


# ─── Queries (request/response with correlation ids) ─────────────────────

_QUERY_TIMEOUT_MIN = 0.5
_QUERY_TIMEOUT_MAX = 30.0


def _queries_declared_for(name: str) -> set[str] | None:
    """Return the plugin's declared ``queries`` names, or None when unknown.

    Same best-effort contract as ``_accepted_commands_for``: ``None``
    means no declaration available and validation is skipped.
    """
    try:
        from core.plugin_config import discover_plugins_dir, load_plugin_manifest

        plugin_dir = discover_plugins_dir() / name
        manifest = load_plugin_manifest(plugin_dir) if plugin_dir.is_dir() else None
        raw = (manifest or {}).get("queries")
        result: set[str] | None = (
            {str(q) for q in raw} if isinstance(raw, list) and raw else None
        )
    except Exception as exc:
        log.debug("queries lookup failed for '%s': %s", name, exc)
        return None
    return result


@router.post("/plugins/{name}/query")
async def query_plugin(name: str, body: dict):
    """Send a query to a plugin and wait for its response.

    Request/response channel for extensions: the query is
    delivered to the plugin through its command queue as the reserved
    command ``__query__`` with a correlation id; BasePlugin routes it to
    ``on_query()`` and POSTs the answer back, which resolves this HTTP
    request. Requires the plugin process to be running.
    """
    query = body.get("query")
    if not query or not isinstance(query, str):
        raise HTTPException(status_code=422, detail="Missing 'query' field")
    args = body.get("args") or {}
    if not isinstance(args, dict):
        raise HTTPException(status_code=422, detail="'args' must be an object")

    from core.api.registry import get_registry

    if get_registry().get(name) is None:
        raise HTTPException(status_code=404, detail=f"Plugin '{name}' not found")

    declared = _queries_declared_for(name)
    if declared is not None and query not in declared:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Plugin '{name}' does not declare query '{query}' "
                f"(declared: {', '.join(sorted(declared))})"
            ),
        )

    try:
        timeout = min(
            _QUERY_TIMEOUT_MAX,
            max(_QUERY_TIMEOUT_MIN, float(body.get("timeout", 5))),
        )
    except (TypeError, ValueError):
        timeout = 5.0

    query_id = str(uuid.uuid4())
    future: asyncio.Future = asyncio.get_running_loop().create_future()
    query_store.register(query_id, name, future)
    command_queue.enqueue(name, "__query__", _query_id=query_id, _query=query, **args)

    log.info("[QUERY] '%s' sent to plugin '%s' (id=%s)", query, name, query_id)
    try:
        outcome = await asyncio.wait_for(future, timeout=timeout)
    except asyncio.TimeoutError:
        log.warning(
            "[QUERY] %s timed out waiting for '%s' from plugin '%s'",
            PLUGIN_0018.code,
            query,
            name,
        )
        raise HTTPException(
            status_code=504,
            detail=f"{PLUGIN_0018.code} {PLUGIN_0018.message}",
        )
    finally:
        query_store.abandon(query_id)

    if not outcome.get("ok", False):
        error = outcome.get("error", "unknown error")
        log.warning(
            "[QUERY] %s handler failed for '%s' on plugin '%s': %s",
            PLUGIN_0019.code,
            query,
            name,
            error,
        )
        raise HTTPException(
            status_code=502,
            detail=f"{PLUGIN_0019.code} {PLUGIN_0019.message}: {error}",
        )
    return {"id": query_id, "result": outcome.get("result")}


@router.post("/plugins/{name}/rpc")
async def plugin_rpc(name: str, body: dict):
    """Generic custom endpoint for a plugin (request/response).

    Gives every extension its own REST-style surface without server
    changes: the call is delivered to the running plugin process as the
    reserved command ``__rpc__`` (correlation id via the query store);
    BasePlugin routes it to ``on_rpc(method, path, body)`` and POSTs the
    answer back through the same response channel as queries. Use it for
    interactions that do not fit the ``commands``/``queries`` schema —
    e.g. REST resources, webhooks into a plugin, or rich dashboard
    callbacks.
    """
    method = str(body.get("method", "GET")).upper()
    if method not in ("GET", "POST", "PUT", "DELETE", "PATCH"):
        raise HTTPException(status_code=422, detail=f"Invalid 'method': {method}")
    path = body.get("path")
    if not isinstance(path, str) or not path.startswith("/") or len(path) > 512:
        raise HTTPException(
            status_code=422,
            detail="'path' must be a string starting with '/' (max 512 chars)",
        )
    rpc_body = body.get("body")
    if rpc_body is not None and not isinstance(rpc_body, dict):
        raise HTTPException(status_code=422, detail="'body' must be an object")

    from core.api.registry import get_registry

    if get_registry().get(name) is None:
        raise HTTPException(status_code=404, detail=f"Plugin '{name}' not found")

    try:
        timeout = min(
            _QUERY_TIMEOUT_MAX,
            max(_QUERY_TIMEOUT_MIN, float(body.get("timeout", 5))),
        )
    except (TypeError, ValueError):
        timeout = 5.0

    rpc_id = str(uuid.uuid4())
    future: asyncio.Future = asyncio.get_running_loop().create_future()
    query_store.register(rpc_id, name, future)
    command_queue.enqueue(
        name,
        "__rpc__",
        _rpc_id=rpc_id,
        _rpc_method=method,
        _rpc_path=path,
        _rpc_body=rpc_body or {},
    )

    log.info("[RPC] %s %s sent to plugin '%s' (id=%s)", method, path, name, rpc_id)
    try:
        outcome = await asyncio.wait_for(future, timeout=timeout)
    except asyncio.TimeoutError:
        log.warning(
            "[RPC] %s timed out waiting for %s %s on plugin '%s'",
            PLUGIN_0018.code,
            method,
            path,
            name,
        )
        raise HTTPException(
            status_code=504,
            detail=f"{PLUGIN_0018.code} {PLUGIN_0018.message}",
        )
    finally:
        query_store.abandon(rpc_id)

    if not outcome.get("ok", False):
        error = outcome.get("error", "unknown error")
        log.warning(
            "[RPC] %s handler failed for %s %s on plugin '%s': %s",
            PLUGIN_0019.code,
            method,
            path,
            name,
            error,
        )
        raise HTTPException(
            status_code=502,
            detail=f"{PLUGIN_0019.code} {PLUGIN_0019.message}: {error}",
        )
    return {"id": rpc_id, "result": outcome.get("result")}


@router.post("/plugins/{name}/query-response")
async def query_plugin_response(name: str, body: dict):
    """Deliver a plugin's answer for a pending query.

    Called by the plugin process after ``on_query()`` returns. Unknown or
    already-timed-out correlation ids are accepted silently so late
    responses don't error in the plugin's polling thread.
    """
    query_id = body.get("id")
    if not isinstance(query_id, str):
        raise HTTPException(status_code=422, detail="Missing 'id' field")
    resolved = (
        query_store.resolve(query_id, body.get("result"))
        if body.get("ok", True)
        else query_store.fail(query_id, str(body.get("error", "unknown")))
    )
    return {"status": "ok", "resolved": resolved}


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
