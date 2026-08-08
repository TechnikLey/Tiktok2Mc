from __future__ import annotations

import ast
import importlib.util
import json
import sys
import logging
from pathlib import Path
from typing import Optional

from core.hook_api import HookAPI
from core.hook_manifest import (
    load_hook_manifest,
    discover_hooks_dirs,
    read_hook_version,
    HookManifest,
)
from core.hook_registry import get_hook_registry, HookRegistration
from core.plugin_config import load_plugin_config, save_plugin_config
from core.crash_manager import get_crash_manager
from core.error_codes import HOOK_0001, HOOK_0002, HOOK_0003, HOOK_0004, HOOK_0005, HOOK_0007
from ruamel.yaml.error import YAMLError

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Allowed imports for event hook scripts — AST-checked at load time
# ---------------------------------------------------------------------------

ALLOWED_IMPORTS: frozenset[str] = frozenset({
    "time", "random", "logging", "json", "urllib", "requests",
})

ALLOWED_HOOK_MODULES: frozenset[str] = frozenset({
    "core.hook_api", "core.plugin_config",
})


def _check_imports(path: Path) -> list[str]:
    """Parse the hook file with the AST and return disallowed imports."""
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (SyntaxError, OSError):
        return []

    disallowed: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                full_name = alias.name
                if full_name in ALLOWED_HOOK_MODULES:
                    continue
                top = full_name.split(".")[0]
                if top not in ALLOWED_IMPORTS:
                    disallowed.append(full_name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                full_module = node.module
                if full_module in ALLOWED_HOOK_MODULES:
                    continue
                top = full_module.split(".")[0]
                if top not in ALLOWED_IMPORTS:
                    disallowed.append(full_module)
    return disallowed


# ---------------------------------------------------------------------------
# Hook discovery
# ---------------------------------------------------------------------------


def _discover_hook_dirs() -> list[dict]:
    """Scan all hook directories and return metadata for each discovered hook.

    Returns a list of dicts::
        {
            "name": str,
            "version": str,
            "display_name": str,
            "description": str,
            "author": str,
            "capabilities": list[str],
            "plugin": str,
            "update_url": str,
            "source": str,        # filesystem path to hook dir
            "source_type": str,   # "main" or "plugin"
        }
    """
    hooks: list[dict] = []
    seen_names: set[str] = set()

    for parent_dir in discover_hooks_dirs():
        source_type = "main"
        plugin_name = ""
        # Check if this is a plugin-bundled hooks dir
        parts = parent_dir.parts
        for i, part in enumerate(parts):
            if part in ("plugins",):
                if i + 1 < len(parts):
                    plugin_name = parts[i + 1]
                    source_type = "plugin"
                break

        for child in sorted(parent_dir.iterdir()):
            if not child.is_dir():
                continue

            manifest = load_hook_manifest(child)
            error = None
            fallback_name = child.name

            if manifest is None:
                hook_json = child / "hook.json"
                if hook_json.exists():
                    try:
                        with hook_json.open("r", encoding="utf-8") as f:
                            json.load(f)
                    except (json.JSONDecodeError, OSError) as exc:
                        error = str(exc)
                if not error:
                    error = "hook.json is missing or invalid"

                if error:
                    hooks.append({
                        "name": fallback_name,
                        "version": "0.0.0",
                        "display_name": fallback_name,
                        "description": "",
                        "author": "",
                        "capabilities": [],
                        "plugin": plugin_name,
                        "update_url": "",
                        "source": str(child.resolve()),
                        "source_type": source_type,
                        "_manifest": None,
                        "_error": error,
                    })
                    log.debug("[HOOK] Hook '%s' has errors: %s", fallback_name, error)
                continue

            if manifest.name in seen_names:
                log.debug(
                    "[HOOK] Duplicate hook name '%s' in %s — skipping",
                    manifest.name, child,
                )
                continue
            seen_names.add(manifest.name)

            version = read_hook_version(child)
            hooks.append({
                "name": manifest.name,
                "version": version,
                "display_name": manifest.display_name,
                "description": manifest.description,
                "author": manifest.author,
                "capabilities": manifest.capabilities,
                "plugin": plugin_name,
                "update_url": manifest.update_url,
                "source": str(child.resolve()),
                "source_type": source_type,
                "_manifest": manifest,
            })
            log.debug(
                "[HOOK] Discovered hook '%s' v%s in %s",
                manifest.name, version, child,
            )

    return hooks


# ---------------------------------------------------------------------------
# Config loading per hook
# ---------------------------------------------------------------------------


def _ensure_hook_config(hook_dir: Path, manifest: HookManifest) -> dict:
    """Load or create the per-hook ``config.yaml``.

    Uses ``core.plugin_config.load_plugin_config()`` with the hook's
    ``config_schema`` from its manifest to generate defaults and validate.
    """
    config_path = hook_dir / "config.yaml"

    if manifest.config_schema:
        # Create a temporary plugin.json-like structure so we can reuse
        # the config system
        fake_manifest = {"config_schema": manifest.config_schema, "name": manifest.name}
        manifest_path = hook_dir / ".hook_schema.tmp"
        try:
            import json
            manifest_path.write_text(json.dumps(fake_manifest), encoding="utf-8")
            cfg = load_plugin_config(hook_dir, apply_defaults=True)
            return cfg
        except (TypeError, OSError, ValueError, YAMLError) as exc:
            log.warning("[HOOK] Failed to load config for '%s': %s", manifest.name, exc)
        finally:
            if manifest_path.exists():
                manifest_path.unlink()

    # No schema: load raw if exists, return empty otherwise
    if config_path.exists():
        from core.yaml_utils import load_yaml
        try:
            return load_yaml(config_path) or {}
        except (OSError, ValueError, YAMLError) as exc:
            log.warning("[HOOK] Failed to load config.yaml for '%s': %s", manifest.name, exc)
    return {}


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def _load_single_hook(
    api: HookAPI,
    hook_dir: Path,
    manifest: HookManifest,
) -> bool:
    """Load a single hook from its directory.

    Expects ``hook_dir/main.py`` as the entry point.
    Returns ``True`` on success.
    """
    main_py = hook_dir / "main.py"
    if not main_py.exists():
        log.warning("[HOOK] %s: no main.py found — skipping", hook_dir)
        get_crash_manager().report_error(HOOK_0002, detail=f"{manifest.name}: {main_py}")
        return False

    disallowed = _check_imports(main_py)
    if disallowed:
        for name in disallowed:
            log.error(
                "[HOOK] %s uses disallowed import: '%s' — hook skipped.",
                manifest.name, name,
            )
            get_crash_manager().report_error(HOOK_0003, detail=f"{manifest.name}: {name}")
        return False

    module_name = f"hooks.{manifest.name}"
    try:
        if "hooks" not in sys.modules:
            import types
            sys.modules["hooks"] = types.ModuleType("hooks")

        spec = importlib.util.spec_from_file_location(module_name, main_py)
        if spec is None or spec.loader is None:
            log.warning("[HOOK] Could not create spec for: %s", manifest.name)
            get_crash_manager().report_error(HOOK_0004, detail=f"{manifest.name}: spec creation failed")
            return False

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    except SyntaxError as e:
        log.warning("[HOOK] Syntax error in %s: %s", manifest.name, e)
        get_crash_manager().report_exception(HOOK_0004, exc=e, context_info={"hook": manifest.name})
        return False
    except Exception as e:  # noqa: BLE001  # hook module code runs here — must never crash the loader
        log.warning("[HOOK] Failed to load %s: %s", manifest.name, e)
        get_crash_manager().report_exception(HOOK_0004, exc=e, context_info={"hook": manifest.name})
        return False

    if hasattr(module, "register") and callable(module.register):
        try:
            module.register(api)
            log.info("[HOOK] Loaded: %s v%s", manifest.name, manifest.version)
            return True
        except Exception as e:  # noqa: BLE001  # hook code runs here — must never crash the loader
            log.warning("[HOOK] register() failed in %s: %s", manifest.name, e)
            get_crash_manager().report_exception(HOOK_0005, exc=e, context_info={"hook": manifest.name})
            return False
    else:
        log.error("[HOOK] %s/main.py has no register() function — skipped.", hook_dir)
        get_crash_manager().report_error(HOOK_0007, detail=manifest.name)
        return False


def load_event_hooks(
    api: HookAPI,
    hooks_dir: Path | None = None,
    config: dict | None = None,
) -> dict[str, dict]:
    """Load all event hooks from all hook directories.

    This is the main entry point. It:

    1. Discovers hooks in ``hooks/`` and ``plugins/*/hooks/``
    2. Loads per-hook configs
    3. Syncs the persistent hook registry
    4. Loads each enabled hook's ``main.py`` entry point
    5. Returns a mapping ``{hook_name: hook_config}``

    The ``hooks_dir`` parameter is kept for backward compatibility
    (previously the only source). When provided, it is scanned
    alongside the automatic discovery paths.
    """
    discovered = _discover_hook_dirs()
    registry = get_hook_registry()

    # Add legacy hooks_dir if provided and not already covered
    if hooks_dir is not None:
        legacy_dir = str(hooks_dir.resolve())
        already = any(h["source"] == legacy_dir for h in discovered)
        if not already and hooks_dir.exists():
            for child in sorted(hooks_dir.iterdir()):
                if child.is_dir():
                    m = load_hook_manifest(child)
                    error = None
                    if m is None:
                        hook_json = child / "hook.json"
                        if hook_json.exists():
                            try:
                                with hook_json.open("r", encoding="utf-8") as f:
                                    json.load(f)
                            except (json.JSONDecodeError, OSError) as exc:
                                error = str(exc)
                        if not error:
                            error = "hook.json is missing or invalid"
                    if error:
                        if not any(h["name"] == child.name for h in discovered):
                            discovered.append({
                                "name": child.name,
                                "version": "0.0.0",
                                "display_name": child.name,
                                "description": "",
                                "author": "",
                                "capabilities": [],
                                "plugin": "",
                                "update_url": "",
                                "source": str(child.resolve()),
                                "source_type": "main",
                                "_manifest": None,
                                "_error": error,
                            })
                        continue
                    if m:
                        # Already caught by discover_hooks_dirs, but ensure we don't
                        # double-count
                        if not any(h["name"] == m.name for h in discovered):
                            version = read_hook_version(child)
                            discovered.append({
                                "name": m.name,
                                "version": version,
                                "display_name": m.display_name,
                                "description": m.description,
                                "author": m.author,
                                "capabilities": m.capabilities,
                                "plugin": "",
                                "update_url": m.update_url,
                                "source": str(child.resolve()),
                                "source_type": "main",
                                "_manifest": m,
                            })

    # Sync registry: add new hooks, update versions
    hook_infos = []
    for info in discovered:
        hook_infos.append({
            "name": info["name"],
            "version": info["version"],
            "display_name": info["display_name"],
            "description": info["description"],
            "author": info["author"],
            "capabilities": info["capabilities"],
            "plugin": info["plugin"],
            "update_url": info["update_url"],
            "source": info["source"],
            "_error": info.get("_error", ""),
        })

    new_count = registry.sync_from_discovery(hook_infos)
    if new_count:
        log.info("[HOOK] Registered %d new hook(s) in registry", new_count)

    # Load per-hook configs
    hook_configs: dict[str, dict] = {}
    for info in discovered:
        if info.get("_error"):
            continue
        manifest: HookManifest = info["_manifest"]
        hook_dir = Path(info["source"])
        hook_configs[manifest.name] = _ensure_hook_config(hook_dir, manifest)

    # Inject configs into the API so hooks can access them
    api._hook_configs = hook_configs

    # Load each enabled hook
    loaded = 0
    skipped = 0
    for info in discovered:
        if info.get("_error"):
            log.warning("[HOOK] Hook '%s' has errors — skipping: %s", info["name"], info["_error"])
            skipped += 1
            continue
        manifest: HookManifest = info["_manifest"]
        if not registry.is_enabled(manifest.name):
            log.info("[HOOK] Hook '%s' is disabled — skipping", manifest.name)
            skipped += 1
            continue

        hook_dir = Path(info["source"])
        if _load_single_hook(api, hook_dir, manifest):
            loaded += 1
        else:
            skipped += 1

    log.info(
        "[HOOK] Loaded %d hook(s), %d skipped/disabled",
        loaded, skipped,
    )

    # Clean stale registry entries
    active_names = {info["name"] for info in discovered}
    cleaned = registry.clean_stale(active_names)
    if cleaned:
        log.info("[HOOK] Removed %d stale registry entr(ies)", cleaned)

    return hook_configs
