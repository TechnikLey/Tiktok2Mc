import asyncio
import logging
import json
import os
import shutil
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

from core.api.services import ApiService
from core.paths import get_root_dir

log = logging.getLogger(__name__)

router = APIRouter(tags=["Servers"])

PAPER_API = "https://fill.papermc.io/v3/projects/paper"
SAFE_VERSIONS = {"1.21.11"}

_MIN_SUPPORTED_MAJOR = 1
_MIN_SUPPORTED_MINOR = 13


def _flatten_versions(nested: dict) -> list[str]:
    result = []
    for group, versions in nested.items():
        if isinstance(versions, list):
            result.extend(versions)
    return result


def _semver_sort_key(v: str) -> tuple[int, ...]:
    return tuple(int(p) if p.isdigit() else 0 for p in v.split("."))


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


def _read_meta(version_dir: Path) -> dict[str, Any]:
    meta_file = version_dir / ".meta.json"
    if meta_file.exists():
        try:
            return json.loads(meta_file.read_text("utf-8"))
        except Exception:
            return {}
    return {}


def _write_meta(version_dir: Path, meta: dict[str, Any]) -> None:
    meta_file = version_dir / ".meta.json"
    try:
        meta_file.write_text(json.dumps(meta), encoding="utf-8")
    except Exception as e:
        log.warning("Failed to write meta for %s: %s", version_dir, e)


