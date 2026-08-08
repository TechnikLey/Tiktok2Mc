"""Unified .mca (actions) parser — single source of truth for parsing, validation, and serialization.

This module replaces the duplicated parsing logic in:
- core.validator.validate_text
- core.api.services.actions.ActionsService.parse/serialize
- src.python.main.generate_datapack (inline parsing)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from core.diagnostics import Diagnostic, Severity, _make_diag

log = logging.getLogger(__name__)

# ── Regex patterns ──────────────────────────────────────────────────────

_RE_OVERLAY_PREFIX = re.compile(r"^@(\w+)>>")
_RE_MULTIPLIER = re.compile(r"\s+x(\d+)\s*$")

# ── Known event trigger names ──────────────────────────────────────────

EVENT_TRIGGERS: set[str] = {
    "follow",
    "join",
    "comment",
    "likes",
    "like_2",
    "share",
}

TRIGGER_TYPE_MAP: dict[str, str] = {
    "/": "vanilla",
    "!": "rcon",
    "$": "script",
    "&": "shell",
}

# ── Comment / disabled-trigger prefixes ──────────────────────────────────

COMMENT_PREFIX = "#"
DISABLED_PREFIX = "##"
INLINE_COMMENT = "#"


# ── Data classes ────────────────────────────────────────────────────────


@dataclass(slots=True)
class ParsedCommand:
    """A single parsed command within a trigger."""

    type: str  # "vanilla" | "rcon" | "script" | "overlay" | "named_overlay" | "shell"
    body: str  # command body without prefix, without multiplier
    multiplier: int = 1
    # Overlay-specific fields
    title: str = ""
    subtitle: str = ""
    duration: int = 3
    overlay_name: str = "default"

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "command": self.body,
            "multiplier": self.multiplier,
            "title": self.title,
            "subtitle": self.subtitle,
            "duration": self.duration,
            "overlay_name": self.overlay_name,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ParsedCommand":
        return cls(
            type=d.get("type", "vanilla"),
            body=d.get("command", ""),
            multiplier=d.get("multiplier", 1),
            title=d.get("title", ""),
            subtitle=d.get("subtitle", ""),
            duration=d.get("duration", 3),
            overlay_name=d.get("overlay_name", "default"),
        )


@dataclass(slots=True)
class ParsedTrigger:
    """A single parsed trigger definition."""

    name: str  # display name (may be quoted)
    raw_name: str  # unquoted trigger name used for matching
    enabled: bool = True
    commands: list[ParsedCommand] = field(default_factory=list)

    def to_dict(self, gifts: list[dict] | None = None) -> dict[str, Any]:
        return {
            "name": self.name,
            "enabled": self.enabled,
            "type": self._detect_type(gifts),
            "commands": [c.to_dict() for c in self.commands],
        }

    def _detect_type(self, gifts: list[dict] | None = None) -> str:
        name = self.raw_name
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


# ── Parsing helpers ────────────────────────────────────────────────────


def _detect_prefix(cmd_str: str) -> tuple[str, dict[str, Any]]:
    """Detect command type prefix and return (type, extracted_data)."""
    m = _RE_OVERLAY_PREFIX.match(cmd_str)
    if m:
        return "named_overlay", {"overlay_name": m.group(1)}
    if cmd_str.startswith(">>"):
        return "overlay", {}
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
            return cmd_str[len(prefix) :]
        return cmd_str
    if cmd_type == "overlay":
        return cmd_str[2:]
    return cmd_str[1:]


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


def _serialize_overlay_body(cmd: ParsedCommand) -> str:
    """Serialize overlay title/subtitle/duration back to pipe format."""
    parts = [cmd.title]
    if cmd.subtitle:
        parts.append(cmd.subtitle)
    if cmd.duration != 3:
        parts.append(str(cmd.duration))
    return "|".join(parts)


# ── Core parsing ───────────────────────────────────────────────────────


@dataclass(slots=True)
class ParseResult:
    """Result of parsing an actions.mca text."""

    triggers: list[ParsedTrigger] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)

    def to_editor_format(self, gifts: list[dict] | None = None) -> list[dict[str, Any]]:
        """Convert to the format used by the visual editor."""
        return [t.to_dict(gifts) for t in self.triggers]


def parse_mca(text: str, *, gifts: list[dict] | None = None) -> ParseResult:
    """Parse actions.mca text into structured triggers + diagnostics.

    Comment rules:
    - ``#`` at column 0 (after leading whitespace) = full-line comment, skipped
    - ``##`` at column 0 = disabled trigger (parsed but marked inactive)
    - Inline ``#`` on an active line = inline comment, stripped
    - Disabled triggers (##) are parsed normally but marked enabled=False
    """
    from core.validator import Diagnostic, Severity, _make_diag  # local import to avoid cycle

    result = ParseResult()
    lines = text.splitlines()
    seen_enabled: set[str] = set()

    for line_number, raw_line in enumerate(lines):
        # ── Determine comment / disabled status ────────────────────
        stripped = raw_line.lstrip()
        is_disabled = stripped.startswith(DISABLED_PREFIX)
        is_full_comment = stripped.startswith(COMMENT_PREFIX) and not is_disabled

        if is_full_comment:
            continue  # skip entirely

        # For disabled triggers, strip the "##" prefix but keep leading whitespace
        if is_disabled:
            lead = raw_line[: len(raw_line) - len(stripped)]
            content = stripped[len(DISABLED_PREFIX) :].lstrip()
        else:
            content = stripped

        # Strip inline comment
        if INLINE_COMMENT in content and not is_disabled:
            content = content.split(INLINE_COMMENT, 1)[0]

        content = content.strip()
        if not content:
            continue

        # ── Validate colon ────────────────────────────────────────
        if ":" not in content:
            result.diagnostics.append(
                _make_diag(
                    line_number,
                    0,
                    len(raw_line),
                    "Missing colon: each line must define a trigger.",
                    Severity.ERROR,
                    "missing_colon",
                )
            )
            continue

        # Split trigger name and command part
        try:
            trigger_raw, commands_str = map(str.strip, content.split(":", 1))
        except ValueError:
            result.diagnostics.append(
                _make_diag(
                    line_number,
                    0,
                    len(content),
                    "Invalid trigger format (expected 'trigger:command').",
                    Severity.ERROR,
                    "invalid_format",
                )
            )
            continue

        if not trigger_raw or not commands_str:
            result.diagnostics.append(
                _make_diag(
                    line_number,
                    0,
                    len(content),
                    "Empty trigger name or command part.",
                    Severity.ERROR,
                    "empty_parts",
                )
            )
            continue

        # Strip surrounding single quotes from trigger name
        display_name = trigger_raw
        raw_name = trigger_raw
        if trigger_raw.startswith("'") and trigger_raw.endswith("'"):
            raw_name = trigger_raw[1:-1].strip()

        # ── Parse individual commands ────────────────────────────
        commands: list[ParsedCommand] = []
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
                overlay_name = extra.get("overlay_name", "default") if cmd_type == "named_overlay" else "default"
                commands.append(
                    ParsedCommand(
                        type=cmd_type,
                        body=body,
                        multiplier=1,  # overlays don't use multiplier
                        title=overlay_data["title"],
                        subtitle=overlay_data["subtitle"],
                        duration=overlay_data["duration"],
                        overlay_name=overlay_name,
                    )
                )
            else:
                commands.append(
                    ParsedCommand(
                        type=cmd_type,
                        body=body,
                        multiplier=multiplier,
                    )
                )

        # ── Duplicate enabled trigger detection ──────────────────
        trigger = ParsedTrigger(
            name=display_name,
            raw_name=raw_name,
            enabled=not is_disabled,
            commands=commands,
        )

        if trigger.enabled:
            key = raw_name.lower()
            if key in seen_enabled:
                result.diagnostics.append(
                    _make_diag(
                        line_number,
                        0,
                        len(trigger_raw),
                        f"Duplicate trigger: '{raw_name}' defined multiple times.",
                        Severity.ERROR,
                        "duplicate_trigger",
                    )
                )
            else:
                seen_enabled.add(key)

        result.triggers.append(trigger)

    return result


# ── Serialization ──────────────────────────────────────────────────────


def serialize_mca(triggers: list[ParsedTrigger]) -> str:
    """Serialize triggers back to actions.mca text.

    Disabled triggers are prefixed with ``##``.
    """
    lines: list[str] = []

    for trigger in triggers:
        name = trigger.name
        enabled = trigger.enabled

        # Quote trigger name if it contains spaces
        serialized_name = name
        if " " in name and not name.startswith("'"):
            serialized_name = f"'{name}'"

        # Serialize each command
        cmd_parts: list[str] = []
        for cmd in trigger.commands:
            if cmd.type == "overlay":
                overlay_str = _serialize_overlay_body(cmd)
                part = f">>{overlay_str}"
            elif cmd.type == "named_overlay":
                overlay_str = _serialize_overlay_body(cmd)
                part = f"@{cmd.overlay_name}>>{overlay_str}"
            elif cmd.type == "rcon":
                part = f"!{cmd.body}"
            elif cmd.type == "script":
                part = f"${cmd.body}"
            elif cmd.type == "shell":
                part = f"&{cmd.body}"
            else:  # vanilla
                part = f"/{cmd.body}"

            # Append multiplier (overlays don't use multiplier)
            mult = cmd.multiplier
            if mult and mult > 1 and cmd.type not in ("overlay", "named_overlay"):
                part += f" x{mult}"

            cmd_parts.append(part)

        line = f"{serialized_name}:{' ; '.join(cmd_parts)}"
        if not enabled:
            line = "##" + line
        lines.append(line)

    return "\n".join(lines) + "\n" if lines else ""