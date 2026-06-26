import logging
import json
import os
import shutil
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

from core.api.services import ApiService
from core.paths import get_root_dir

log = logging.getLogger(__name__)

router = APIRouter(tags=["Servers"])

PAPER_API = "https://api.papermc.io/v2/projects/paper"
SAFE_VERSIONS = {"1.21.11"}

_service: ApiService | None = None


def _get_service() -> ApiService:
    global _service
    if _service is None:
        _service = ApiService()
    return _service


def _get_servers_dir() -> Path:
    return (get_root_dir() / "servers").resolve()


def _get_server_mc_dir() -> Path:
    return (get_root_dir() / "server" / "mc").resolve()


def _get_active_jar_path() -> Path:
    return _get_server_mc_dir() / "server.jar"


def _fetch_json(url: str, timeout: int = 30) -> dict | list:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "TikTok2Mc/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        log.warning("Failed to fetch %s: %s", url, e)
        raise HTTPException(status_code=502, detail=f"Upstream error: {e}")


def _ensure_servers_dir() -> Path:
    d = _get_servers_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d


def _list_installed_versions() -> list[dict[str, Any]]:
    servers_dir = _get_servers_dir()
    versions = []
    seen = set()

    # Scan version-managed directories: servers/<version>/server.jar
    if servers_dir.exists():
        for subdir in sorted(servers_dir.iterdir()):
            if subdir.is_dir() and subdir.name.startswith(".") is False:
                jar = subdir / "server.jar"
                if jar.exists():
                    seen.add(subdir.name)
                    versions.append({
                        "version": subdir.name,
                        "path": str(subdir.relative_to(get_root_dir())),
                        "type": "safe" if subdir.name in SAFE_VERSIONS else "unsafe",
                        "hasJar": True,
                        "size": jar.stat().st_size,
                    })

    # Also recognise the legacy jar at server/mc/server.jar
    legacy_jar = _get_server_mc_dir() / "server.jar"
    if legacy_jar.exists():
        cfg_ver = _get_active_version() or "1.21.11"
        if cfg_ver not in seen:
            versions.append({
                "version": cfg_ver,
                "path": str(_get_server_mc_dir().relative_to(get_root_dir())),
                "type": "safe" if cfg_ver in SAFE_VERSIONS else "unsafe",
                "hasJar": True,
                "size": legacy_jar.stat().st_size,
            })

    return versions


def _get_active_version() -> str | None:
    svc = _get_service()
    try:
        cfg = svc.read_config()
        return cfg.get("mc_version")
    except Exception:
        return None


def _get_server_status() -> str:
    try:
        from core.lifecycle import get_supervisor
        supervisor = get_supervisor()
        proc = supervisor.get("Minecraft Server")
        if proc is None:
            return "unknown"
        return proc.state.value
    except Exception:
        return "stopped"


# ── Models ──────────────────────────────────────────────────────────


class ServerVersionInfo(BaseModel):
    version: str
    path: str
    type: str  # safe | unsafe | custom
    hasJar: bool
    size: int | None = None
    active: bool = False


class ServersListResponse(BaseModel):
    active: dict[str, Any]
    installed: list[ServerVersionInfo]
    serverStatus: str


class DownloadRequest(BaseModel):
    version: str


class DownloadResponse(BaseModel):
    status: str
    version: str
    path: str
    message: str


class SwitchRequest(BaseModel):
    version: str


class SwitchResponse(BaseModel):
    status: str
    version: str
    message: str


class CustomJarResponse(BaseModel):
    status: str
    version: str
    path: str
    message: str


class RemoveResponse(BaseModel):
    status: str
    version: str
    message: str


# ── Endpoints ───────────────────────────────────────────────────────


