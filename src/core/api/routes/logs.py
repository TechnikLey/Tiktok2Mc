"""Log viewing and crash report endpoints."""

import asyncio
import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from starlette.responses import StreamingResponse

from core.api.eventbus import event_bus
from core.logger import _get_log_dir

log = logging.getLogger(__name__)

router = APIRouter(tags=["Logs"])


# ---------------------------------------------------------------------------
# SSE log stream
# ---------------------------------------------------------------------------

@router.get("/logs/stream")
async def logs_stream():
    """Server-Sent Events stream of unified log entries.

    Each event has ``type: log.unified`` and ``data`` containing:
    ``level``, ``name``, ``message``, ``raw``, ``timestamp``.
    """

    async def generate():
        q = event_bus.subscribe("log.unified")
        try:
            yield ": connected\n\n"
            while True:
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=30)
                    yield f"data: {json.dumps(msg)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                except (ConnectionResetError, ConnectionAbortedError, OSError) as exc:
                    log.debug("SSE log client disconnected abruptly: %s", exc)
                    break
        except asyncio.CancelledError:
            pass
        except (ConnectionResetError, ConnectionAbortedError, OSError) as exc:
            log.debug("SSE log transport closed: %s", exc)
        finally:
            event_bus.unsubscribe(q)

    return StreamingResponse(generate(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Crash reports
# ---------------------------------------------------------------------------

@router.get("/logs/crash-reports")
async def list_crash_reports():
    """List all crash report files with metadata."""
    crash_dir = _get_log_dir() / "crash_reports"
    if not crash_dir.exists():
        return {"reports": []}

    reports = []
    for path in sorted(crash_dir.glob("crash_*.json"), reverse=True):
        try:
            stat = path.stat()
            # Peek at the first few lines to get lightweight metadata
            # without parsing the whole file.
            data = json.loads(path.read_text(encoding="utf-8"))
            reports.append(
                {
                    "filename": path.name,
                    "timestamp": data.get("timestamp"),
                    "module": data.get("module"),
                    "exception_type": data.get("exception_type"),
                    "size": stat.st_size,
                }
            )
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            continue

    return {"reports": reports}


@router.get("/logs/crash-reports/{filename}")
async def get_crash_report(filename: str):
    """Return a single crash report as JSON."""
    # Sanitise filename to prevent directory traversal
    safe_name = Path(filename).name
    if not safe_name.startswith("crash_") or not safe_name.endswith(".json"):
        raise HTTPException(status_code=400, detail="Invalid filename")

    path = _get_log_dir() / "crash_reports" / safe_name
    if not path.exists():
        raise HTTPException(status_code=404, detail="Crash report not found")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
        log.warning("Failed to read crash report %s: %s", safe_name, exc)
        raise HTTPException(status_code=500, detail="Failed to read crash report")
