#!/usr/bin/env python3
"""Plugin-local configuration loader, schema parser, and validator.

Each plugin is self-contained and ships its own ``config.yaml`` alongside
its ``plugin.json`` manifest.  The manifest may declare a ``config_schema``
section that drives:

* automatic generation of missing config files (defaults)
* runtime validation
* future GUI auto-rendering

Usage
-----
    from core.plugin_config import load_plugin_config, save_plugin_config
    from pathlib import Path

    plugin_dir = Path(__file__).resolve().parent
    cfg = load_plugin_config(plugin_dir)
"""

from __future__ import annotations

import copy
import json
import logging
import re
from pathlib import Path
from typing import Any, Optional

import yaml

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
#  Nested dict helpers
# ---------------------------------------------------------------------------


def _set_nested(data: dict, key_path: str, value: Any) -> None:
    """Set *value* at a dotted key path, creating intermediate dicts."""
    parts = key_path.split(".")
    for part in parts[:-1]:
        if part not in data or not isinstance(data[part], dict):
            data[part] = {}
        data = data[part]
    data[parts[-1]] = value


def _get_nested(data: dict, key_path: str, default: Any = None) -> Any:
    """Return the value at a dotted key path, or *default* if absent."""
    parts = key_path.split(".")
    for part in parts[:-1]:
        if not isinstance(data, dict):
            return default
        data = data.get(part, {})
    if not isinstance(data, dict):
        return default
    return data.get(parts[-1], default)


def _deep_update(base: dict, overlay: dict) -> None:
    """Recursively merge *overlay* into *base* (in-place).  Existing keys
    in *base* that are dicts are updated rather than replaced."""
    for key, value in overlay.items():
        if isinstance(value, dict) and key in base and isinstance(base[key], dict):
            _deep_update(base[key], value)
        else:
            base[key] = value


# ---------------------------------------------------------------------------
#  Discovery
# ---------------------------------------------------------------------------


def discover_plugins_dir() -> Path:
    """Return the resolved plugins directory (dev or release layout)."""
    from core.paths import get_root_dir

    root = get_root_dir()
    dev_dir = root / "src" / "plugins"
    if dev_dir.is_dir():
        return dev_dir
    rel_dir = root / "plugins"
    if rel_dir.is_dir():
        return rel_dir
    return dev_dir


def load_plugin_manifest(plugin_dir: Path) -> Optional[dict]:
    """Read ``plugin.json`` from the given plugin directory."""
    manifest_path = plugin_dir / "plugin.json"
    if not manifest_path.exists():
        return None
    try:
        with manifest_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        log.warning("Failed to load manifest %s: %s", manifest_path, exc)
        return None


def get_plugin_config_path(plugin_dir: Path) -> Path:
    """Return the expected ``config.yaml`` path inside a plugin directory."""
    return plugin_dir / "config.yaml"


# ---------------------------------------------------------------------------
#  Schema → defaults
# ---------------------------------------------------------------------------


def _generate_defaults_from_fields(fields: list[dict]) -> dict:
    """Walk a list of schema fields and build a nested dict of defaults."""
    result: dict = {}
    for field in fields:
        key = field["key"]
        default = field.get("default")
        ftype = field.get("type", "string")

        if ftype == "array" and "item_schema" in field and default is None:
            item_defaults = _generate_defaults_from_fields(
                field["item_schema"].get("fields", [])
            )
            default = [item_defaults] if item_defaults else []

        if default is not None:
            _set_nested(result, key, copy.deepcopy(default))
    return result


# ---------------------------------------------------------------------------
#  Config I/O
# ---------------------------------------------------------------------------


def load_plugin_config(plugin_dir: Path, apply_defaults: bool = True) -> dict:
    """Load a plugin's local ``config.yaml``.

    If the file does not exist and the manifest declares a
    ``config_schema``, a default config is generated from the schema.
    If *apply_defaults* is ``True`` (the default), any missing keys in
    the existing config are filled with schema defaults.
    """
    manifest = load_plugin_manifest(plugin_dir)
    schema = None
    if manifest:
        schema = manifest.get("config_schema")

    config_path = get_plugin_config_path(plugin_dir)

    if config_path.exists():
        try:
            with config_path.open("r", encoding="utf-8") as f:
                data: dict = yaml.safe_load(f) or {}
        except Exception as exc:
            log.warning("Failed to load plugin config %s: %s", config_path, exc)
            data = {}
    else:
        data = {}
        if schema:
            log.info("Creating default config for plugin: %s", config_path.parent.name)

    if apply_defaults and schema:
        defaults = _generate_defaults_from_fields(schema.get("fields", []))
        merged = copy.deepcopy(defaults)
        _deep_update(merged, data)
        data = merged

    return data


