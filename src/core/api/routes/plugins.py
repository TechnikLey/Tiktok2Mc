"""Plugin registration & management endpoints.

These replace the old file-based ``python.registry.register_plugin()``
flow.  Plugins now register via the API, which persists to its own
JSON store (``data/api_plugin_registry.json``).
"""

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

import core.paths
from core.api.dependency import validate_dependencies
from core.api.models import (
    PluginListResponse,
    PluginRegisterRequest,
    PluginRegisterResponse,
    PluginRegistration,
    PluginUpdateInstallResult,
    PluginUpdateRequest,
    PluginUpdatesInstallResponse,
    PluginUpdatesResponse,
    PluginUpdateStatus,
)
from core.api.plugin_overlay import command_queue
from core.api.registry import get_registry
from core.api.services.plugin_discovery import (
    discover_plugins_from_manifests,
    discover_queries_from_manifests,
)
from core.api.updater import PluginUpdateChecker
from core.base_plugin import SHUTDOWN_COMMAND
from core.runtime_signals import (
    clean_plugin_signals as _clean_plugin_signals,
)
from core.runtime_signals import (
    write_plugin_signal as _write_plugin_signal,
)

log = logging.getLogger(__name__)

_HEALTH_POLL_TIMEOUT = 30.0
# How long disable/restart/unregister wait after delivering the reserved
# ``__shutdown__`` command before the hard stop signal is written, so a
# well-behaved plugin can run on_stop() and flush (bounded — an old plugin
# that ignores the command only delays the stop by this much).
SHUTDOWN_GRACE_SECONDS = 1.0


async def _request_graceful_shutdown(plugin_name: str) -> None:
    """Deliver the reserved ``__shutdown__`` command and give the plugin
    a short grace period to flush before the process is stopped."""
    try:
        command_queue.enqueue(plugin_name, SHUTDOWN_COMMAND)
    except Exception as exc:  # best-effort: the hard signal follows anyway
        log.warning("Failed to enqueue shutdown command for '%s': %s", plugin_name, exc)
        return
    await asyncio.sleep(SHUTDOWN_GRACE_SECONDS)


def _queries_from_manifest(raw: dict) -> list[str]:
    """Extract the sorted ``queries`` declaration from a raw manifest."""
    qs = raw.get("queries")
    if not isinstance(qs, list):
        return []
    return sorted({str(q) for q in qs if q})


router = APIRouter(tags=["Plugins"])


# ── Register ─────────────────────────────────────────────────────────


@router.post(
    "/plugins/register",
    response_model=PluginRegisterResponse,
    status_code=201,
)
async def register_plugin(body: PluginRegisterRequest):
    """Register or update a plugin in the central registry."""
    try:
        registry = get_registry()
        if body.depends_on:
            registered = {p.name: p for p in registry.list()}
            missing = validate_dependencies(body.name, body.depends_on, registered)
            if missing:
                raise HTTPException(
                    status_code=422,
                    detail=f"Plugin '{body.name}' depends on unregistered plugin(s): {', '.join(missing)}",
                )
        data = PluginRegistration(
            name=body.name,
            path=body.path,
            entry_point=body.entry_point,
            display_name=body.display_name,
            version=body.version,
            enabled=body.enabled,
            level=body.level,
            ics=body.ics,
            description=body.description,
            capabilities=body.capabilities,
            depends_on=body.depends_on,
            update_url=body.update_url,
            author=body.author,
            homepage=body.homepage,
            registered_at=None,
            updated_at=None,
            health_status="unknown",
            last_heartbeat=None,
            error="",
            platform="all",
        )
        result = registry.register(data)
        return PluginRegisterResponse(status="registered", plugin=result)
    except HTTPException:
        raise
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:  # any unexpected error becomes an HTTP 500
        log.exception("Failed to register plugin")
        raise HTTPException(status_code=500, detail=str(e))


# ── List ─────────────────────────────────────────────────────────────


