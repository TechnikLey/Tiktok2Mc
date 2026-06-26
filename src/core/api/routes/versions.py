import logging
import urllib.request
import json
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.api.services import ApiService
from core.paths import get_root_dir

log = logging.getLogger(__name__)

router = APIRouter(tags=["Versions"])

PAPER_API = "https://api.papermc.io/v2/projects/paper"

SAFE_VERSIONS = {"1.21.11"}

_service: ApiService | None = None


def _get_service() -> ApiService:
    global _service
    if _service is None:
        _service = ApiService()
    return _service


def _fetch_json(url: str, timeout: int = 15) -> dict | list:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "TikTok2Mc/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        log.warning("Failed to fetch %s: %s", url, e)
        raise HTTPException(status_code=502, detail=f"Failed to fetch PaperMC versions: {e}")


class VersionInfo(BaseModel):
    version: str
    safe: bool
    build: int | None = None
    download_url: str | None = None


class VersionsResponse(BaseModel):
    versions: list[VersionInfo]
    current_version: str
    safe_versions: list[str]


class SetVersionRequest(BaseModel):
    version: str


class SetVersionResponse(BaseModel):
    status: str
    version: str
    safe: bool
    message: str


@router.get("/versions", response_model=VersionsResponse)
async def list_versions():
    svc = _get_service()
    cfg = svc.read_config()
    current_version = cfg.get("mc_version", "1.21.11")

    data = _fetch_json(PAPER_API)
    raw_versions: list[str] = data.get("versions", []) if isinstance(data, dict) else []
    # Reverse so newest versions appear first
    raw_versions = list(reversed(raw_versions))

    versions: list[VersionInfo] = []
    for v in raw_versions:
        versions.append(VersionInfo(
            version=v,
            safe=v in SAFE_VERSIONS,
        ))

    return VersionsResponse(
        versions=versions,
        current_version=current_version,
        safe_versions=list(sorted(SAFE_VERSIONS)),
    )


@router.post("/versions/set", response_model=SetVersionResponse)
async def set_version(body: SetVersionRequest):
    svc = _get_service()
    cfg = svc.read_config()

    requested = body.version.strip()
    if not requested:
        raise HTTPException(status_code=400, detail="Version cannot be empty")

    data = _fetch_json(PAPER_API)
    raw_versions: list[str] = data.get("versions", []) if isinstance(data, dict) else []
    if requested not in raw_versions:
        raise HTTPException(
            status_code=400,
            detail=f"Version '{requested}' is not available on PaperMC",
        )

    cfg["mc_version"] = requested
    svc.write_config(cfg, backup=True)

    is_safe = requested in SAFE_VERSIONS
    message = (
        f"Version {requested} set successfully."
        if is_safe
        else f"WARNING: Version {requested} is untested. Switching versions may break functionality, plugins, or server behavior."
    )

    return SetVersionResponse(
        status="ok" if is_safe else "warning",
        version=requested,
        safe=is_safe,
        message=message,
    )