def save_plugin_config(plugin_dir: Path, data: dict) -> None:
    """Write *data* to the plugin's ``config.yaml`` atomically."""
    config_path = get_plugin_config_path(plugin_dir)
    tmp_path = config_path.with_suffix(".yaml.tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(
            data,
            f,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )
    tmp_path.replace(config_path)
    log.debug("Plugin config written: %s", config_path)


# ---------------------------------------------------------------------------
#  Validation
# ---------------------------------------------------------------------------


def _validate_field_value(value: Any, field: dict, path: str) -> list[str]:
    """Validate a single value against its schema field definition."""
    errors: list[str] = []
    if value is None:
        if field.get("required", False):
            errors.append(f"{path} is required")
        return errors

    ftype = field.get("type", "string")

    if ftype == "string":
        if not isinstance(value, str):
            errors.append(f"{path} must be a string, got {type(value).__name__}")

    elif ftype == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            errors.append(f"{path} must be an integer, got {type(value).__name__}")
        else:
            mn = field.get("min")
            mx = field.get("max")
            if mn is not None and value < mn:
                errors.append(f"{path} must be >= {mn}")
            if mx is not None and value > mx:
                errors.append(f"{path} must be <= {mx}")

    elif ftype == "number":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            errors.append(f"{path} must be a number, got {type(value).__name__}")
        else:
            mn = field.get("min")
            mx = field.get("max")
            if mn is not None and value < mn:
                errors.append(f"{path} must be >= {mn}")
            if mx is not None and value > mx:
                errors.append(f"{path} must be <= {mx}")

    elif ftype == "boolean":
        if not isinstance(value, bool):
            errors.append(f"{path} must be a boolean, got {type(value).__name__}")

    elif ftype == "color":
        if not isinstance(value, str) or not re.fullmatch(
            r"#[0-9a-fA-F]{6}", value
        ):
            errors.append(f"{path} must be a hex color like #RRGGBB")

    elif ftype == "select":
        options = field.get("options", [])
        if options and value not in options:
            errors.append(f"{path} must be one of {options}, got {value!r}")

    elif ftype == "array":
        if not isinstance(value, list):
            errors.append(f"{path} must be an array, got {type(value).__name__}")
        else:
            item_schema = field.get("item_schema")
            if item_schema and item_schema.get("type") == "object":
                subfields = item_schema.get("fields", [])
                for i, item in enumerate(value):
                    if isinstance(item, dict):
                        for subfield in subfields:
                            subkey = subfield["key"]
                            subval = item.get(subkey)
                            errors.extend(
                                _validate_field_value(
                                    subval, subfield, f"{path}[{i}].{subkey}"
                                )
                            )

    elif ftype == "object":
        if not isinstance(value, dict):
            errors.append(f"{path} must be an object, got {type(value).__name__}")

    return errors


def validate_plugin_config(data: dict, schema: Optional[dict]) -> list[str]:
    """Validate *data* against the given schema.

    Returns a list of human-readable error strings (empty on success).
    """
    if not schema:
        return []
    errors: list[str] = []
    for field in schema.get("fields", []):
        key = field["key"]
        value = _get_nested(data, key)
        errors.extend(_validate_field_value(value, field, key))
    return errors


# ---------------------------------------------------------------------------
#  Batch loading
# ---------------------------------------------------------------------------


def load_all_plugin_configs() -> dict[str, dict]:
    """Discover all plugins and load their local configs.

    Returns a mapping ``{plugin_name: config_dict}``.
    """
    result: dict[str, dict] = {}
    plugins_dir = discover_plugins_dir()
    if not plugins_dir.is_dir():
        log.warning("Plugins directory not found: %s", plugins_dir)
        return result

    for child in sorted(plugins_dir.iterdir()):
        if not child.is_dir():
            continue
        manifest = load_plugin_manifest(child)
        if not manifest:
            continue
        name = manifest.get("name")
        if not name:
            continue
        try:
            result[name] = load_plugin_config(child)
        except Exception as exc:
            log.warning("Failed to load config for plugin '%s': %s", name, exc)
            result[name] = {}

    return result