@router.get("/plugins", response_model=PluginListResponse)
async def list_plugins():
    """Return every registered plugin, plus filesystem-discovered ones.

    If a plugin.json is broken or missing, the plugin is still listed
    with an ``error`` field explaining the problem.
    """
    try:
        registry = get_registry()
        plugins = registry.list()

        # Check each registered plugin's manifest for errors and the
        # dashboard_ui/bundled/queries declarations (read fresh per request
        # so manifest edits take effect without re-registering).
        for plugin in plugins:
            if plugin.path:
                plugin_dir = (
                    Path(plugin.path).parent
                    if Path(plugin.path).is_file()
                    else Path(plugin.path)
                )
                if not plugin_dir.is_dir():
                    # Stale/missing executable path — fall back to the
                    # conventional <plugins_dir>/<name> location so the
                    # fresh manifest data still shows up.
                    from core.plugin_config import discover_plugins_dir

                    candidate = discover_plugins_dir() / plugin.name
                    if candidate.is_dir():
                        plugin_dir = candidate
                if plugin_dir.is_dir():
                    manifest_path = plugin_dir / "plugin.json"
                    if manifest_path.exists():
                        try:
                            with manifest_path.open("r", encoding="utf-8") as fh:
                                raw = json.load(fh)
                            plugin.dashboard_ui = bool(raw.get("dashboard_ui", False))
                            plugin.bundled = bool(raw.get("bundled", False))
                            plugin.queries = _queries_from_manifest(raw)
                        except (json.JSONDecodeError, OSError) as exc:
                            plugin.error = str(exc)

        # Scan filesystem for unregistered plugins (broken manifests)
        plugins_dir = core.paths.get_root_dir() / "src" / "plugins"
        if not plugins_dir.is_dir():
            plugins_dir = core.paths.get_root_dir() / "plugins"
        if plugins_dir.is_dir():
            for child in sorted(plugins_dir.iterdir()):
                if not child.is_dir():
                    continue
                manifest_file = child / "plugin.json"
                if not manifest_file.is_file():
                    continue
                name = child.name
                if any(p.name == name for p in plugins):
                    continue
                error = ""
                raw: dict = {}
                try:
                    with manifest_file.open("r", encoding="utf-8") as fh:
                        raw = json.load(fh)
                    name = raw.get("name", child.name)
                except (json.JSONDecodeError, OSError) as exc:
                    error = str(exc)
                if any(p.name == name for p in plugins):
                    continue
                from core.api.models import PluginRegistration

                plugins.append(
                    PluginRegistration(
                        name=name,
                        display_name=name,
                        version="0.0.0",
                        error=error,
                        enabled=False,
                        path=str(child),
                        entry_point="",
                        level=4,
                        ics=False,
                        description="",
                        update_url="",
                        author="",
                        homepage="",
                        registered_at=None,
                        updated_at=None,
                        health_status="unknown",
                        last_heartbeat=None,
                        platform="all",
                        dashboard_ui=bool(raw.get("dashboard_ui", False)),
                        bundled=bool(raw.get("bundled", False)),
                        queries=_queries_from_manifest(raw),
                    )
                )

        enabled = sum(1 for p in plugins if p.enabled)
        return PluginListResponse(total=len(plugins), enabled=enabled, plugins=plugins)
    except Exception as e:  # any unexpected error becomes an HTTP 500
        log.exception("Failed to list plugins")
        raise HTTPException(status_code=500, detail=str(e))


# ── Updates ──────────────────────────────────────────────────────────

_updater = PluginUpdateChecker()


@router.get("/plugins/updates", response_model=PluginUpdatesResponse)
async def check_plugin_updates():
    """Check all registered plugins for available updates."""
    try:
        registry = get_registry()
        plugins = [p.model_dump(mode="json") for p in registry.list()]
        results = _updater.check_updates(plugins)
        updates_available = sum(1 for r in results if r.get("update_available"))
        return PluginUpdatesResponse(
            plugins=[PluginUpdateStatus(**r) for r in results],
            total=len(results),
            updates_available=updates_available,
        )
    except Exception as e:  # any unexpected error becomes an HTTP 500
        log.exception("Failed to check plugin updates")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/plugins/updates/install", response_model=PluginUpdatesInstallResponse)