@router.get("/servers", response_model=ServersListResponse)
async def list_servers():
    installed = _list_installed_versions()
    active_version = _get_active_version() or "1.21.11"

    for v in installed:
        v["active"] = v["version"] == active_version

    active_jar = _get_active_jar_path()
    active = {
        "id": "default",
        "name": "Default Server",
        "path": str(_get_server_mc_dir().relative_to(get_root_dir())),
        "version": active_version,
        "status": _get_server_status(),
        "jarName": "server.jar",
        "jarExists": active_jar.exists(),
    }

    return ServersListResponse(
        active=active,
        installed=[ServerVersionInfo(**v) for v in installed],
        serverStatus=_get_server_status(),
    )


@router.post("/servers/download", response_model=DownloadResponse)
async def download_version(body: DownloadRequest):
    version = body.version.strip()
    if not version:
        raise HTTPException(status_code=400, detail="Version cannot be empty")

    # Verify version exists on PaperMC
    try:
        builds_data = _fetch_json(f"{PAPER_API}/versions/{version}/builds")
    except HTTPException:
        raise HTTPException(
            status_code=400,
            detail=f"Version '{version}' is not available on PaperMC",
        )

    builds = builds_data.get("builds", []) if isinstance(builds_data, dict) else []
    # PaperMC channels: STABLE (preferred) > BETA > ALPHA > default (legacy)
    _channel_priority = {"STABLE": 0, "default": 1, "BETA": 2, "ALPHA": 3}
    candidates = [
        b for b in builds
        if b.get("channel") in _channel_priority and b.get("downloads", {}).get("application")
    ]
    if not candidates:
        raise HTTPException(status_code=400, detail=f"No successful builds found for version '{version}'")

    # Pick the newest build with the highest priority channel
    candidates.sort(key=lambda b: (_channel_priority.get(b.get("channel"), 99), -b.get("build", 0)))
    latest = candidates[0]
    build_num = latest["build"]
    app_download = latest["downloads"]["application"]
    jar_name = app_download["name"]
    download_url = f"{PAPER_API}/versions/{version}/builds/{build_num}/downloads/{jar_name}"

    # Prepare target directory
    servers_dir = _ensure_servers_dir()
    target_dir = servers_dir / version
    target_dir.mkdir(parents=True, exist_ok=True)
    target_jar = target_dir / "server.jar"

    # Download
    try:
        log.info("Downloading PaperMC %s build %s -> %s", version, build_num, target_jar)
        req = urllib.request.Request(download_url, headers={"User-Agent": "TikTok2Mc/1.0"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            with target_jar.open("wb") as f:
                shutil.copyfileobj(resp, f)
        log.info("Download complete: %s (%s bytes)", target_jar, target_jar.stat().st_size)
    except Exception as e:
        log.exception("Download failed")
        raise HTTPException(status_code=500, detail=f"Download failed: {e}")

    return DownloadResponse(
        status="ok",
        version=version,
        path=str(target_dir.relative_to(get_root_dir())),
        message=f"Downloaded PaperMC {version} build {build_num} to {target_jar.name}",
    )


@router.post("/servers/switch", response_model=SwitchResponse)
async def switch_version(body: SwitchRequest):
    version = body.version.strip()
    if not version:
        raise HTTPException(status_code=400, detail="Version cannot be empty")

    servers_dir = _get_servers_dir()
    source_dir = servers_dir / version
    source_jar = source_dir / "server.jar"
    legacy_jar = _get_server_mc_dir() / "server.jar"

    if not source_jar.exists():
        # Fallback: if the legacy jar matches the requested version, it's valid
        svc = _get_service()
        try:
            cfg = svc.read_config()
            cfg_version = cfg.get("mc_version", "")
        except Exception:
            cfg_version = ""
        if version == cfg_version and legacy_jar.exists():
            # The legacy jar IS the requested version — nothing to copy
            source_jar = legacy_jar
        else:
            raise HTTPException(
                status_code=404,
                detail=f"Version '{version}' is not installed. Download it first.",
            )

    target_jar = _get_active_jar_path()
    server_mc_dir = _get_server_mc_dir()
    server_mc_dir.mkdir(parents=True, exist_ok=True)

    # Backup existing jar if it exists and isn't from the same version
    svc = _get_service()
    try:
        cfg = svc.read_config()
        current_version = cfg.get("mc_version", "")
    except Exception:
        current_version = ""

    if target_jar.exists() and current_version and current_version != version:
        backup_dir = servers_dir / current_version
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_jar = backup_dir / "server.jar"
        if not backup_jar.exists():
            try:
                shutil.copy2(target_jar, backup_jar)
                log.info("Backed up existing jar to %s", backup_jar)
            except Exception as e:
                log.warning("Could not backup existing jar: %s", e)

    # Copy new jar into place (skip if source and target are the same file)
    if source_jar.resolve() != target_jar.resolve():
        try:
            shutil.copy2(source_jar, target_jar)
            log.info("Switched active server.jar to %s", target_jar)
        except Exception as e:
            log.exception("Failed to copy jar")
            raise HTTPException(status_code=500, detail=f"Failed to activate version: {e}")
    else:
        log.info("Version %s is already active at %s", version, target_jar)

    # Update config
    try:
        cfg = svc.read_config()
        cfg["mc_version"] = version
        svc.write_config(cfg, backup=True)
    except Exception as e:
        log.exception("Failed to update config")
        raise HTTPException(status_code=500, detail=f"Version switched but config update failed: {e}")

    is_safe = version in SAFE_VERSIONS
    return SwitchResponse(
        status="ok",
        version=version,
        message=(
            f"Switched to {version}."
            if is_safe
            else f"Switched to {version}. WARNING: This version is untested."
        ),
    )


@router.post("/servers/custom", response_model=CustomJarResponse)
async def upload_custom_jar(
    file: UploadFile = File(...),
    name: str = Form(...),
):
    if not file.filename or not file.filename.endswith(".jar"):
        raise HTTPException(status_code=400, detail="Only .jar files are accepted")

    version_name = name.strip() or file.filename.replace(".jar", "")
    if not version_name:
        raise HTTPException(status_code=400, detail="Version name is required")

    # Sanitize version name for filesystem
    version_name = "".join(c for c in version_name if c.isalnum() or c in "._-").strip()
    if not version_name:
        raise HTTPException(status_code=400, detail="Invalid version name")

    servers_dir = _ensure_servers_dir()
    target_dir = servers_dir / version_name
    target_dir.mkdir(parents=True, exist_ok=True)
    target_jar = target_dir / "server.jar"

    try:
        with target_jar.open("wb") as f:
            while chunk := file.file.read(8192):
                f.write(chunk)
        log.info("Saved custom jar to %s (%s bytes)", target_jar, target_jar.stat().st_size)
    except Exception as e:
        log.exception("Failed to save custom jar")
        raise HTTPException(status_code=500, detail=f"Failed to save jar: {e}")
    finally:
        file.file.close()

    return CustomJarResponse(
        status="ok",
        version=version_name,
        path=str(target_dir.relative_to(get_root_dir())),
        message=f"Custom jar saved as '{version_name}'",
    )


@router.delete("/servers/{version}", response_model=RemoveResponse)
async def remove_version(version: str):
    servers_dir = _get_servers_dir()
    target_dir = servers_dir / version

    if not target_dir.exists() or not target_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Version '{version}' not found")

    # Prevent removing the currently active version's source if it's the only copy
    svc = _get_service()
    try:
        cfg = svc.read_config()
        active_version = cfg.get("mc_version", "")
    except Exception:
        active_version = ""

    if version == active_version:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot remove the currently active version '{version}'. Switch to another version first.",
        )

    try:
        shutil.rmtree(target_dir)
        log.info("Removed version directory: %s", target_dir)
    except Exception as e:
        log.exception("Failed to remove version")
        raise HTTPException(status_code=500, detail=f"Failed to remove version: {e}")

    return RemoveResponse(
        status="ok",
        version=version,
        message=f"Version '{version}' removed",
    )
