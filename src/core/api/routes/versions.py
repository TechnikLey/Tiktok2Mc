import json
import logging
import urllib.request

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.api.services import ApiService

log = logging.getLogger(__name__)

router = APIRouter(tags=["Versions"])

PAPER_API = "https://fill.papermc.io/v3/projects/paper"

SAFE_VERSIONS = {"1.21.11"}

_MIN_SUPPORTED_MAJOR = 1
_MIN_SUPPORTED_MINOR = 13


def _is_stable_version(version: str) -> bool:
    return "-" not in version


def _is_supported_version(version: str) -> bool:
    if not _is_stable_version(version):
        return False
    parts = version.split(".")
    try:
        major = int(parts[0])
        minor = int(parts[1]) if len(parts) > 1 else 0
    except (ValueError, IndexError):
        return False
    return major > _MIN_SUPPORTED_MAJOR or (major == _MIN_SUPPORTED_MAJOR and minor >= _MIN_SUPPORTED_MINOR)


def _flatten_versions(nested: dict) -> list[str]:
    result = []
    for versions in nested.values():
        if isinstance(versions, list):
            result.extend(versions)
    return result


def _semver_sort_key(v: str) -> tuple[int, ...]:
    return tuple(int(p) if p.isdigit() else 0 for p in v.split("."))

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
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
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
    raw_versions = _flatten_versions(data.get("versions", {})) if isinstance(data, dict) else []
    supported = [v for v in raw_versions if _is_supported_version(v)]
    supported.sort(key=_semver_sort_key, reverse=True)

    versions: list[VersionInfo] = []
    for v in supported:
        versions.append(VersionInfo(
            version=v,
            safe=v in SAFE_VERSIONS,
        ))

    return VersionsResponse(
        versions=versions,
        current_version=current_version,
        safe_versions=sorted(SAFE_VERSIONS),
    )


@router.post("/versions/set", response_model=SetVersionResponse)
async def set_version(body: SetVersionRequest):
    svc = _get_service()
    cfg = svc.read_config()

    requested = body.version.strip()
    if not requested:
        raise HTTPException(status_code=400, detail="Version cannot be empty")

    if not _is_supported_version(requested):
        raise HTTPException(
            status_code=400,
            detail=f"Version '{requested}' is not supported. Minimum supported version is {_MIN_SUPPORTED_MAJOR}.{_MIN_SUPPORTED_MINOR}+.",
        )

    data = _fetch_json(PAPER_API)
    raw_versions = _flatten_versions(data.get("versions", {})) if isinstance(data, dict) else []
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
