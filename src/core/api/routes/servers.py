import asyncio
import json
import logging
import os
import platform
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from ruamel.yaml.error import YAMLError

from core.api.services import ApiService
from core.paths import get_root_dir, get_servers_dir, get_versions_dir

log = logging.getLogger(__name__)

router = APIRouter(tags=["Servers"])

PAPER_API = "https://fill.papermc.io/v3/projects/paper"
SAFE_VERSIONS = {"1.21.11"}

_MIN_SUPPORTED_MAJOR = 1
_MIN_SUPPORTED_MINOR = 13


def _flatten_versions(nested: dict) -> list[str]:
    result = []
    for versions in nested.values():
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
    return major > _MIN_SUPPORTED_MAJOR or (
        major == _MIN_SUPPORTED_MAJOR and minor >= _MIN_SUPPORTED_MINOR
    )


_service: ApiService | None = None


def _get_service() -> ApiService:
    global _service
    if _service is None:
        _service = ApiService()
    return _service


def _get_versions_dir() -> Path:
    return get_versions_dir()


def _get_instance_dir(instance_id: str) -> Path:
    return (get_servers_dir() / instance_id).resolve()


def _instance_has_jar(instance_id: str) -> bool:
    """Whether the instance directory actually contains a runnable server.jar."""
    return (_get_instance_dir(instance_id) / "server.jar").is_file()


def _ensure_versions_dir() -> Path:
    d = _get_versions_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d


