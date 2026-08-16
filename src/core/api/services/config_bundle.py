"""ConfigBundleService — export/import a full configuration bundle.

The bundle is a ZIP archive containing the user's configuration files:

* ``config/config.yaml`` — main configuration
* ``data/actions.mca`` — event actions
* ``data/event_commands.yaml`` — chat command mapping
* ``plugins/<name>/config.yaml`` — one entry per plugin with a config
* ``hooks/<name>/config.yaml`` — one entry per standalone hook with a config
* ``bundle.json`` — manifest (format version, tool version, file list)

Export collects the *active* files (the ``defaults/`` templates are only
shipped as a fallback and are never exported).  Import validates the
archive (traversal-safe, allow-listed names, content validation) and
applies every file with a safety backup via ``BackupManager`` first.
"""

from __future__ import annotations

import io
import json
import logging
import re
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ruamel.yaml.error import YAMLError

import core.paths
from core.api.services.actions import ActionsService
from core.backup import get_backup_manager
from core.diagnostics import Severity
from core.plugin_config import discover_plugins_dir, get_plugin_config_path
from core.validation_framework import validate_config_schema
from core.version import EXPECTED_CONFIG_VERSION, TOOL_VERSION
from core.yaml_utils import create_yaml_rt

log = logging.getLogger(__name__)

BUNDLE_FORMAT_VERSION = 1
BUNDLE_MANIFEST = "bundle.json"

# Bundle-internal names are matched against these allow-listed patterns.
_PLUGIN_RE = re.compile(r"^plugins/([A-Za-z0-9_-]+)/config\.yaml$")
_HOOK_RE = re.compile(r"^hooks/([A-Za-z0-9_-]+)/config\.yaml$")


def _standalone_hooks_dir() -> Path | None:
    """Return the standalone hooks directory (dev or release layout)."""
    root = core.paths.get_root_dir()
    dev_hooks = root / "src" / "hooks"
    if dev_hooks.is_dir():
        return dev_hooks
    rel_hooks = root / "hooks"
    return rel_hooks if rel_hooks.is_dir() else None


