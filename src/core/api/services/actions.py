#!/usr/bin/env python3
"""ActionsService — parse, validate, and serialize actions.mca.

Provides the bridge between the raw file format and the structured
JSON representation used by the visual editor.
"""

import logging
import re
from pathlib import Path
from typing import Any

from core.paths import get_root_dir
from core.validator import validate_text, Severity

log = logging.getLogger(__name__)

# ── Regex patterns ──────────────────────────────────────────────────────

_RE_OVERLAY_PREFIX = re.compile(r"^@(\w+)>>")
_RE_MULTIPLIER = re.compile(r"\s+x(\d+)\s*$")

# ── Known event trigger names ──────────────────────────────────────────

EVENT_TRIGGERS: set[str] = {
    "follow", "join", "comment", "likes", "like_2", "share",
}

TRIGGER_TYPE_MAP: dict[str, str] = {
    "/": "vanilla",
    "!": "rcon",
    "$": "script",
    "&": "shell",
}


def _detect_prefix(cmd_str: str) -> tuple[str, dict[str, Any]]:
    """Detect command type prefix and return (type, extracted_data)."""
    # Named overlay: @name>>
    m = _RE_OVERLAY_PREFIX.match(cmd_str)
    if m:
        return "named_overlay", {"overlay_name": m.group(1)}

    # Default overlay: >>
    if cmd_str.startswith(">>"):
        return "overlay", {}

    # Single-char prefixes: /, !, $
    prefix = cmd_str[0] if cmd_str else ""
    if prefix in TRIGGER_TYPE_MAP:
        return TRIGGER_TYPE_MAP[prefix], {}

    return "vanilla", {}


def _strip_prefix(cmd_str: str, cmd_type: str, extra: dict[str, Any]) -> str:
    """Remove the type prefix from a command string, returning the body."""
    if cmd_type == "named_overlay":
        name = extra.get("overlay_name", "default")
        prefix = f"@{name}>>"
        if cmd_str.startswith(prefix):
            return cmd_str[len(prefix):]
        return cmd_str
    if cmd_type == "overlay":
        return cmd_str[2:]
    # /, !, $
    return cmd_str[1:]


def _detect_trigger_type(name: str, gifts: list[dict] | None = None) -> str:
    """Categorize a trigger name into a human-readable type.

    Checks against the gift database (by ID, exact name, or normalized name)
    before falling back to Custom.
    """
    if name in EVENT_TRIGGERS:
        return "Event"
    if gifts:
        normalized = name.lower().strip()
        for g in gifts:
            g_name = g.get("name", "").lower().strip()
            if g_name == normalized:
                return "Gift"
            if g_name.replace(" ", "") == normalized.replace(" ", ""):
                return "Gift"
            if str(g.get("id")) == name:
                return "Gift"
    if name.isdigit():
        return "Gift"
    return "Custom"


def _parse_overlay_body(body: str) -> dict[str, Any]:
    """Parse overlay body 'Title|Subtitle|Duration' into fields."""
    parts = body.split("|")
    result: dict[str, Any] = {"title": "", "subtitle": "", "duration": 3}
    if parts:
        result["title"] = parts[0]
    if len(parts) > 1:
        result["subtitle"] = parts[1]
    if len(parts) > 2 and parts[2].strip().isdigit():
        result["duration"] = int(parts[2].strip())
    return result