def _ensure_instance_dir(instance_id: str) -> Path:
    d = _get_instance_dir(instance_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _sync_datapack_to_instance(instance_id: str) -> Path | None:
    """Copy the StreamingTool datapack from the central store to *instance_id*.

    Creates the instance's ``world/datapacks/`` directory if needed and copies
    the full datapack folder and zip from ``server/datapack/``.
    Returns the instance's datapack root path, or ``None`` on failure.
    """
    dp_dir = get_servers_dir() / "datapack"
    if not dp_dir.exists():
        log.warning(
            "[DATAPACK] Datapack source not found at %s — nothing to sync", dp_dir
        )
        return None

    instance_dp = get_servers_dir() / instance_id / "world" / "datapacks"
    instance_dp.mkdir(parents=True, exist_ok=True)

    dp_name = "StreamingTool"
    src_dir = dp_dir / dp_name
    dst_dir = instance_dp / dp_name
    src_zip = dp_dir / f"{dp_name}.zip"
    dst_zip = instance_dp / f"{dp_name}.zip"

    try:
        # Remove old datapack in instance
        if dst_dir.exists():
            shutil.rmtree(dst_dir)
        if dst_zip.exists():
            dst_zip.unlink()

        # Copy fresh datapack
        if src_dir.exists():
            shutil.copytree(src_dir, dst_dir)
        if src_zip.exists():
            shutil.copy2(src_zip, dst_zip)

        log.info(
            "[DATAPACK] Synced '%s' datapack to instance '%s'", dp_name, instance_id
        )
        return instance_dp
    except OSError as exc:
        log.warning(
            "[DATAPACK] Failed to sync datapack to instance '%s': %s", instance_id, exc
        )
        return None


def _resolve_version_jar(version: str) -> Path | None:
    """Return the path to server.jar for an installed *version*.

    Only checks the canonical template repository:
    versions/<version>/server.jar
    """
    versions_dir = _get_versions_dir()
    jar = versions_dir / version / "server.jar"
    if jar.exists():
        return jar
    return None


def _fetch_json(url: str, timeout: int = 30) -> dict | list:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "TikTok2Mc/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        log.warning("Failed to fetch %s: %s", url, e)
        raise HTTPException(status_code=502, detail=f"Upstream error: {e}")


def _read_meta(version_dir: Path) -> dict[str, Any]:
    meta_file = version_dir / ".meta.json"
    if meta_file.exists():
        try:
            return json.loads(meta_file.read_text("utf-8"))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            return {}
    return {}


def _write_meta(version_dir: Path, meta: dict[str, Any]) -> None:
    meta_file = version_dir / ".meta.json"
    try:
        meta_file.write_text(json.dumps(meta), encoding="utf-8")
    except (OSError, TypeError) as e:
        log.warning("Failed to write meta for %s: %s", version_dir, e)


def _list_installed_versions() -> list[dict[str, Any]]:
    versions_dir = _get_versions_dir()
    versions = []

    def _resolve_type(name: str, meta: dict) -> str:
        if meta.get("origin") == "custom":
            return "custom"
        return "safe" if name in SAFE_VERSIONS else "unsafe"

    # Scan version template directories: versions/<version>/server.jar
    if versions_dir.exists():
        for subdir in sorted(versions_dir.iterdir()):
            if subdir.is_dir() and subdir.name.startswith(".") is False:
                jar = subdir / "server.jar"
                if jar.exists():
                    meta = _read_meta(subdir)
                    versions.append(
                        {
                            "version": subdir.name,
                            "path": str(subdir.relative_to(get_root_dir())),
                            "type": _resolve_type(subdir.name, meta),
                            "hasJar": True,
                            "size": jar.stat().st_size,
                        }
                    )

    return versions


def _get_active_version() -> str | None:
    svc = _get_service()
    try:
        cfg = svc.read_config()
        return cfg.get("mc_version")
    except Exception:  # best-effort; caller falls back to None
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
    except Exception:  # status reporting is best-effort
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
    except Exception:  # config read failures fall back to defaults
        return dict(DEFAULT_INSTANCES)


def _save_instances(instances: dict[str, dict[str, Any]]) -> None:
    svc = ApiService()
    cfg = svc.read_config()
    cfg[INSTANCE_CONFIG_KEY] = instances
    svc.write_config(cfg, backup=True, replace_keys=[INSTANCE_CONFIG_KEY])


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
    hasJar: bool


class ServersListResponse(BaseModel):
    instances: list[InstanceInfo]
    installed: list[ServerVersionInfo]
    safe_versions: list[str]
    current_version: str


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

    try:
        cfg = _get_service().read_config()
        current_version = cfg.get("mc_version", "1.21.11")
    except Exception:
        current_version = "1.21.11"

    raw_instances = _load_instances()
    instances: list[InstanceInfo] = []
    for inst_id, inst_data in raw_instances.items():
        version = inst_data.get("version", "1.21.11")
        instances.append(
            InstanceInfo(
                id=inst_id,
                name=inst_data.get("name", inst_id),
                version=version,
                port=inst_data.get("port", 25565),
                enabled=inst_data.get("enabled", True),
                auto_start=inst_data.get("auto_start", False),
                java_args=inst_data.get("java_args", ""),
                status=_get_server_status(inst_id),
                path=str(_get_instance_dir(inst_id).relative_to(get_root_dir())),
                hasJar=_instance_has_jar(inst_id),
            )
        )

    return ServersListResponse(
        instances=instances,
        installed=[ServerVersionInfo(**v) for v in installed],
        safe_versions=sorted(SAFE_VERSIONS),
        current_version=current_version,
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
    log.info(
        "CREATE_INSTANCE request: name='%s' version='%s' port=%d java_args='%s'",
        body.name,
        body.version,
        body.port,
        body.java_args,
    )
    instances = _load_instances()

    # Validate name uniqueness
    existing_names = {
        data.get("name", "").strip().lower() for data in instances.values()
    }
    if body.name.strip().lower() in existing_names:
        raise HTTPException(
            status_code=409,
            detail=f"A server instance named '{body.name}' already exists.",
        )

    # Validate port uniqueness
    existing_ports = {data.get("port", 25565) for data in instances.values()}
    if body.port in existing_ports:
        conflicting = [
            iid
            for iid, data in instances.items()
            if data.get("port", 25565) == body.port
        ]
        raise HTTPException(
            status_code=409,
            detail=f"Port {body.port} is already in use by instance(s): {', '.join(conflicting)}.",
        )

    # Validate version is installed
    version = body.version.strip()
    if not version:
        raise HTTPException(status_code=400, detail="Version is required.")

    source_jar = _resolve_version_jar(version)
    if source_jar is None:
        checked_path = str(_get_versions_dir() / version / "server.jar")
        log.warning(
            "Version '%s' not found. Checked: %s",
            version,
            checked_path,
        )
        raise HTTPException(
            status_code=400,
            detail=f"Version '{version}' is not installed. Download it first.",
        )

    inst_id = _new_instance_id(body.name, instances)

    # Create instance directory and copy server.jar
    instance_dir = _ensure_instance_dir(inst_id)
    target_jar = instance_dir / "server.jar"
    try:
        shutil.copy2(source_jar, target_jar)
        log.info("Copied %s -> %s for instance '%s'", source_jar, target_jar, inst_id)
    except OSError as e:
        log.exception("Failed to copy server.jar for instance '%s'", inst_id)
        raise HTTPException(status_code=500, detail=f"Failed to copy server.jar: {e}")

    # Write server.properties with instance port
    props_file = instance_dir / "server.properties"
    try:
        _set_server_property(props_file, "server-port", str(body.port))
        _set_server_property(props_file, "enable-rcon", "true")
    except OSError as e:
        log.warning(
            "Failed to write server.properties for instance '%s': %s", inst_id, e
        )

    # Accept EULA
    eula_file = instance_dir / "eula.txt"
    try:
        eula_file.write_text("eula=true\n", encoding="utf-8")
    except OSError as e:
        log.warning("Failed to write eula.txt for instance '%s': %s", inst_id, e)

    # Sync datapack from default server to the new instance
    _sync_datapack_to_instance(inst_id)

    instances[inst_id] = {
        "name": body.name,
        "version": version,
        "port": body.port,
        "enabled": True,
        "auto_start": False,
        "java_args": body.java_args,
    }
    _save_instances(instances)
    return {
        "status": "ok",
        "id": inst_id,
        "message": f"Server instance '{body.name}' created",
    }


def _set_server_property(file_path: Path, key: str, value: str) -> None:
    """Set or append a property in a properties file."""
    try:
        if not file_path.exists():
            file_path.write_text("", encoding="utf-8")
        lines = file_path.read_text("utf-8").splitlines()
        found = False
        for i, line in enumerate(lines):
            if line.startswith(f"{key}="):
                lines[i] = f"{key}={value}"
                found = True
                break
        if not found:
            lines.append(f"{key}={value}")
        file_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError as e:
        log.warning("Failed to set property %s: %s", key, e)


@router.get("/servers/instances")
async def list_instances():
    raw = _load_instances()
    result = []
    for inst_id, data in raw.items():
        result.append(
            {
                "id": inst_id,
                "name": data.get("name", inst_id),
                "version": data.get("version", "1.21.11"),
                "port": data.get("port", 25565),
                "enabled": data.get("enabled", True),
                "auto_start": data.get("auto_start", False),
                "java_args": data.get("java_args", ""),
                "status": _get_server_status(inst_id),
                "hasJar": _instance_has_jar(inst_id),
            }
        )
    return {"instances": result}


@router.get("/servers/instances/{instance_id}")
async def get_instance(instance_id: str):
    data = _get_instance(instance_id)
    if data is None:
        raise HTTPException(
            status_code=404, detail=f"Server instance '{instance_id}' not found"
        )
    return {
        "id": instance_id,
        "name": data.get("name", instance_id),
        "version": data.get("version", "1.21.11"),
        "port": data.get("port", 25565),
        "enabled": data.get("enabled", True),
        "auto_start": data.get("auto_start", False),
        "java_args": data.get("java_args", ""),
        "status": _get_server_status(instance_id),
        "hasJar": _instance_has_jar(instance_id),
    }


@router.put("/servers/instances/{instance_id}")
async def update_instance(instance_id: str, body: UpdateInstanceRequest):
    instances = _load_instances()
    if instance_id not in instances:
        raise HTTPException(
            status_code=404, detail=f"Server instance '{instance_id}' not found"
        )
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
        raise HTTPException(
            status_code=400, detail="Cannot delete the default server instance"
        )
    instances = _load_instances()
    if instance_id not in instances:
        raise HTTPException(
            status_code=404, detail=f"Server instance '{instance_id}' not found"
        )

    # Remove from configuration first
    del instances[instance_id]
    _save_instances(instances)

    # Delete instance directory
    instance_dir = _get_instance_dir(instance_id)
    if instance_dir.exists():
        try:
            shutil.rmtree(instance_dir)
            log.info("Deleted instance directory: %s", instance_dir)
        except OSError as e:
            log.warning("Failed to delete instance directory %s: %s", instance_dir, e)

    return {"status": "ok", "message": f"Server instance '{instance_id}' deleted"}


@router.post("/servers/instances/{instance_id}/open")
async def open_instance_folder(instance_id: str):
    instances = _load_instances()
    if instance_id not in instances:
        raise HTTPException(
            status_code=404, detail=f"Server instance '{instance_id}' not found"
        )
    target_path = _get_instance_dir(instance_id)
    if not target_path.exists():
        raise HTTPException(
            status_code=404, detail=f"Directory does not exist: {target_path}"
        )

    # Open the folder in the OS file explorer
    opened = False
    system = platform.system()
    try:
        if system == "Windows":
            os.startfile(str(target_path))
            opened = True
        elif system == "Darwin":
            await asyncio.to_thread(
                subprocess.Popen,
                ["open", str(target_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            opened = True
        else:
            await asyncio.to_thread(
                subprocess.Popen,
                ["xdg-open", str(target_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            opened = True
    except OSError as e:
        log.warning("Failed to open folder %s: %s", target_path, e)

    return {"path": str(target_path), "opened": opened}


@router.put("/servers/instances/{instance_id}/version")
async def set_instance_version(instance_id: str, body: SwitchRequest):
    version = body.version.strip()
    if not version:
        raise HTTPException(status_code=400, detail="Version cannot be empty")
    instances = _load_instances()
    if instance_id not in instances:
        raise HTTPException(
            status_code=404, detail=f"Server instance '{instance_id}' not found"
        )
    instances[instance_id]["version"] = version
    _save_instances(instances)
    return {
        "status": "ok",
        "version": version,
        "message": f"Instance '{instance_id}' version set to {version}",
    }


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
    versions_dir = _ensure_versions_dir()
    target_dir = versions_dir / version
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
        builds = await asyncio.to_thread(
            _fetch_json, f"{PAPER_API}/versions/{version}/builds"
        )
    except HTTPException:
        raise HTTPException(
            status_code=400,
            detail=f"Version '{version}' is not available on PaperMC",
        )

    if not isinstance(builds, list) or not builds:
        raise HTTPException(
            status_code=400, detail=f"No builds found for version '{version}'"
        )

    _channel_priority = {"STABLE": 0, "BETA": 1, "ALPHA": 2}
    candidates = [
        b
        for b in builds
        if b.get("channel") in _channel_priority
        and b.get("downloads", {}).get("server:default")
    ]
    if not candidates:
        raise HTTPException(
            status_code=400,
            detail=f"No successful builds found for version '{version}'",
        )

    candidates.sort(
        key=lambda b: (_channel_priority.get(b.get("channel"), 99), -b.get("id", 0))
    )
    try:
        latest = candidates[0]
        build_num = latest["id"]
        download_obj = latest["downloads"]["server:default"]
        download_url = download_obj["url"]
    except (KeyError, TypeError) as e:
        log.exception("Unexpected PaperMC API format for version %s", version)
        raise HTTPException(
            status_code=502,
            detail=f"Unexpected API response from PaperMC for version '{version}': {e}",
        )

    if not download_url:
        raise HTTPException(
            status_code=502,
            detail=f"PaperMC did not return a download URL for version '{version}' build {build_num}",
        )

    # Prepare target directory
    target_dir.mkdir(parents=True, exist_ok=True)

    # Download with detailed error reporting
    download_exc = None
    for attempt in range(3):
        try:
            log.info(
                "Downloading PaperMC %s build %s -> %s (attempt %d/3)",
                version,
                build_num,
                target_jar,
                attempt + 1,
            )
            req = urllib.request.Request(
                download_url, headers={"User-Agent": "TikTok2Mc/1.0"}
            )
            resp = await asyncio.to_thread(urllib.request.urlopen, req, timeout=120)
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
        except Exception as e:  # any download failure is retried, then surfaced
            download_exc = f"Unexpected error downloading build {build_num}: {e}"
            log.exception("Download attempt %d/3 failed", attempt + 1)
            await asyncio.sleep(1)

    if download_exc:
        # Clean up partial download if any
        if target_jar.exists():
            try:
                target_jar.unlink()
            except OSError:
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

    # Find the source jar
    source_jar = _resolve_version_jar(version)
    if source_jar is None:
        raise HTTPException(
            status_code=404,
            detail=f"Version '{version}' is not installed. Download it first.",
        )

    default_instance_dir = _get_instance_dir("default")
    legacy_jar = default_instance_dir / "server.jar"
    target_jar = legacy_jar
    default_instance_dir.mkdir(parents=True, exist_ok=True)

    # Backup existing jar if it exists and isn't from the same version
    svc = _get_service()
    try:
        cfg = svc.read_config()
        current_version = cfg.get("mc_version", "")
    except Exception:  # best-effort; defaults to no backup
        current_version = ""

    if target_jar.exists() and current_version and current_version != version:
        backup_dir = _get_versions_dir() / current_version
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_jar = backup_dir / "server.jar"
        if not backup_jar.exists():
            try:
                shutil.copy2(target_jar, backup_jar)
                log.info("Backed up existing jar to %s", backup_jar)
            except OSError as e:
                log.warning("Could not backup existing jar: %s", e)

    # Copy new jar into place (skip if source and target are the same file)
    if source_jar.resolve() != target_jar.resolve():
        try:
            shutil.copy2(source_jar, target_jar)
            log.info("Switched active server.jar to %s", target_jar)
        except OSError as e:
            log.exception("Failed to copy jar")
            raise HTTPException(
                status_code=500, detail=f"Failed to activate version: {e}"
            )
    else:
        log.info("Version %s is already active at %s", version, target_jar)

    # Update config
    try:
        cfg = svc.read_config()
        cfg["mc_version"] = version
        svc.write_config(cfg, backup=True)
    except (OSError, ValueError, YAMLError) as e:
        log.exception("Failed to update config")
        raise HTTPException(
            status_code=500, detail=f"Version switched but config update failed: {e}"
        )

    # Auto-restart the Minecraft Server if it is currently running
    restart_initiated = False
    try:
        from core.lifecycle import ProcessState, get_supervisor

        supervisor = get_supervisor()
        proc = supervisor.get("Minecraft Server")
        if proc is not None and proc.state == ProcessState.RUNNING:
            log.info("Version switched to %s — restarting Minecraft Server", version)
            await supervisor.stop("Minecraft Server")
            await supervisor.start("Minecraft Server")
            restart_initiated = True
    except Exception as e:  # version switch succeeds even if auto-restart fails
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
    file: Annotated[UploadFile, File()],
    name: str = Form(...),
):
    if not file.filename or not file.filename.endswith(".jar"):
        raise HTTPException(status_code=400, detail="Only .jar files are accepted")

    version_name = name.strip() or file.filename.replace(".jar", "")
    if not version_name:
        raise HTTPException(status_code=400, detail="Version name is required")

    # Sanitize version name for filesystem
    version_name = "".join(c for c in version_name if c.isalnum() or c in "._-").strip()
    # ".." survives the character filter and would escape versions_dir
    # when used as a single path component.
    if not version_name or ".." in version_name:
        raise HTTPException(status_code=400, detail="Invalid version name")

    versions_dir = _ensure_versions_dir()
    target_dir = versions_dir / version_name
    target_dir.mkdir(parents=True, exist_ok=True)
    target_jar = target_dir / "server.jar"

    try:
        with target_jar.open("wb") as f:
            while chunk := file.file.read(8192):
                f.write(chunk)
        log.info(
            "Saved custom jar to %s (%s bytes)", target_jar, target_jar.stat().st_size
        )
        _write_meta(target_dir, {"origin": "custom", "originalName": file.filename})
    except OSError as e:
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
    version = version.strip()
    # Same semantic validation as download/switch: only supported PaperMC
    # version identifiers pass.  This rejects path fragments ("..", "\",
    # "/", pre-releases) before the path is ever joined.
    if not _is_supported_version(version):
        raise HTTPException(
            status_code=400,
            detail=f"Version '{version}' is not a valid supported version",
        )

    versions_dir = _get_versions_dir().resolve()
    target_dir = (versions_dir / version).resolve()
    # Defense in depth: the resolved target must stay inside versions/.
    if target_dir != versions_dir and versions_dir not in target_dir.parents:
        raise HTTPException(status_code=400, detail="Invalid version path")

    if not target_dir.exists() or not target_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Version '{version}' not found")

    try:
        shutil.rmtree(target_dir)
        log.info("Removed version directory: %s", target_dir)
    except OSError as e:
        log.exception("Failed to remove version")
        raise HTTPException(status_code=500, detail=f"Failed to remove version: {e}")

    return RemoveResponse(
        status="ok",
        version=version,
        message=f"Version '{version}' removed",
    )
