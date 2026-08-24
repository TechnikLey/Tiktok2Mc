import asyncio
import json
import logging
import re

from fastapi import APIRouter, Header, HTTPException, Query
from starlette.responses import StreamingResponse

from core.api.eventbus import event_bus
from core.api.services.reaction_catalog import validate_event_payload
from core.error_codes import API_0009, API_0010

log = logging.getLogger(__name__)

router = APIRouter(tags=["Events"])

# Core event families can only be published by the bridge process. The
# bridge marks its posts with ``X-T2M-Source: bridge``; every other caller
# (plugins, hooks via raw HTTP, external tools) must use its own namespace.
RESERVED_EVENT_PREFIXES = ("tiktok.", "minecraft.")
BRIDGE_SOURCE_HEADER = "X-T2M-Source"
BRIDGE_SOURCE_VALUE = "bridge"

# Event types must be namespaced: "<source>.<name>" with at least one dot.
_EVENT_TYPE_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}(\.[A-Za-z0-9_.-]{1,128})$")


def _is_trusted_bridge(source_header: str | None) -> bool:
    return source_header == BRIDGE_SOURCE_VALUE


def _check_reserved_type(event_type: str, source_header: str | None) -> None:
    """Reject writes to reserved core event families from untrusted callers."""
    if event_type.startswith(RESERVED_EVENT_PREFIXES) and not _is_trusted_bridge(
        source_header
    ):
        log.warning(
            "%s: rejected publish of reserved event type '%s' "
            "(missing/invalid %s header)",
            API_0009.code,
            event_type,
            BRIDGE_SOURCE_HEADER,
        )
        raise HTTPException(
            status_code=403,
            detail=(
                f"Event family '{event_type.rsplit('.', 1)[0]}.*' is reserved; "
                f"publish under your own namespace instead."
            ),
        )


def _validate_payload(event_type: str, data: dict) -> None:
    """Reject payloads violating the declaring plugin's data_schema."""
    violations = validate_event_payload(event_type, data)
    if violations:
        log.warning(
            "%s: payload for '%s' rejected: %s",
            API_0010.code,
            event_type,
            "; ".join(violations),
        )
        raise HTTPException(
            status_code=422,
            detail=(f"{API_0010.code} {API_0010.message}: " + "; ".join(violations)),
        )


def _validate_event_type(event_type: str) -> None:
    if not _EVENT_TYPE_RE.match(event_type):
        raise HTTPException(
            status_code=422,
            detail=(
                "'type' must be namespaced like '<source>.<event>' "
                "(letters, digits, '_', '-', '.')"
            ),
        )


@router.get("/events/stream")
async def event_stream(
    types: str = Query(
        "",
        description="Comma-separated event types to subscribe to (empty = all events)",
    ),
):
    """Server-Sent Events (SSE) endpoint.

    Clients connect via ``EventSource`` and receive a stream of
    real-time events.  Optional ``?types=log,status`` filtering
    lets consumers subscribe to only the events they need.
    """

    filter_types = [t.strip() for t in types.split(",") if t.strip()] if types else []

    async def generate():
        q = event_bus.subscribe(*filter_types)
        try:
            # Signal that the connection is established
            yield ": connected\n\n"
            while True:
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=30)
                    yield f"data: {json.dumps(msg)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                except (ConnectionResetError, ConnectionAbortedError, OSError) as exc:
                    log.debug("SSE client disconnected abruptly: %s", exc)
                    break
        except asyncio.CancelledError:
            pass
        except (ConnectionResetError, ConnectionAbortedError, OSError) as exc:
            log.warning("SSE generator failed: %s", exc)
        finally:
            event_bus.unsubscribe(q)

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/events")
async def inject_event(
    body: dict,
    x_t2m_source: str | None = Header(default=None, alias=BRIDGE_SOURCE_HEADER),
):
    """Inject an event into the bus from any component.

    Expected format::

        {"type": "custom.event", "data": {"key": "value"}}

    Reserved core event families (``tiktok.*``, ``minecraft.*``) are only
    accepted from the trusted bridge (``X-T2M-Source: bridge``); all other
    publishers must use their own namespace.
    """
    try:
        event_type = body.get("type", "external.event")
        data = body.get("data", {})
        if not isinstance(event_type, str):
            raise HTTPException(status_code=422, detail="'type' must be a string")
        if not isinstance(data, dict):
            raise HTTPException(status_code=422, detail="'data' must be a dict")
        _check_reserved_type(event_type, x_t2m_source)
        _validate_payload(event_type, data)
        await event_bus.publish(event_type, data)
        return {"status": "ok", "event": event_type}
    except HTTPException:
        raise
    except Exception as e:  # any unexpected error becomes an HTTP 500
        log.exception("Failed to inject event")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/events/ingest")
async def ingest_event(
    body: dict,
    x_t2m_source: str | None = Header(default=None, alias=BRIDGE_SOURCE_HEADER),
):
    """Generic structured inbound for extensions and external systems.

    Publishes a namespaced event onto the EventBus (reaching plugins via
    ``event_subscriptions``, hooks via ``register_event`` and the GUI live
    feed) and optionally dispatches an actions.mca trigger chain with the
    same payload in one call:

    ```
    {
      "type": "mygame.player_death",
      "data": {"player": "Notch", "level": 42},
      "trigger": "on_death",
      "user": "Notch"
    }
    ```

    Only ``type`` is required. ``data`` must be a dict (default ``{}``).
    When ``trigger`` is set, the trigger runs through the TriggerService
    programmatic path (no debounce, recorded in trigger history); the
    known keys ``user`` / ``gift_id`` / ``gift_name`` are taken from the
    body or data when present.
    """
    try:
        event_type = body.get("type")
        if not isinstance(event_type, str) or not event_type.strip():
            raise HTTPException(status_code=422, detail="'type' is required")
        event_type = event_type.strip()
        _validate_event_type(event_type)
        _check_reserved_type(event_type, x_t2m_source)

        data = body.get("data", {})
        if not isinstance(data, dict):
            raise HTTPException(status_code=422, detail="'data' must be a dict")
        _validate_payload(event_type, data)

        await event_bus.publish(event_type, data)

        result: dict = {"status": "ok", "event": event_type}
        trigger_name = body.get("trigger")
        if isinstance(trigger_name, str) and trigger_name.strip():
            user = body.get("user") or data.get("user") or "external"
            gift_id = body.get("gift_id") or data.get("gift_id")
            gift_name = body.get("gift_name") or data.get("gift_name")
            # Imported lazily: the trigger service spins up the shared
            # engine; events routes stay usable without it in tests.
            from core.api.services.trigger_service import get_trigger_service

            dispatch_result = await asyncio.to_thread(
                get_trigger_service().dispatch,
                trigger=trigger_name.strip(),
                user=str(user),
                gift_id=str(gift_id) if gift_id is not None else None,
                gift_name=str(gift_name) if gift_name is not None else None,
            )
            result["trigger"] = dispatch_result
        return result
    except HTTPException:
        raise
    except Exception as e:  # any unexpected error becomes an HTTP 500
        log.exception("Failed to ingest event")
        raise HTTPException(status_code=500, detail=str(e))
