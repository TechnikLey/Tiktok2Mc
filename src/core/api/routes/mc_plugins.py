import logging
import re
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi import Path as PathParam
from pydantic import BaseModel

from core.api.services import ApiService
from core.paths import get_servers_dir

log = logging.getLogger(__name__)

router = APIRouter(tags=["MC Plugins"])

_service: ApiService | None = None


def _get_service() -> ApiService:
    global _service
    if _service is None:
        _service = ApiService()
    return _service


def _get_plugins_dir(instance_id: str) -> Path:
    return (get_servers_dir() / instance_id / "plugins").resolve()


def _instance_has_jar(instance_id: str) -> bool:
    return (get_servers_dir() / instance_id / "server.jar").is_file()


def _validate_instance_exists(instance_id: str) -> None:
    if not _instance_has_jar(instance_id):
        raise HTTPException(
            status_code=404,
            detail=f"Instance '{instance_id}' not found or server.jar missing",
        )


def _sanitize_plugin_name(name: str) -> str:
    name = re.sub(r"\.(jar|disabled)$", "", name, flags=re.IGNORECASE)
    return re.sub(r"[^A-Za-z0-9._-]", "", name)


# ── Models ──────────────────────────────────────────────────────────


class McPluginInfo(BaseModel):
    name: str
    filename: str
    enabled: bool


class McPluginsListResponse(BaseModel):
    plugins: list[McPluginInfo]


class McPluginActionResponse(BaseModel):
    status: str
    plugin: str
    enabled: bool
    message: str


class McPluginDeleteResponse(BaseModel):
    status: str
    plugin: str
    message: str


class McPluginUploadResponse(BaseModel):
    status: str
    plugin: str
    filename: str
    message: str


# ── Endpoints ───────────────────────────────────────────────────────


@router.get("/server/{instance_id}/mc-plugins", response_model=McPluginsListResponse)
async def list_mc_plugins(
    instance_id: Annotated[str, PathParam(description="Server instance ID")],
):
    _validate_instance_exists(instance_id)

    plugins_dir = _get_plugins_dir(instance_id)
    if not plugins_dir.is_dir():
        return McPluginsListResponse(plugins=[])

    plugins: list[McPluginInfo] = []

    for entry in sorted(plugins_dir.iterdir()):
        if entry.is_dir():
            continue
        if entry.suffix.lower() == ".disabled":
            name = entry.stem
            if name.lower().endswith(".jar"):
                name = name[:-4]
            plugins.append(
                McPluginInfo(
                    name=name,
                    filename=entry.name,
                    enabled=False,
                )
            )
        elif entry.suffix.lower() == ".jar":
            plugins.append(
                McPluginInfo(
                    name=entry.stem,
                    filename=entry.name,
                    enabled=True,
                )
            )

    return McPluginsListResponse(plugins=plugins)


@router.post(
    "/server/{instance_id}/mc-plugins/{plugin_name}/enable",
    response_model=McPluginActionResponse,
)
async def enable_mc_plugin(
    instance_id: Annotated[str, PathParam(description="Server instance ID")],
    plugin_name: Annotated[str, PathParam(description="Plugin name")],
):
    _validate_instance_exists(instance_id)

    name = _sanitize_plugin_name(plugin_name)
    if not name:
        raise HTTPException(status_code=400, detail="Invalid plugin name")

    plugins_dir = _get_plugins_dir(instance_id)
    disabled_file = plugins_dir / f"{name}.jar.disabled"
    enabled_file = plugins_dir / f"{name}.jar"

    if enabled_file.exists():
        return McPluginActionResponse(
            status="already_enabled",
            plugin=name,
            enabled=True,
            message=f"Plugin '{name}' is already enabled",
        )

    if not disabled_file.exists():
        raise HTTPException(status_code=404, detail=f"Plugin '{name}' not found")

    try:
        disabled_file.rename(enabled_file)
        log.info("[MC-PLUGINS] Enabled '%s' in instance '%s'", name, instance_id)
    except OSError as e:
        log.warning("[MC-PLUGINS] Failed to enable '%s': %s", name, e)
        raise HTTPException(status_code=500, detail=f"Failed to enable plugin: {e}")

    return McPluginActionResponse(
        status="enabled",
        plugin=name,
        enabled=True,
        message=f"Plugin '{name}' enabled. Restart the server for changes to take effect.",
    )


