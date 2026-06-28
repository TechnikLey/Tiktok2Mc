import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException
from starlette.responses import HTMLResponse, StreamingResponse

from core.api.eventbus import event_bus
from core.overlay import get_overlay_manager

log = logging.getLogger(__name__)

router = APIRouter(tags=["Overlay"])


@router.get("/overlay")
async def serve_overlay(overlay: str = "default", chroma: bool = False):
    """Serve the rendered overlay HTML for the built-in overlay subsystem.

    Intended for use as an OBS Browser Source or pywebview URL.
    """
    mgr = get_overlay_manager()
    html = mgr.render_html(overlay_name=overlay, chroma=chroma)
    return HTMLResponse(html)


@router.get("/overlay/stream")
async def overlay_event_stream():
    """SSE endpoint for the built-in overlay state stream.

    Clients (OBS browser sources, pywebview) connect here and receive
    real-time state updates.  On connection the client receives the
    latest cached state if one exists.
    """
    mgr = get_overlay_manager()

    async def generate():
        q = event_bus.subscribe("overlay.state_update")
        try:
            # Stream real-time updates
            while True:
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=30)
                    yield f"data: {json.dumps(msg['data'])}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                except (ConnectionResetError, ConnectionAbortedError, OSError) as exc:
                    log.debug("Overlay SSE client disconnected abruptly: %s", exc)
                    break
        except asyncio.CancelledError:
            pass
        except (ConnectionResetError, ConnectionAbortedError, OSError) as exc:
            log.debug("Overlay SSE transport closed: %s", exc)
        finally:
            event_bus.unsubscribe(q)

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/overlay/preview")
async def overlay_preview(body: dict):
    """Render a preview of the overlay HTML with optional theme overrides.

    Used by the GUI live theme editor to show real-time preview without
    saving configuration changes.
    """
    mgr = get_overlay_manager()
    overlay_name = body.get("overlay_name", "default")
    chroma = body.get("chroma", True)
    theme_overrides = body.get("theme", None)
    html = mgr.render_html(overlay_name=overlay_name, chroma=chroma, theme_overrides=theme_overrides)
    return {"html": html}


@router.post("/overlay/display")
async def overlay_display(body: dict):
    """Display text on a built-in overlay.

    This is the direct endpoint used by ``core.overlay_utils`` and the
    actions.mca pipeline.  It bypasses the old plugin command-queue
    indirection and updates the event bus immediately.
    """
    title = body.get("title", "")
    subtitle = body.get("subtitle", "")
    duration = body.get("duration", 3)
    overlay_name = body.get("overlay_name", "default")

    mgr = get_overlay_manager()
    success = mgr.dispatch(title, subtitle, duration, overlay_name)
    if not success:
        # Distinguish between "not found" and "cooldown"
        if overlay_name not in mgr.clients:
            raise HTTPException(status_code=404, detail=f"Overlay '{overlay_name}' not found")
        raise HTTPException(status_code=429, detail=f"Overlay '{overlay_name}' is in cooldown")

    return {"status": "ok", "overlay": overlay_name}
