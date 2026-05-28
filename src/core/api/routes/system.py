"""System control endpoints (restart, shutdown signals)."""

import logging
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException

from core.paths import get_root_dir

log = logging.getLogger(__name__)

router = APIRouter(tags=["System"])


@router.post("/restart")
async def restart_system():
    """Write a restart signal that start.py picks up via file watcher."""
    try:
        runtime_dir = get_root_dir() / "core" / "runtime"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        signal_file = runtime_dir / "restart"
        signal_file.write_text("", encoding="utf-8")
        log.info("Restart signal written to %s", signal_file)
        return {"status": "restart_requested"}
    except Exception as e:
        log.exception("Failed to write restart signal")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/shutdown")
async def shutdown_system():
    """Write a shutdown signal that start.py picks up via file watcher."""
    try:
        runtime_dir = get_root_dir() / "core" / "runtime"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        signal_file = runtime_dir / "shutdown"
        signal_file.write_text("", encoding="utf-8")
        log.info("Shutdown signal written to %s", signal_file)
        return {"status": "shutdown_requested"}
    except Exception as e:
        log.exception("Failed to write shutdown signal")
        raise HTTPException(status_code=500, detail=str(e))