def _serialize_overlay_body(cmd: dict[str, Any]) -> str:
    """Serialize overlay title/subtitle/duration back to pipe format."""
    parts = [cmd.get("title", "")]
    if cmd.get("subtitle"):
        parts.append(cmd["subtitle"])
    if cmd.get("duration", 3) != 3:
        parts.append(str(cmd["duration"]))
    return "|".join(parts)


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

    # ── Validation ────────────────────────────────────────────────────

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

    # ── Parse (raw → structured) ─────────────────────────────────────

    def parse(self, text: str | None = None, gifts: list[dict] | None = None) -> list[dict[str, Any]]:
        """Parse actions.mca text into a list of trigger dicts.

        Comment rules (strict):
          - ``#`` at column 0 = full-line comment, skipped entirely
          - ``##`` at column 0 = disabled trigger, parsed but marked inactive
          - Inline ``#`` on an active line = inline comment, stripped

        If *gifts* is provided it is used for accurate type detection
        (Gift vs Custom). Each trigger dict::
            {
                "name": str,
                "enabled": bool,
                "type": "Gift" | "Event" | "Custom",
                "commands": [
                    {
                        "type": "vanilla"|"rcon"|"script"|"overlay"|"named_overlay",
                        "command": str,
                        "multiplier": int,
                        "title": str,        # overlay only
                        "subtitle": str,     # overlay only
                        "duration": int,     # overlay only
                        "overlay_name": str, # named_overlay only
                    }
                ]
            }
        """
        if text is None:
            text = self.read_raw()

        triggers: list[dict[str, Any]] = []

        for raw_line in text.splitlines():
            stripped = raw_line.strip()
            if not stripped:
                continue

            # ── Comment / disabled-trigger detection ────────────────
            #
            #   ##  → disabled trigger (parse content after ##)
            #   #   → full-line comment (skip entirely)
            #   neither → active trigger
            #
            if stripped.startswith("##"):
                # Disabled trigger — strip "##", parse normally
                is_disabled = True
                content = stripped[2:].strip()
            elif stripped.startswith("#"):
                # Full-line comment — skip entirely
                continue
            else:
                # Active trigger — strip inline # comment
                is_disabled = False
                content = stripped.split("#", 1)[0].strip()

            if not content or ":" not in content:
                continue

            # Parse trigger name and command part
            trigger_name, commands_str = map(str.strip, content.split(":", 1))
            if not trigger_name or not commands_str:
                continue

            # Strip surrounding single quotes from trigger name
            display_name = trigger_name
            if trigger_name.startswith("'") and trigger_name.endswith("'"):
                trigger_name = trigger_name[1:-1].strip()

            # Parse individual commands
            commands: list[dict[str, Any]] = []
            for raw_cmd in commands_str.split(";"):
                cmd_str = raw_cmd.strip()
                if not cmd_str:
                    continue

                cmd_type, extra = _detect_prefix(cmd_str)
                body = _strip_prefix(cmd_str, cmd_type, extra)

                # Extract multiplier (e.g., "command x3")
                mult_match = _RE_MULTIPLIER.search(body)
                if mult_match:
                    body = body[: mult_match.start()].strip()
                    multiplier = int(mult_match.group(1))
                else:
                    multiplier = 1

                if cmd_type in ("overlay", "named_overlay"):
                    overlay_data = _parse_overlay_body(body)
                    commands.append({
                        "type": cmd_type,
                        "command": body,
                        "multiplier": 1,
                        "title": overlay_data["title"],
                        "subtitle": overlay_data["subtitle"],
                        "duration": overlay_data["duration"],
                        "overlay_name": extra.get("overlay_name", "default"),
                    })
                else:
                    commands.append({
                        "type": cmd_type,
                        "command": body,
                        "multiplier": multiplier,
                        "title": "",
                        "subtitle": "",
                        "duration": 3,
                        "overlay_name": "default",
                    })

            triggers.append({
                "name": display_name,
                "enabled": not is_disabled,
                "type": _detect_trigger_type(trigger_name, gifts),
                "commands": commands,
            })

        return triggers

    # ── Script validation ──────────────────────────────────────────────

    def _get_registered_scripts(self) -> set[str]:
        """Get the set of registered script names from the hook registry."""
        try:
            from core.hook_api import HOOK_ACTIONS
            return set(HOOK_ACTIONS.keys())
        except Exception as e:
            log.warning(f"Failed to get registered scripts: {e}")
            return set()

    def validate_triggers(self, triggers: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Validate trigger configuration and return diagnostics.
        
        Checks:
        - Script commands must reference registered scripts only
        - Overlay actions must not have invalid data
        """
        registered_scripts = self._get_registered_scripts()
        diagnostics: list[dict[str, Any]] = []

        for ti, trigger in enumerate(triggers):
            for ci, cmd in enumerate(trigger.get("commands", [])):
                cmd_type = cmd.get("type", "vanilla")
                
                # Validate script commands
                if cmd_type == "script":
                    script_name = cmd.get("command", "").strip()
                    if not script_name:
                        diagnostics.append({
                            "line": ti,
                            "message": f"Script action has empty script name",
                            "severity": "ERROR",
                            "code": "INVALID_SCRIPT"
                        })
                    elif script_name not in registered_scripts:
                        diagnostics.append({
                            "line": ti,
                            "message": f"Script '{script_name}' is not registered. Available: {', '.join(sorted(registered_scripts)) if registered_scripts else 'none'}",
                            "severity": "WARNING",
                            "code": "UNREGISTERED_SCRIPT"
                        })
                
                # Validate overlay actions
                elif cmd_type in ("overlay", "named_overlay"):
                    title = cmd.get("title", "").strip()
                    if not title:
                        diagnostics.append({
                            "line": ti,
                            "message": f"{cmd_type} action must have a title",
                            "severity": "WARNING",
                            "code": "MISSING_OVERLAY_TITLE"
                        })

        return diagnostics

    # ── Serialize (structured → raw) ─────────────────────────────────

    def serialize(self, triggers: list[dict[str, Any]]) -> str:
        """Serialize a list of trigger dicts back to actions.mca text.

        Disabled triggers are prefixed with ``##``.
        Full-line comments are not re-serialized (the raw tab preserves
        them; the visual tab produces clean output).
        """
        lines: list[str] = []

        for trigger in triggers:
            name = trigger.get("name", "unnamed")
            enabled = trigger.get("enabled", True)
            commands = trigger.get("commands", [])

            # Quote trigger name if it contains spaces
            serialized_name = name
            if " " in name and not name.startswith("'"):
                serialized_name = f"'{name}'"

            # Serialize each command
            cmd_parts: list[str] = []
            for cmd in commands:
                cmd_type = cmd.get("type", "vanilla")
                body = cmd.get("command", "")

                if cmd_type == "overlay":
                    overlay_str = _serialize_overlay_body(cmd)
                    part = f">>{overlay_str}"
                elif cmd_type == "named_overlay":
                    overlay_name = cmd.get("overlay_name", "default")
                    overlay_str = _serialize_overlay_body(cmd)
                    part = f"@{overlay_name}>>{overlay_str}"
                elif cmd_type == "rcon":
                    part = f"!{body}"
                elif cmd_type == "script":
                    part = f"${body}"
                elif cmd_type == "shell":
                    part = f"&{body}"
                else:  # vanilla
                    part = f"/{body}"

                # Append multiplier
                mult = cmd.get("multiplier", 1)
                if mult and mult > 1 and cmd_type not in ("overlay", "named_overlay"):
                    part += f" x{mult}"

                cmd_parts.append(part)

            line = f"{serialized_name}:{' ; '.join(cmd_parts)}"
            if not enabled:
                line = "##" + line
            lines.append(line)

        return "\n".join(lines) + "\n" if lines else ""