async def install_plugin_updates():
    """Install all pending plugin updates immediately."""
    try:
        registry = get_registry()
        plugins = [p.model_dump(mode="json") for p in registry.list()]
        # Re-check to get latest versions
        results = _updater.check_updates(plugins)

        plugins_dir = core.paths.get_root_dir() / "plugins"
        if not plugins_dir.is_dir():
            plugins_dir = core.paths.get_root_dir() / "src" / "plugins"
        if not plugins_dir.is_dir():
            raise HTTPException(
                status_code=500, detail="Cannot locate plugins directory"
            )

        install_results: list[PluginUpdateInstallResult] = []
        for r in results:
            if not r.get("update_available"):
                continue
            name = r.get("name", "")
            display_name = r.get("display_name", name)
            latest_version = r.get("latest_version", "")
            plugin = next((p for p in plugins if p.get("name") == name), {})
            success = _updater.install_update(plugin, plugins_dir)
            if success:
                # Update registry with new version
                registry.update(name, version=latest_version)
            install_results.append(
                PluginUpdateInstallResult(
                    name=name,
                    display_name=display_name,
                    version=latest_version,
                    success=success,
                    error=None if success else "Installation failed",
                )
            )

        installed = sum(1 for r in install_results if r.success)
        failed = sum(1 for r in install_results if not r.success)
        return PluginUpdatesInstallResponse(
            results=install_results, installed=installed, failed=failed
        )
    except HTTPException:
        raise
    except Exception as e:  # any unexpected error becomes an HTTP 500
        log.exception("Failed to install plugin updates")
        raise HTTPException(status_code=500, detail=str(e))


# ── Discover ──────────────────────────────────────────────────────────


@router.get("/plugins/discover")
async def discover_plugins():
    """Scan filesystem manifests and merge with registry state.

    Returns every plugin found in ``src/plugins/*/plugin.json`` with
    its current ``enabled`` state from the registry.

    This is a **read-only** operation — no plugins are registered
    or loaded as a side effect.
    """
    try:
        plugins_dir = str(core.paths.get_plugins_dir())
        discovered = discover_plugins_from_manifests(plugins_dir)
    except Exception as e:  # any unexpected error becomes an HTTP 500
        log.exception("Failed to discover plugins")
        raise HTTPException(status_code=500, detail=str(e))

    # Merge registry state (read-only query, no side effects)
    try:
        registry = get_registry()
        registry_plugins = {p.name: p for p in registry.list()}
    except Exception:  # discovery still returns manifests if registry is unavailable
        registry_plugins = {}

    for entry in discovered:
        reg = registry_plugins.get(entry["name"])
        entry["enabled"] = reg.enabled if reg is not None else False
        entry.pop("enabled_by_registry", None)

    return {"plugins": discovered}


# ── Query discovery ───────────────────────────────────────────────────


@router.get("/plugins/queries")
async def list_plugin_queries():
    """List every plugin's declared query names discovery.

    Reads the ``queries`` declaration from each ``plugin.json`` on the
    filesystem so callers can find out which queries exist before
    calling ``POST /plugins/{name}/query``. Plugins without a
    ``queries`` declaration are omitted (their queries would 404 at
    call time anyway). Read-only — fresh per request, manifest edits
    take effect immediately.
    """
    try:
        from core.plugin_config import discover_plugins_dir

        plugins_dir = discover_plugins_dir()
        discovered = discover_queries_from_manifests(str(plugins_dir))
    except Exception as e:  # any unexpected error becomes an HTTP 500
        log.exception("Failed to list plugin queries")
        raise HTTPException(status_code=500, detail=str(e))

    # Merge registry state (best-effort, read-only)
    try:
        registry = get_registry()
        registry_plugins = {p.name: p for p in registry.list()}
    except Exception:  # discovery result is still returned without it
        registry_plugins = {}

    for entry in discovered:
        reg = registry_plugins.get(entry["name"])
        entry["enabled"] = reg.enabled if reg is not None else False

    total = sum(len(entry["queries"]) for entry in discovered)
    return {"total": total, "plugins": discovered}


