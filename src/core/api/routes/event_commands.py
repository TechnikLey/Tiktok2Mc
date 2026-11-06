"""REST endpoints for the event-command mapping in ``data/event_commands.yaml``."""

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException

import core.paths
from core.api.models import EventCommandsResponse, EventCommandsUpdateRequest
from core.yaml_utils import load_yaml, save_yaml

log = logging.getLogger(__name__)

router = APIRouter(tags=["Event Commands"])

DEFAULT_CONFIG_PATH = Path("defaults/event_commands.yaml")
DATA_CONFIG_PATH = Path("data/event_commands.yaml")


def _config_path() -> Path:
    """Resolve the event-command file, preferring the user copy.

Returns:
    ``data/event_commands.yaml`` when it exists, otherwise the default
    file, otherwise the (not yet created) data path."""

    root = core.paths.get_root_dir()
    data_path = root / DATA_CONFIG_PATH
    if data_path.exists():
        return data_path
    default_path = root / DEFAULT_CONFIG_PATH
    if default_path.exists():
        return default_path
    return data_path


def _ensure_data_config() -> Path:
    """Return the data config path, copying from defaults if missing."""
    root = core.paths.get_root_dir()
    data_path = root / DATA_CONFIG_PATH
    if not data_path.exists():
        data_path.parent.mkdir(parents=True, exist_ok=True)
        default_path = root / DEFAULT_CONFIG_PATH
        if default_path.exists():
            save_yaml(data_path, load_yaml(default_path))
        else:
            save_yaml(data_path, {"event_commands": {}})
    return data_path


@router.get("/event-commands", response_model=EventCommandsResponse)
async def get_event_commands():
    """Return the event-command mapping and the file it came from.

When no file exists, an empty mapping is returned without creating
anything. Any unexpected error is reported as HTTP 500."""

    try:
        path = _config_path()
        if not path.exists():
            return EventCommandsResponse(path=str(path), event_commands={})
        cfg = load_yaml(path)
        return EventCommandsResponse(
            path=str(path),
            event_commands=cfg.get("event_commands", {}),
        )
    except Exception as e:  # any unexpected error becomes an HTTP 500
        log.error("Failed to load event_commands: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/event-commands", response_model=EventCommandsResponse)
async def update_event_commands(body: EventCommandsUpdateRequest):
    """Persist a new event-command mapping to the data directory.

The file is created from the defaults on first write and the previous
version is backed up. Returns the written mapping and its path; unexpected
errors are reported as HTTP 500."""

    try:
        path = _ensure_data_config()
        save_yaml(path, {"event_commands": body.event_commands}, backup=True)
        log.info("event_commands updated: %s", path)
        return EventCommandsResponse(
            path=str(path),
            event_commands=body.event_commands,
        )
    except Exception as e:  # any unexpected error becomes an HTTP 500
        log.error("Failed to write event_commands: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