@router.post(
    "/server/{instance_id}/mc-plugins/{plugin_name}/disable",
    response_model=McPluginActionResponse,
)
async def disable_mc_plugin(
    instance_id: Annotated[str, PathParam(description="Server instance ID")],
    plugin_name: Annotated[str, PathParam(description="Plugin name")],
):
    _validate_instance_exists(instance_id)

    name = _sanitize_plugin_name(plugin_name)
    if not name:
        raise HTTPException(status_code=400, detail="Invalid plugin name")

    plugins_dir = _get_plugins_dir(instance_id)
    enabled_file = plugins_dir / f"{name}.jar"
    disabled_file = plugins_dir / f"{name}.jar.disabled"

    if disabled_file.exists():
        return McPluginActionResponse(
            status="already_disabled",
            plugin=name,
            enabled=False,
            message=f"Plugin '{name}' is already disabled",
        )

    if not enabled_file.exists():
        raise HTTPException(status_code=404, detail=f"Plugin '{name}' not found")

    try:
        enabled_file.rename(disabled_file)
        log.info("[MC-PLUGINS] Disabled '%s' in instance '%s'", name, instance_id)
    except OSError as e:
        log.warning("[MC-PLUGINS] Failed to disable '%s': %s", name, e)
        raise HTTPException(status_code=500, detail=f"Failed to disable plugin: {e}")

    return McPluginActionResponse(
        status="disabled",
        plugin=name,
        enabled=False,
        message=f"Plugin '{name}' disabled. Restart the server for changes to take effect.",
    )


@router.delete(
    "/server/{instance_id}/mc-plugins/{plugin_name}",
    response_model=McPluginDeleteResponse,
)
async def delete_mc_plugin(
    instance_id: Annotated[str, PathParam(description="Server instance ID")],
    plugin_name: Annotated[str, PathParam(description="Plugin name")],
):
    _validate_instance_exists(instance_id)

    name = _sanitize_plugin_name(plugin_name)
    if not name:
        raise HTTPException(status_code=400, detail="Invalid plugin name")

    plugins_dir = _get_plugins_dir(instance_id)
    enabled_file = plugins_dir / f"{name}.jar"
    disabled_file = plugins_dir / f"{name}.jar.disabled"

    target = (
        enabled_file
        if enabled_file.exists()
        else disabled_file
        if disabled_file.exists()
        else None
    )

    if target is None:
        raise HTTPException(status_code=404, detail=f"Plugin '{name}' not found")

    try:
        target.unlink()
        log.info("[MC-PLUGINS] Deleted '%s' from instance '%s'", name, instance_id)
    except OSError as e:
        log.warning("[MC-PLUGINS] Failed to delete '%s': %s", name, e)
        raise HTTPException(status_code=500, detail=f"Failed to delete plugin: {e}")

    return McPluginDeleteResponse(
        status="deleted",
        plugin=name,
        message=f"Plugin '{name}' deleted",
    )


@router.post(
    "/server/{instance_id}/mc-plugins/upload",
    response_model=McPluginUploadResponse,
)
async def upload_mc_plugin(
    instance_id: Annotated[str, PathParam(description="Server instance ID")],
    file: Annotated[UploadFile, File(description="Plugin .jar file")],
):
    _validate_instance_exists(instance_id)

    if not file.filename or not file.filename.lower().endswith(".jar"):
        raise HTTPException(status_code=400, detail="Only .jar files are accepted")

    name = _sanitize_plugin_name(file.filename)
    if not name:
        raise HTTPException(status_code=400, detail="Invalid plugin filename")

    plugins_dir = _get_plugins_dir(instance_id)
    plugins_dir.mkdir(parents=True, exist_ok=True)
    target = plugins_dir / f"{name}.jar"

    try:
        with target.open("wb") as f:
            while chunk := await file.read(8192):
                f.write(chunk)
        log.info(
            "[MC-PLUGINS] Uploaded '%s' to instance '%s' (%s bytes)",
            name,
            instance_id,
            target.stat().st_size,
        )
    except OSError as e:
        log.warning("[MC-PLUGINS] Failed to upload '%s': %s", name, e)
        raise HTTPException(status_code=500, detail=f"Failed to save plugin: {e}")
    finally:
        await file.close()

    return McPluginUploadResponse(
        status="uploaded",
        plugin=name,
        filename=target.name,
        message=f"Plugin '{name}' uploaded. Restart the server for changes to take effect.",
    )