# ── Enable / Disable ─────────────────────────────────────────────────


@router.post("/plugins/{name}/enable", response_model=PluginRegistration)
async def enable_plugin(name: str):
    """Enable a plugin by name and signal runtime start."""
    try:
        registry = get_registry()
        plugin = registry.get(name)
        if plugin is None:
            log.warning("Enable plugin '%s' failed: not found in registry", name)
            raise HTTPException(
                status_code=404, detail=f"Plugin '{name}' not found in registry"
            )
        if plugin.enabled:
            log.info("Plugin '%s' is already enabled — returning current state", name)
            return plugin
        # Check platform compatibility
        plugin_platform = getattr(plugin, "platform", "all") or "all"
        if plugin_platform != "all":
            current_os = "windows" if sys.platform == "win32" else "linux"
            if plugin_platform != current_os:
                raise HTTPException(
                    status_code=422,
                    detail=f"Cannot enable '{name}': plugin is for '{plugin_platform}' only, but running on '{current_os}'",
                )
        # Check dependencies are enabled
        if plugin.depends_on:
            registered = {p.name: p for p in registry.list()}
            for dep_name in plugin.depends_on:
                dep = registered.get(dep_name)
                if dep is None:
                    raise HTTPException(
                        status_code=422,
                        detail=f"Cannot enable '{name}': dependency '{dep_name}' is not registered",
                    )
                if not dep.enabled:
                    raise HTTPException(
                        status_code=422,
                        detail=f"Cannot enable '{name}': dependency '{dep_name}' is not enabled",
                    )
        # Write signal FIRST so start.py sees it immediately
        if not _write_plugin_signal(name, "start"):
            raise HTTPException(
                status_code=500,
                detail=f"Failed to write start signal for plugin '{name}'",
            )
        # Only update registry after signal was written successfully
        # Use "starting" — the first heartbeat will promote to healthy.
        result = registry.update(name, enabled=True, health_status="starting")
        if result is None:
            log.error(
                "Enable plugin '%s': registry.update returned None after get succeeded",
                name,
            )
            raise HTTPException(
                status_code=500, detail=f"Registry inconsistency for plugin '{name}'"
            )
        log.info("Plugin '%s' enabled and start signal written", name)
        return result
    except HTTPException:
        raise
    except Exception as e:  # any unexpected error becomes an HTTP 500
        log.exception("Failed to enable plugin '%s'", name)
        raise HTTPException(
            status_code=500, detail=f"Failed to enable plugin '{name}': {e}"
        )


@router.post("/plugins/{name}/disable", response_model=PluginRegistration)
async def disable_plugin(name: str):
    """Disable a plugin by name and signal runtime stop."""
    try:
        registry = get_registry()
        plugin = registry.get(name)
        if plugin is None:
            log.warning("Disable plugin '%s' failed: not found in registry", name)
            raise HTTPException(
                status_code=404, detail=f"Plugin '{name}' not found in registry"
            )
        if not plugin.enabled:
            log.info("Plugin '%s' is already disabled — returning current state", name)
            return plugin
        # Graceful stop first: deliver __shutdown__ so the plugin can flush,
        # then write the hard signal for start.py.
        await _request_graceful_shutdown(name)
        # Write signal FIRST so start.py sees it immediately
        if not _write_plugin_signal(name, "stop"):
            raise HTTPException(
                status_code=500,
                detail=f"Failed to write stop signal for plugin '{name}'",
            )
        # Only update registry after signal was written successfully
        result = registry.update(name, enabled=False, health_status="unknown")
        if result is None:
            log.error(
                "Disable plugin '%s': registry.update returned None after get succeeded",
                name,
            )
            raise HTTPException(
                status_code=500, detail=f"Registry inconsistency for plugin '{name}'"
            )
        log.info("Plugin '%s' disabled and stop signal written", name)
        return result
    except HTTPException:
        raise
    except Exception as e:  # any unexpected error becomes an HTTP 500
        log.exception("Failed to disable plugin '%s'", name)
        raise HTTPException(
            status_code=500, detail=f"Failed to disable plugin '{name}': {e}"
        )


