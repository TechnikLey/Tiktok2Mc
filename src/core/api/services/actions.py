#!/usr/bin/env python3
"""ActionsService — parse, validate, and serialize actions.mca.

Provides the bridge between the raw file format and the structured
JSON representation used by the visual editor.
"""

import logging
from pathlib import Path
from typing import Any

from core.mca_parser import (
    TRIGGER_TYPE_MAP,  # noqa: F401
    ParsedCommand,
    ParsedTrigger,
    _detect_prefix,  # noqa: F401
    _strip_prefix,  # noqa: F401
    parse_mca,
    serialize_mca,
)
from core.paths import get_root_dir
from core.validator import validate_text

log = logging.getLogger(__name__)


class ActionsService:
    """Read, write, parse, and serialize actions.mca."""

    def __init__(self) -> None:
        self._actions_path: Path | None = None

    # ── File path resolution ──────────────────────────────────────────

    @property
    def actions_path(self) -> Path:
        if self._actions_path is None:
            self._actions_path = self._resolve_path()
        return self._actions_path

    @staticmethod
    def _resolve_path() -> Path:
        root = get_root_dir()

        # Try active data file first
        data_path = root / "data" / "actions.mca"
        if data_path.exists():
            return data_path.resolve()

        # Fall back to defaults template
        defaults_path = root / "defaults" / "actions.mca"
        if defaults_path.exists():
            return defaults_path.resolve()

        # Neither exists — return data path for creation on save
        return (root / "data" / "actions.mca").resolve()

    @property
    def file_exists(self) -> bool:
        return self.actions_path.exists()

    # ── Raw file I/O ──────────────────────────────────────────────────

    def read_raw(self) -> str:
        """Read the raw text of actions.mca."""
        if not self.file_exists:
            return ""
        return self.actions_path.read_text(encoding="utf-8")

    def write_raw(self, text: str, backup: bool = True) -> None:
        """Write raw text to actions.mca, with optional backup."""
        path = self.actions_path
        path.parent.mkdir(parents=True, exist_ok=True)

        if backup and path.exists():
            from core.backup import get_backup_manager

            mgr = get_backup_manager()
            mgr.create_backup(path, category="actions")

        # Atomic write via temp file
        tmp = path.with_suffix(".mca.tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)
        log.info("Actions written: %s", path)

    # ── Validation ─────────────────────────────────────────────────────

    def validate(self, text: str | None = None) -> list[dict[str, Any]]:
        """Validate actions text and return diagnostics as dicts."""
        if text is None:
            text = self.read_raw()
        diags = validate_text(text)
        return [
            {
                "line": d.line,
                "start_char": d.start_char,
                "end_char": d.end_char,
                "message": d.message,
                "severity": d.severity.value,
                "code": d.code,
            }
            for d in diags
        ]

    # ── Parse (raw → structured) ──────────────────────────────────────

    def parse(
        self, text: str | None = None, gifts: list[dict] | None = None
    ) -> list[dict[str, Any]]:
        """Parse actions.mca text into a list of trigger dicts.

        Delegates to the unified parser in core.mca_parser.
        """
        if text is None:
            text = self.read_raw()

        result = parse_mca(text, gifts=gifts)
        return result.to_editor_format(gifts)

    # ── Script/Overlay validation ──────────────────────────────────────

    def _get_registered_scripts(self) -> set[str]:
        """Get the set of registered script names from the hook registry."""
        try:
            from core.hook_api import HOOK_ACTIONS

            return set(HOOK_ACTIONS.keys())
        except (
            Exception
        ) as e:  # script validation must not fail because hooks are unavailable
            log.warning(f"Failed to get registered scripts: {e}")
            return set()

    def validate_triggers(self, triggers: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Validate trigger configuration and return diagnostics.

        Checks:
        - Script commands must reference registered scripts only
        - Overlay actions must not have invalid data
        - Duplicate enabled triggers
        """
        registered_scripts = self._get_registered_scripts()
        diagnostics: list[dict[str, Any]] = []

        # Check for duplicate enabled trigger names (case-insensitive)
        seen: dict[str, int] = {}
        for ti, trigger in enumerate(triggers):
            if not trigger.get("enabled", True):
                continue
            name = str(trigger.get("name", "")).strip().lower()
            if not name:
                continue
            if name in seen:
                diagnostics.append(
                    {
                        "line": ti,
                        "message": f"Duplicate trigger: '{trigger.get('name', '')}' defined multiple times.",
                        "severity": "ERROR",
                        "code": "DUPLICATE_TRIGGER",
                    }
                )
            else:
                seen[name] = ti

        for ti, trigger in enumerate(triggers):
            for ci, cmd in enumerate(trigger.get("commands", [])):
                cmd_type = cmd.get("type", "vanilla")

                # Validate script commands
                if cmd_type == "script":
                    script_name = cmd.get("command", "").strip()
                    if not script_name:
                        diagnostics.append(
                            {
                                "line": ti,
                                "message": "Script action has empty script name",
                                "severity": "ERROR",
                                "code": "INVALID_SCRIPT",
                            }
                        )
                    elif script_name not in registered_scripts:
                        diagnostics.append(
                            {
                                "line": ti,
                                "message": f"Script '{script_name}' is not registered. Available: {', '.join(sorted(registered_scripts)) if registered_scripts else 'none'}",
                                "severity": "WARNING",
                                "code": "UNREGISTERED_SCRIPT",
                            }
                        )

                # Validate overlay actions
                elif cmd_type in ("overlay", "named_overlay"):
                    title = cmd.get("title", "").strip()
                    if not title:
                        diagnostics.append(
                            {
                                "line": ti,
                                "message": f"{cmd_type} action must have a title",
                                "severity": "WARNING",
                                "code": "MISSING_OVERLAY_TITLE",
                            }
                        )

                # Validate vanilla commands: warn if {user} used without !rc
                elif cmd_type == "vanilla":
                    body = cmd.get("command", "")
                    dynamic = cmd.get("dynamic_vanilla", False)
                    if "{user}" in body and not dynamic:
                        diagnostics.append(
                            {
                                "line": ti,
                                "message": "Vanilla command uses {user} but lacks !rc suffix — {user} will NOT be substituted. Add ' !rc' to send via RCON for dynamic substitution.",
                                "severity": "WARNING",
                                "code": "USER_PLACEHOLDER_NEEDS_RC",
                            }
                        )

        return diagnostics

    # ── Serialize (structured → raw) ──────────────────────────────────

    def serialize(self, triggers: list[dict[str, Any]]) -> str:
        """Serialize a list of trigger dicts back to actions.mca text.

        Delegates to the unified serializer in core.mca_parser.
        """
        # Convert editor format to ParsedTrigger objects
        parsed_triggers: list[ParsedTrigger] = []
        for t in triggers:
            name = t.get("name", "unnamed")
            enabled = t.get("enabled", True)
            # raw_name = unquoted name used for matching
            raw_name = name
            if name.startswith("'") and name.endswith("'"):
                raw_name = name[1:-1].strip()
            commands = []
            for cmd in t.get("commands", []):
                commands.append(ParsedCommand.from_dict(cmd))
            parsed_triggers.append(
                ParsedTrigger(
                    name=name, raw_name=raw_name, enabled=enabled, commands=commands
                )
            )
        return serialize_mca(parsed_triggers)