def _list_installed_versions() -> list[dict[str, Any]]:
    servers_dir = _get_servers_dir()
    versions = []
    seen = set()

    def _resolve_type(name: str, meta: dict) -> str:
        if meta.get("origin") == "custom":
            return "custom"
        return "safe" if name in SAFE_VERSIONS else "unsafe"

    # Scan version-managed directories: servers/<version>/server.jar
    if servers_dir.exists():
        for subdir in sorted(servers_dir.iterdir()):
            if subdir.is_dir() and subdir.name.startswith(".") is False:
                jar = subdir / "server.jar"
                if jar.exists():
                    seen.add(subdir.name)
                    meta = _read_meta(subdir)
                    versions.append({
                        "version": subdir.name,
                        "path": str(subdir.relative_to(get_root_dir())),
                        "type": _resolve_type(subdir.name, meta),
                        "hasJar": True,
                        "size": jar.stat().st_size,
                    })

    # Also recognise the legacy jar at server/mc/server.jar
    legacy_jar = _get_server_mc_dir() / "server.jar"
    if legacy_jar.exists():
        cfg_ver = _get_active_version() or "1.21.11"
        if cfg_ver not in seen:
            meta = _read_meta(_get_server_mc_dir())
            versions.append({
                "version": cfg_ver,
                "path": str(_get_server_mc_dir().relative_to(get_root_dir())),
                "type": _resolve_type(cfg_ver, meta),
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


def _get_server_status(instance_id: str = "default") -> str:
    try:
        from core.lifecycle import get_supervisor
        supervisor = get_supervisor()
        proc_name = _instance_process_name(instance_id)
        proc = supervisor.get(proc_name)
        if proc is None:
            return "unknown"
        return proc.state.value
    except Exception:
        return "stopped"


# ── Server Instance Model ───────────────────────────────────────────


INSTANCE_CONFIG_KEY = "instances"

DEFAULT_INSTANCES: dict[str, dict[str, Any]] = {
    "default": {
        "name": "Default Server",
        "version": "1.21.11",
        "port": 25565,
        "enabled": True,
        "auto_start": False,
        "java_args": "",
    }
}


def _load_instances(svc: ApiService | None = None) -> dict[str, dict[str, Any]]:
    if svc is None:
        svc = ApiService()
    try:
        cfg = svc.read_config()
        instances = cfg.get(INSTANCE_CONFIG_KEY, {})
        if not isinstance(instances, dict) or not instances:
            return dict(DEFAULT_INSTANCES)
        return instances
    except Exception:
        return dict(DEFAULT_INSTANCES)


def _save_instances(instances: dict[str, dict[str, Any]]) -> None:
    svc = ApiService()
    cfg = svc.read_config()
    cfg[INSTANCE_CONFIG_KEY] = instances
    svc.write_config(cfg, backup=True)


def _get_instance(instance_id: str) -> dict[str, Any] | None:
    instances = _load_instances()
    return instances.get(instance_id)


def _instance_process_name(instance_id: str) -> str:
    if instance_id == "default":
        return "Minecraft Server"
    return f"Minecraft Server:{instance_id}"


# ── Models ──────────────────────────────────────────────────────────


class ServerVersionInfo(BaseModel):
    version: str
    path: str
    type: str  # safe | unsafe | custom
    hasJar: bool
    size: int | None = None
    active: bool = False


class InstanceInfo(BaseModel):
    id: str
    name: str
    version: str
    port: int
    enabled: bool
    auto_start: bool
    java_args: str
    status: str
    path: str


class ServersListResponse(BaseModel):
    instances: list[InstanceInfo]
    installed: list[ServerVersionInfo]


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


class CreateInstanceRequest(BaseModel):
    name: str
    version: str = "1.21.11"
    port: int = 25565
    java_args: str = ""


class UpdateInstanceRequest(BaseModel):
    name: str | None = None
    version: str | None = None
    port: int | None = None
    enabled: bool | None = None
    auto_start: bool | None = None
    java_args: str | None = None


# ── Endpoints ───────────────────────────────────────────────────────


@router.get("/servers", response_model=ServersListResponse)
async def list_servers():
    installed = _list_installed_versions()
    active_version = _get_active_version() or "1.21.11"

    for v in installed:
        v["active"] = v["version"] == active_version

    raw_instances = _load_instances()
    instances: list[InstanceInfo] = []
    for inst_id, inst_data in raw_instances.items():
        version = inst_data.get("version", active_version)
        instances.append(InstanceInfo(
            id=inst_id,
            name=inst_data.get("name", inst_id),
            version=version,
            port=inst_data.get("port", 25565),
            enabled=inst_data.get("enabled", True),
            auto_start=inst_data.get("auto_start", False),
            java_args=inst_data.get("java_args", ""),
            status=_get_server_status(inst_id),
            path=str(_get_server_mc_dir().relative_to(get_root_dir())),
        ))

    return ServersListResponse(
        instances=instances,
        installed=[ServerVersionInfo(**v) for v in installed],
    )


# ── Instance CRUD ───────────────────────────────────────────────────


def _new_instance_id(name: str, existing: dict) -> str:
    base = name.lower().replace(" ", "-").replace("_", "-")
    base = "".join(c for c in base if c.isalnum() or c == "-")
    if not base:
        base = "server"
    candidate = base
    n = 1
    while candidate in existing:
        n += 1
        candidate = f"{base}-{n}"
    return candidate


@router.post("/servers/instances")
async def create_instance(body: CreateInstanceRequest):
    instances = _load_instances()
    inst_id = _new_instance_id(body.name, instances)
    instances[inst_id] = {
        "name": body.name,
        "version": body.version,
        "port": body.port,
        "enabled": True,
        "auto_start": False,
        "java_args": body.java_args,
    }
    _save_instances(instances)
    return {"status": "ok", "id": inst_id, "message": f"Server instance '{body.name}' created"}


@router.get("/servers/instances")
async def list_instances():
    raw = _load_instances()
    result = []
    for inst_id, data in raw.items():
        result.append({
            "id": inst_id,
            "name": data.get("name", inst_id),
            "version": data.get("version", "1.21.11"),
            "port": data.get("port", 25565),
            "enabled": data.get("enabled", True),
            "auto_start": data.get("auto_start", False),
            "java_args": data.get("java_args", ""),
            "status": _get_server_status(inst_id),
        })
    return {"instances": result}


@router.get("/servers/instances/{instance_id}")
async def get_instance(instance_id: str):
    data = _get_instance(instance_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Server instance '{instance_id}' not found")
    return {
        "id": instance_id,
        "name": data.get("name", instance_id),
        "version": data.get("version", "1.21.11"),
        "port": data.get("port", 25565),
        "enabled": data.get("enabled", True),
        "auto_start": data.get("auto_start", False),
        "java_args": data.get("java_args", ""),
        "status": _get_server_status(instance_id),
    }


@router.put("/servers/instances/{instance_id}")
async def update_instance(instance_id: str, body: UpdateInstanceRequest):
    instances = _load_instances()
    if instance_id not in instances:
        raise HTTPException(status_code=404, detail=f"Server instance '{instance_id}' not found")
    data = instances[instance_id]
    if body.name is not None:
        data["name"] = body.name
    if body.version is not None:
        data["version"] = body.version
    if body.port is not None:
        data["port"] = body.port
    if body.enabled is not None:
        data["enabled"] = body.enabled
    if body.auto_start is not None:
        data["auto_start"] = body.auto_start
    if body.java_args is not None:
        data["java_args"] = body.java_args
    _save_instances(instances)
    return {"status": "ok", "message": f"Server instance '{instance_id}' updated"}


@router.delete("/servers/instances/{instance_id}")
async def delete_instance(instance_id: str):
    if instance_id == "default":
        raise HTTPException(status_code=400, detail="Cannot delete the default server instance")
    instances = _load_instances()
    if instance_id not in instances:
        raise HTTPException(status_code=404, detail=f"Server instance '{instance_id}' not found")
    del instances[instance_id]
    _save_instances(instances)
    return {"status": "ok", "message": f"Server instance '{instance_id}' deleted"}


@router.put("/servers/instances/{instance_id}/version")
async def set_instance_version(instance_id: str, body: SwitchRequest):
    version = body.version.strip()
    if not version:
        raise HTTPException(status_code=400, detail="Version cannot be empty")
    instances = _load_instances()
    if instance_id not in instances:
        raise HTTPException(status_code=404, detail=f"Server instance '{instance_id}' not found")
    instances[instance_id]["version"] = version
    _save_instances(instances)
    return {"status": "ok", "version": version, "message": f"Instance '{instance_id}' version set to {version}"}


@router.post("/servers/download", response_model=DownloadResponse)
async def download_version(body: DownloadRequest):
    version = body.version.strip()
    if not version:
        raise HTTPException(status_code=400, detail="Version cannot be empty")
    if not _is_supported_version(version):
        raise HTTPException(
            status_code=400,
            detail=f"Version '{version}' is not supported. Minimum supported version is {_MIN_SUPPORTED_MAJOR}.{_MIN_SUPPORTED_MINOR}+.",
        )

    # Check if version is already installed (duplicate download guard)
    servers_dir = _ensure_servers_dir()
    target_dir = servers_dir / version
    target_jar = target_dir / "server.jar"
    already_installed = target_jar.exists()

    if already_installed:
        log.info("Version %s is already installed at %s", version, target_jar)
        return DownloadResponse(
            status="already_installed",
            version=version,
            path=str(target_dir.relative_to(get_root_dir())),
            message=f"Version '{version}' is already installed at {target_dir.name}",
        )

    # Verify version exists on PaperMC with a STABLE build
    try:
        builds = _fetch_json(f"{PAPER_API}/versions/{version}/builds")
    except HTTPException as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Version '{version}' is not available on PaperMC",
        )

    if not isinstance(builds, list) or not builds:
        raise HTTPException(status_code=400, detail=f"No builds found for version '{version}'")

    _channel_priority = {"STABLE": 0, "BETA": 1, "ALPHA": 2}
    candidates = [
        b for b in builds
        if b.get("channel") in _channel_priority
        and b.get("downloads", {}).get("server:default")
    ]
    if not candidates:
        raise HTTPException(status_code=400, detail=f"No successful builds found for version '{version}'")

    candidates.sort(key=lambda b: (_channel_priority.get(b.get("channel"), 99), -b.get("build", 0)))
    latest = candidates[0]
    build_num = latest["build"]
    download_obj = latest["downloads"]["server:default"]
    download_url = download_obj["url"]

    if not download_url:
        raise HTTPException(status_code=502, detail=f"PaperMC did not return a download URL for version '{version}' build {build_num}")

    # Prepare target directory
    target_dir.mkdir(parents=True, exist_ok=True)

    # Download with detailed error reporting
    download_exc = None
    for attempt in range(3):
        try:
            log.info("Downloading PaperMC %s build %s -> %s (attempt %d/3)", version, build_num, target_jar, attempt + 1)
            req = urllib.request.Request(download_url, headers={"User-Agent": "TikTok2Mc/1.0"})
            resp = urllib.request.urlopen(req, timeout=120)
            try:
                with target_jar.open("wb") as f:
                    shutil.copyfileobj(resp, f)
            finally:
                resp.close()
            size = target_jar.stat().st_size
            if size == 0:
                target_jar.unlink()
                raise ValueError("Downloaded file is empty")
            log.info("Download complete: %s (%s bytes)", target_jar, size)
            download_exc = None
            break
        except urllib.error.HTTPError as e:
            download_exc = f"PaperMC server returned HTTP {e.code} for build {build_num}: {e.reason}"
            log.warning("Download attempt %d/3 failed: %s", attempt + 1, download_exc)
            await asyncio.sleep(1)
        except urllib.error.URLError as e:
            download_exc = f"Network error downloading build {build_num}: {e.reason}"
            log.warning("Download attempt %d/3 failed: %s", attempt + 1, download_exc)
            await asyncio.sleep(1)
        except Exception as e:
            download_exc = f"Unexpected error downloading build {build_num}: {e}"
            log.exception("Download attempt %d/3 failed", attempt + 1)
            await asyncio.sleep(1)

    if download_exc:
        # Clean up partial download if any
        if target_jar.exists():
            try:
                target_jar.unlink()
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=download_exc)

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
    if not _is_supported_version(version):
        raise HTTPException(
            status_code=400,
            detail=f"Version '{version}' is not supported. Minimum supported version is {_MIN_SUPPORTED_MAJOR}.{_MIN_SUPPORTED_MINOR}+.",
        )

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

    # Auto-restart the Minecraft Server if it is currently running
    restart_initiated = False
    try:
        from core.lifecycle import get_supervisor, ProcessState
        supervisor = get_supervisor()
        proc = supervisor.get("Minecraft Server")
        if proc is not None and proc.state == ProcessState.RUNNING:
            log.info("Version switched to %s — restarting Minecraft Server", version)
            await supervisor.stop("Minecraft Server")
            await supervisor.start("Minecraft Server")
            restart_initiated = True
    except Exception as e:
        log.warning("Failed to auto-restart server after version switch: %s", e)

    is_safe = version in SAFE_VERSIONS
    msg = f"Switched to {version}."
    if restart_initiated:
        msg += " Server restarted to apply changes."
    elif not is_safe:
        msg += " WARNING: This version is untested."
    return SwitchResponse(
        status="ok",
        version=version,
        message=msg,
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
        _write_meta(target_dir, {"origin": "custom", "originalName": file.filename})
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