# ── Get single ───────────────────────────────────────────────────────


@router.get("/plugins/{name}", response_model=PluginRegistration)
async def get_plugin(name: str):
    """Return a single plugin by name."""
    try:
        registry = get_registry()
        plugin = registry.get(name)
        if plugin is None:
            raise HTTPException(status_code=404, detail=f"Plugin '{name}' not found")
        return plugin
    except HTTPException:
        raise
    except Exception as e:  # any unexpected error becomes an HTTP 500
        log.exception("Failed to get plugin")
        raise HTTPException(status_code=500, detail=str(e))


# ── Update ────────────────────────────────────────────────────────────


@router.put("/plugins/{name}", response_model=PluginRegistration)
async def update_plugin(name: str, body: PluginUpdateRequest):
    """Partially update a plugin's properties (e.g. enable/disable, health)."""
    try:
        registry = get_registry()
        # Validate depends_on if being updated
        if body.depends_on is not None:
            registered = {p.name: p for p in registry.list()}
            missing = validate_dependencies(name, body.depends_on, registered)
            if missing:
                raise HTTPException(
                    status_code=422,
                    detail=f"Plugin '{name}' depends on unregistered plugin(s): {', '.join(missing)}",
                )
        kwargs: dict[str, Any] = {
            "enabled": body.enabled,
            "level": body.level,
            "ics": body.ics,
            "path": body.path,
            "version": body.version,
            "description": body.description,
            "entry_point": body.entry_point,
            "display_name": body.display_name,
            "capabilities": body.capabilities,
            "depends_on": body.depends_on,
            "update_url": body.update_url,
            "author": body.author,
            "homepage": body.homepage,
            "health_status": body.health_status,
            "last_heartbeat": body.last_heartbeat,
        }
        # Strip None values so registry.update only touches provided fields
        kwargs = {k: v for k, v in kwargs.items() if v is not None}
        result = registry.update(name, **kwargs)
        if result is None:
            raise HTTPException(status_code=404, detail=f"Plugin '{name}' not found")
        return result
    except HTTPException:
        raise
    except Exception as e:  # any unexpected error becomes an HTTP 500
        log.exception("Failed to update plugin")
        raise HTTPException(status_code=500, detail=str(e))


# ── Restart ──────────────────────────────────────────────────────────


@router.post("/plugins/{name}/restart")
async def restart_plugin(name: str):
    """Restart a plugin process by writing stop/start signals for start.py."""
    try:
        registry = get_registry()
        plugin = registry.get(name)
        if not plugin:
            raise HTTPException(status_code=404, detail=f"Plugin '{name}' not found")

        _clean_plugin_signals(name)
        await _request_graceful_shutdown(name)
        _write_plugin_signal(name, "stop")
        _write_plugin_signal(name, "start")

        log.info("Plugin '%s' restart requested", name)
        return {"status": "restart_requested", "name": name}
    except HTTPException:
        raise
    except Exception as e:  # any unexpected error becomes an HTTP 500
        log.exception("Failed to restart plugin '%s'", name)
        raise HTTPException(status_code=500, detail=str(e))


# ── Unregister ───────────────────────────────────────────────────────


@router.delete("/plugins/{name}")
async def unregister_plugin(name: str):
    """Remove a plugin from the registry, stop its process, and clean up signals."""
    try:
        # Graceful stop first, then the stop signal so start.py terminates
        # the running process if it is still alive after the grace period.
        await _request_graceful_shutdown(name)
        _write_plugin_signal(name, "stop")
        _clean_plugin_signals(name)

        # 2. Remove from registry
        registry = get_registry()
        if not registry.unregister(name):
            raise HTTPException(status_code=404, detail=f"Plugin '{name}' not found")

        log.info("Plugin '%s' unregistered, process stopped, signals cleaned", name)
        return {"status": "unregistered", "name": name}
    except HTTPException:
        raise
    except Exception as e:  # any unexpected error becomes an HTTP 500
        log.exception("Failed to unregister plugin")
        raise HTTPException(status_code=500, detail=str(e))