class ConfigBundleService:
    """High-level config bundle operations for the API layer."""

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def collect_files(self) -> dict[str, Path]:
        """Map bundle-internal names to their active runtime source files."""
        files: dict[str, Path] = {}

        config_file = core.paths.get_config_file()
        if config_file.exists():
            files["config/config.yaml"] = config_file

        actions_path = ActionsService().actions_path
        if actions_path.exists():
            files["data/actions.mca"] = actions_path

        event_commands = core.paths.get_root_dir() / "data" / "event_commands.yaml"
        if event_commands.exists():
            files["data/event_commands.yaml"] = event_commands

        plugins_dir = discover_plugins_dir()
        if plugins_dir.is_dir():
            for child in sorted(plugins_dir.iterdir()):
                cfg = get_plugin_config_path(child)
                if cfg.is_file():
                    files[f"plugins/{child.name}/config.yaml"] = cfg

        hooks_dir = _standalone_hooks_dir()
        if hooks_dir and hooks_dir.is_dir():
            for child in sorted(hooks_dir.iterdir()):
                cfg = child / "config.yaml"
                if cfg.is_file():
                    files[f"hooks/{child.name}/config.yaml"] = cfg

        return files

    def create_bundle(self) -> bytes:
        """Build the ZIP bundle in memory and return it as bytes."""
        files = self.collect_files()
        manifest = {
            "format_version": BUNDLE_FORMAT_VERSION,
            "tool_version": TOOL_VERSION,
            "config_version": EXPECTED_CONFIG_VERSION,
            "created": datetime.now(UTC).isoformat(timespec="seconds"),
            "files": sorted(files.keys()),
        }
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(BUNDLE_MANIFEST, json.dumps(manifest, indent=2))
            for name, path in sorted(files.items()):
                try:
                    zf.write(path, arcname=name)
                except OSError as exc:
                    log.warning("Skipping %s in bundle: %s", path, exc)
        return buffer.getvalue()

    # ------------------------------------------------------------------
    # Import
    # ------------------------------------------------------------------

    def import_bundle(self, content: bytes) -> dict[str, Any]:
        """Validate *content* and apply it with safety backups.

        Raises ``ValueError`` for invalid bundles (unreadable archive,
        unsupported file names, failing content validation).
        """
        try:
            archive = zipfile.ZipFile(io.BytesIO(content), "r")
        except (zipfile.BadZipFile, OSError) as exc:
            raise ValueError(f"Not a valid config bundle: {exc}") from exc

        with archive:
            entries: dict[str, bytes] = {}
            for info in archive.infolist():
                if info.is_dir():
                    continue
                name = info.filename
                if name == BUNDLE_MANIFEST:
                    continue
                if self._target_for(name) is None:
                    raise ValueError(f"Unsupported file in bundle: {name}")
                if name in entries:
                    raise ValueError(f"Duplicate file in bundle: {name}")
                try:
                    entries[name] = archive.read(name)
                except (zipfile.BadZipFile, OSError) as exc:
                    raise ValueError(f"Cannot read {name}: {exc}") from exc

            if not entries:
                raise ValueError("Bundle contains no configuration files")

            # Validate every file before applying anything.
            for name, data in sorted(entries.items()):
                self._validate_entry(name, data)

            # Apply with a safety snapshot per target.
            applied: list[str] = []
            for name, data in sorted(entries.items()):
                target = self._target_for(name)
                assert target is not None
                target.parent.mkdir(parents=True, exist_ok=True)
                try:
                    get_backup_manager().create_backup(target)
                except OSError as exc:
                    log.warning("Safety backup failed for %s: %s", target, exc)
                self._atomic_write_bytes(target, data)
                applied.append(name)

        return {"applied": applied, "count": len(applied)}

    # ------------------------------------------------------------------
    # Path mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _target_for(name: str) -> Path | None:
        """Map a bundle-internal name to its runtime target path."""
        if name == "config/config.yaml":
            return core.paths.get_config_file()
        if name == "data/actions.mca":
            return ActionsService().actions_path
        if name == "data/event_commands.yaml":
            return core.paths.get_root_dir() / "data" / "event_commands.yaml"

        m = _PLUGIN_RE.fullmatch(name)
        if m:
            return discover_plugins_dir() / m.group(1) / "config.yaml"

        m = _HOOK_RE.fullmatch(name)
        if m:
            hooks_dir = _standalone_hooks_dir()
            if hooks_dir is None:
                return None
            return hooks_dir / m.group(1) / "config.yaml"

        return None

    # ------------------------------------------------------------------
    # Validation & writing
    # ------------------------------------------------------------------

    @staticmethod
    def _load_yaml_text(text: str) -> Any:
        """Parse YAML from a string (round-trip).

        Raises ``ValueError`` on malformed YAML or an empty result.
        """
        try:
            data = create_yaml_rt().load(text)
        except YAMLError as exc:
            raise ValueError(f"invalid YAML: {exc}") from exc
        return data if data is not None else {}

    @staticmethod
    def _validate_entry(name: str, data: bytes) -> None:
        """Reject content that would leave the tool in a broken state."""
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"{name}: not valid UTF-8") from exc

        if name == "config/config.yaml":
            try:
                cfg = ConfigBundleService._load_yaml_text(text)
                validate_config_schema(cfg)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{name}: invalid config: {exc}") from exc
        elif name == "data/actions.mca":
            diags = ActionsService().validate(text)
            errors = [d for d in diags if d.get("severity") == Severity.ERROR.value]
            if errors:
                first = errors[0].get("message", "invalid actions")
                raise ValueError(f"{name}: {first}")
        elif (
            name == "data/event_commands.yaml"
            or _PLUGIN_RE.fullmatch(name)
            or _HOOK_RE.fullmatch(name)
        ):
            try:
                ConfigBundleService._load_yaml_text(text)
            except ValueError as exc:
                raise ValueError(f"{name}: invalid YAML: {exc}") from exc

    @staticmethod
    def _atomic_write_bytes(path: Path, data: bytes) -> None:
        """Write bytes atomically (temp file + replace)."""
        tmp = path.with_name(path.name + ".import.tmp")
        tmp.write_bytes(data)
        tmp.replace(path)
        log.info("Config bundle applied: %s", path)
