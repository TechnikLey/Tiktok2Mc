"""REST endpoints for the comment-command mapping in ``data/comment_commands.yaml``."""

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException

import core.paths
from core.api.models import CommentCommandsResponse, CommentCommandsUpdateRequest
from core.yaml_utils import load_yaml, save_yaml

log = logging.getLogger(__name__)

router = APIRouter(tags=["Comment Commands"])

DEFAULT_CONFIG_PATH = Path("defaults/comment_commands.yaml")
DATA_CONFIG_PATH = Path("data/comment_commands.yaml")


def _config_path() -> Path:
    """Resolve the comment-command file, preferring the user copy.

Returns:
    ``data/comment_commands.yaml`` when it exists, otherwise the default
    file, otherwise the (not yet created) data path."""

    root = core.paths.get_root_dir()
    data_path = root / DATA_CONFIG_PATH
    if data_path.exists():
        return data_path
    default_path = root / DEFAULT_CONFIG_PATH
    if default_path.exists():
        return default_path
    return data_path  # will be created empty


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
            save_yaml(
                data_path,
                {
                    "comment_commands": {
                        "enabled": False,
                        "cooldown": 0,
                        "user_cooldown": 0,
                        "groups": [],
                    }
                },
            )
    return data_path


@router.get("/comment-commands", response_model=CommentCommandsResponse)
async def get_comment_commands():
    """Return the comment-command mapping and the file it came from.

When no file exists, an empty disabled mapping is returned without
creating anything. Any unexpected error is reported as HTTP 500."""

    try:
        path = _config_path()
        if not path.exists():
            return CommentCommandsResponse(
                path=str(path),
                comment_commands={"enabled": False, "groups": []},
            )
        cfg = load_yaml(path)
        raw = cfg.get("comment_commands", {})
        return CommentCommandsResponse(
            path=str(path),
            comment_commands=raw,
        )
    except Exception as e:  # any unexpected error becomes an HTTP 500
        log.error("Failed to load comment_commands: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/comment-commands", response_model=CommentCommandsResponse)
async def update_comment_commands(body: CommentCommandsUpdateRequest):
    """Persist a new comment-command mapping to the data directory.

The file is created from the defaults on first write and the previous
version is backed up. Returns the written mapping and its path; unexpected
errors are reported as HTTP 500."""

    try:
        path = _ensure_data_config()
        save_yaml(
            path,
            {"comment_commands": body.comment_commands},
            backup=True,
        )
        log.info("comment_commands updated: %s", path)
        return CommentCommandsResponse(
            path=str(path),
            comment_commands=body.comment_commands,
        )
    except Exception as e:  # any unexpected error becomes an HTTP 500
        log.error("Failed to write comment_commands: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
