#!/usr/bin/env python3
"""Validator for trigger/command definition files (.mca format).

Provides line-level validation of trigger syntax, bracket balance,
command prefixes, multipliers, and duplicate detection.
"""

import logging
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

log = logging.getLogger(__name__)

__all__ = [
    "COMMAND_PREFIX_CHARS",
    "Diagnostic",
    "Severity",
    "print_diagnostics",
    "validate_file",
    "validate_text",
]


class Severity(Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


@dataclass
class Diagnostic:
    line: int
    start_char: int
    end_char: int
    message: str
    severity: Severity
    code: str | None = None


# -- Regex patterns -----------------------------------------------------------

_RE_TRAILING_SEMICOLON = re.compile(r";\s*$")
_RE_OVERLAY_PREFIX = re.compile(r"@(\w+)>>")
_RE_MULTIPLIER = re.compile(r"\s+x(\d+)\s*$")
_RE_INVALID_MULTIPLIER = re.compile(r"\s+x([^\s]+)\s*$")

# -- Thresholds for validation -----------------------------------------------

HIGH_MULTI_THRESHOLD: int = 50

# Single-character command prefixes (the "first char" after the trigger colon).
# These are the standard Minecraft-mode prefixes; overlay (>>, @name>>) is
# handled as a separate branch in prefix validation.
COMMAND_PREFIX_CHARS: tuple[str, ...] = ("/", "!", "$", "&")

# -- Diagnostic code registry (single source of truth for all diagnostic codes)

class DiagnosticCodeInfo:
    """Metadata for a single diagnostic code."""
    __slots__ = ("message", "severity")

    def __init__(self, severity: str, message: str) -> None:
        self.severity = severity
        self.message = message

DIAGNOSTIC_CODES: dict[str, DiagnosticCodeInfo] = {
    "missing_colon": DiagnosticCodeInfo("ERROR", "Missing colon: each line must define a trigger."),
    "space_after_colon": DiagnosticCodeInfo("WARNING", "Space after colon is unusual (expected 'trigger:command' without space)."),
    "no_content_after_colon": DiagnosticCodeInfo("ERROR", "No content after ':' (no commands)."),
    "trailing_colons": DiagnosticCodeInfo("ERROR", "Trailing colon at end of command."),
    "trailing_semicolon": DiagnosticCodeInfo("INFO", "Unnecessary semicolon at end of line."),
    "unmatched_close_square": DiagnosticCodeInfo("ERROR", "Unmatched closing square bracket ']'."),
    "unbalanced_square": DiagnosticCodeInfo("ERROR", "Unbalanced opening square bracket '[' (check selectors!)."),
    "unmatched_close_curly": DiagnosticCodeInfo("ERROR", "Unmatched closing curly bracket '}'."),
    "unbalanced_curly": DiagnosticCodeInfo("ERROR", "Unbalanced opening curly bracket '{' (check NBT data!)."),
    "invalid_trigger_name": DiagnosticCodeInfo("ERROR", "Invalid trigger name (allowed: A-Z, a-z, 0-9, _)."),
    "duplicate_trigger": DiagnosticCodeInfo("ERROR", "Duplicate trigger defined multiple times."),
    "duplicate_trigger_disabled": DiagnosticCodeInfo("WARNING", "Disabled trigger is already defined as an active trigger; activating it would cause a duplicate trigger error."),
    "empty_command_block": DiagnosticCodeInfo("WARNING", "Empty command block (double semicolon?)."),
    "invalid_prefix": DiagnosticCodeInfo("ERROR", "Each command must start with '/', '$', '!', '&' or '>>'."),
    "comment_placeholder_wrong_trigger": DiagnosticCodeInfo("ERROR", "'{comment}' is only valid on the 'comment' trigger."),
    "overlay_multiplier": DiagnosticCodeInfo("ERROR", "Multiplier is not allowed on overlay commands (>> or @name>>)."),
    "high_multi": DiagnosticCodeInfo("WARNING", "Performance warning: multiplier is very high (add # ignore-lag)."),
    "invalid_multiplier": DiagnosticCodeInfo("ERROR", "Invalid multiplier (use xNumber)."),
}


# -- Helpers ------------------------------------------------------------------


def _make_diag(
    line: int,
    start_char: int,
    end_char: int,
    msg: str,
    severity: Severity,
    code: str | None = None,
) -> Diagnostic:
    return Diagnostic(
        line=line,
        start_char=start_char,
        end_char=end_char,
        message=msg,
        severity=severity,
        code=code,
    )


# -- Output -------------------------------------------------------------------


def print_diagnostics(diags: list[Diagnostic]) -> None:
    """Log all diagnostics in a human-readable format (1-based line numbers)."""
    if not diags:
        log.info("[VALIDATOR] No errors found.")
        return

    for d in diags:
        level = d.severity.value
        line_num = d.line + 1
        log.info(
            "[%s] Line %d: chars %d-%d | %s (code=%s)",
            level,
            line_num,
            d.start_char,
            d.end_char,
            d.message,
            d.code,
        )


# -- Core validation ----------------------------------------------------------


def validate_text(text: str) -> list[Diagnostic]:
    """Validate trigger/command definition text and return diagnostics.

    Args:
        text: Raw text content of a trigger definition file.

    Returns:
        A list of Diagnostic objects (empty if no issues found).
    """

    diagnostics: list[Diagnostic] = []
    seen_triggers: set[str] = set()
    seen_disabled_triggers: set[str] = set()

    lines = text.splitlines()
    for line_number, raw_line in enumerate(lines):

        # ── Comment / disabled-trigger detection ────────────────────
        #
        #   ##  → disabled trigger (kept as a template; it is OFF and
        #         must NOT count toward duplicate detection)
        #   #   → full-line comment (skip entirely)
        #
        stripped = raw_line.strip()
        is_disabled = stripped.startswith("##")
        if is_disabled:
            # Disabled trigger — rewrite raw_line without the ##
            # prefix so the existing validation logic works normally.
            lead = raw_line[: len(raw_line) - len(raw_line.lstrip())]
            raw_line = lead + raw_line[len(lead) + 2 :]
        elif stripped.startswith("#"):
            # Full-line comment — skip
            continue
        # else: active trigger — fall through

        # Strip everything after the first '#' (inline comments).
        line_no_comment = raw_line.split("#", 1)[0]

        # Skip empty / comment-only lines.
        if line_no_comment.strip() == "":
            continue

        # Determine where the code part starts in the raw line.
        base_offset = raw_line.find(line_no_comment)
        base_offset = max(base_offset, 0)

        # ------------------------------------------------------------------
        # A. Missing colon
        # ------------------------------------------------------------------
        if ":" not in line_no_comment:
            diagnostics.append(_make_diag(
                line_number,
                0,
                max(1, len(raw_line)),
                "Missing colon: each line must define a trigger.",
                Severity.ERROR,
                "missing_colon",
            ))
            continue

        colon_index_rel = line_no_comment.index(":")
        colon_index_global = base_offset + colon_index_rel

        # ------------------------------------------------------------------
        # B. Space directly after the colon
        # ------------------------------------------------------------------
        if colon_index_rel + 1 < len(line_no_comment):
            char_after = line_no_comment[colon_index_rel + 1]
            if char_after in (" ", "\t"):
                diagnostics.append(_make_diag(
                    line_number,
                    colon_index_global + 1,
                    colon_index_global + 2,
                    "Space after colon is unusual "
                    "(expected 'trigger:command' without space).",
                    Severity.WARNING,
                    "space_after_colon",
                ))
        else:
            diagnostics.append(_make_diag(
                line_number,
                colon_index_global,
                colon_index_global + 1,
                "No content after ':' (no commands).",
                Severity.ERROR,
                "no_content_after_colon",
            ))
            continue

        # ------------------------------------------------------------------
        # C. Trailing colons  (e.g. "trigger::" or "trigger:cmd:")
        # ------------------------------------------------------------------
        colon_count = line_no_comment.count(":")
        if colon_count > 1 and line_no_comment.rstrip().endswith(":"):
            last_colon_global = base_offset + line_no_comment.rindex(":")
            diagnostics.append(_make_diag(
                line_number,
                last_colon_global,
                base_offset + len(line_no_comment),
                "Trailing colon at end of command.",
                Severity.ERROR,
                "trailing_colons",
            ))

        # ------------------------------------------------------------------
        # D. Trailing semicolon  (info-level)
        # ------------------------------------------------------------------
        if _RE_TRAILING_SEMICOLON.search(line_no_comment):
            last_sc_global = base_offset + line_no_comment.rindex(";")
            diagnostics.append(_make_diag(
                line_number,
                last_sc_global,
                last_sc_global + 1,
                "Unnecessary semicolon at end of line.",
                Severity.INFO,
                "trailing_semicolon",
            ))

        # ------------------------------------------------------------------
        # E. Bracket balance  (skip over quoted strings)
        # ------------------------------------------------------------------
        square = 0
        curly = 0
        in_single_quote = False
        in_double_quote = False
        i = 0

        while i < len(line_no_comment):
            ch = line_no_comment[i]

            # Skip escaped character (e.g. \' or \")
            if ch == "\\" and i + 1 < len(line_no_comment):
                i += 2
                continue

            # Toggle quote state.
            if ch == "'" and not in_double_quote:
                in_single_quote = not in_single_quote
            elif ch == '"' and not in_single_quote:
                in_double_quote = not in_double_quote
            elif not in_single_quote and not in_double_quote:
                if ch == "[":
                    square += 1
                elif ch == "]":
                    square -= 1
                    if square < 0:
                        diagnostics.append(_make_diag(
                            line_number,
                            base_offset + i,
                            base_offset + i + 1,
                            "Unmatched closing square bracket ']'.",
                            Severity.ERROR,
                            "unmatched_close_square",
                        ))
                        square = 0
                elif ch == "{":
                    curly += 1
                elif ch == "}":
                    curly -= 1
                    if curly < 0:
                        diagnostics.append(_make_diag(
                            line_number,
                            base_offset + i,
                            base_offset + i + 1,
                            "Unmatched closing curly bracket '}'.",
                            Severity.ERROR,
                            "unmatched_close_curly",
                        ))
                        curly = 0
            i += 1

        if square > 0:
            diagnostics.append(_make_diag(
                line_number,
                0,
                base_offset + len(line_no_comment),
                "Unbalanced opening square bracket '[' (check selectors!).",
                Severity.ERROR,
                "unbalanced_square",
            ))
        if curly > 0:
            diagnostics.append(_make_diag(
                line_number,
                0,
                base_offset + len(line_no_comment),
                "Unbalanced opening curly bracket '{' (check NBT data!).",
                Severity.ERROR,
                "unbalanced_curly",
            ))

        # ------------------------------------------------------------------
        # F. Trigger name validation & duplicate detection
        # ------------------------------------------------------------------
        trigger_raw = line_no_comment[:colon_index_rel]
        trigger = trigger_raw.strip()

        # Compute where the stripped trigger starts in global coordinates.
        leading_whitespace = len(trigger_raw) - len(trigger_raw.lstrip())
        trigger_global_start = base_offset + leading_whitespace

        is_quoted = trigger.startswith("'") and trigger.endswith("'")

        if is_quoted:
            valid = re.fullmatch(r"'[A-Za-z0-9_ ]+'", trigger)
        else:
            valid = re.fullmatch(r"[A-Za-z0-9_]+", trigger)

        if not valid:
            if is_quoted:
                msg = (
                    f"Invalid quoted trigger {trigger!r} "
                    "(allowed: A-Z, a-z, 0-9, _, space, inside single quotes)."
                )
            else:
                msg = (
                    f"Invalid trigger name '{trigger}' "
                    "(allowed: A-Z, a-z, 0-9, _). "
                    "For spaces, wrap the trigger in single quotes."
                )
            diagnostics.append(_make_diag(
                line_number,
                trigger_global_start,
                trigger_global_start + len(trigger),
                msg,
                Severity.ERROR,
                "invalid_trigger_name",
            ))

        if is_disabled:
            # A disabled (##) trigger never counts as a duplicate, but warn if
            # it collides with an existing active trigger (activating it would
            # produce a duplicate trigger error).
            if trigger in seen_triggers:
                diagnostics.append(_make_diag(
                    line_number,
                    trigger_global_start,
                    trigger_global_start + len(trigger),
                    f"Disabled trigger '{trigger}' is already defined as an "
                    "active trigger. Activating it would cause a duplicate "
                    "trigger error.",
                    Severity.WARNING,
                    "duplicate_trigger_disabled",
                ))
            seen_disabled_triggers.add(trigger)
        else:
            if trigger in seen_triggers:
                diagnostics.append(_make_diag(
                    line_number,
                    trigger_global_start,
                    trigger_global_start + len(trigger),
                    f"Duplicate trigger: '{trigger}' defined multiple times.",
                    Severity.ERROR,
                    "duplicate_trigger",
                ))
            elif trigger in seen_disabled_triggers:
                diagnostics.append(_make_diag(
                    line_number,
                    trigger_global_start,
                    trigger_global_start + len(trigger),
                    f"Trigger '{trigger}' is also defined as a disabled "
                    "trigger (##). Activating the disabled line would cause a "
                    "duplicate trigger error.",
                    Severity.WARNING,
                    "duplicate_trigger_disabled",
                ))
            seen_triggers.add(trigger)

        # ------------------------------------------------------------------
        # G. Command parsing (semicolon-separated)
        # ------------------------------------------------------------------
        commands_part_rel = line_no_comment[colon_index_rel + 1:]
        commands = commands_part_rel.split(";")
        current_offset_global = base_offset + colon_index_rel + 1

        for idx, cmd_raw in enumerate(commands):
            cmd_trim = cmd_raw.strip()

            # Best-effort: find where this trimmed command starts in raw_line.
            if cmd_trim:
                cmd_start_global = raw_line.find(cmd_trim, current_offset_global)
                if cmd_start_global == -1:
                    cmd_start_global = current_offset_global
            else:
                cmd_start_global = current_offset_global

            # Advance past this command (approximate, used for next find).
            advance_by = max(len(cmd_trim), len(cmd_raw))
            current_offset_global = cmd_start_global + advance_by + 1

            # Empty command block (double semicolon).
            if cmd_trim == "":
                if idx < len(commands) - 1:
                    diagnostics.append(_make_diag(
                        line_number,
                        cmd_start_global,
                        cmd_start_global + 1,
                        "Empty command block (double semicolon?).",
                        Severity.WARNING,
                        "empty_command_block",
                    ))
                continue

            # --- Prefix validation ---
            is_overlay = (
                cmd_trim.startswith(">>")
                or _RE_OVERLAY_PREFIX.match(cmd_trim) is not None
            )

            if is_overlay:
                # '{comment}' placeholder outside the 'comment' trigger.
                if "{comment}" in cmd_trim and trigger.lower() != "comment":
                    ph_pos = cmd_start_global + cmd_trim.find("{comment}")
                    diagnostics.append(_make_diag(
                        line_number,
                        ph_pos,
                        ph_pos + len("{comment}"),
                        "'{comment}' is only resolved for the 'comment' trigger."
                        " It will not be replaced for other triggers.",
                        Severity.ERROR,
                        "comment_placeholder_wrong_trigger",
                    ))

                # Multiplier is not allowed on overlay commands.
                mm_overlay = _RE_MULTIPLIER.search(cmd_trim)
                if mm_overlay:
                    token = f"x{mm_overlay.group(1)}"
                    token_pos = cmd_start_global + cmd_trim.rfind(token)
                    diagnostics.append(_make_diag(
                        line_number,
                        token_pos,
                        token_pos + len(token),
                        "Multiplier is not allowed on overlay commands "
                        "(>> or @name>>).",
                        Severity.ERROR,
                        "overlay_multiplier",
                    ))

            elif cmd_trim[0] not in COMMAND_PREFIX_CHARS:
                diagnostics.append(_make_diag(
                    line_number,
                    cmd_start_global,
                    cmd_start_global + len(cmd_trim),
                    f"Each command must start with '/', '$', '!', '&' or '>>' "
                    f"(found: '{cmd_trim[0]}').",
                    Severity.ERROR,
                    "invalid_prefix",
                ))

            # --- Multiplier validation ---
            mm = _RE_MULTIPLIER.search(cmd_trim)
            if mm:
                amount = int(mm.group(1))
                if amount > HIGH_MULTI_THRESHOLD and "# ignore-lag" not in raw_line:
                    x_token = f"x{amount}"
                    token_pos = cmd_start_global + cmd_trim.rfind(x_token)
                    diagnostics.append(_make_diag(
                        line_number,
                        token_pos,
                        token_pos + len(x_token),
                        f"Performance warning: x{amount} is very high.",
                        Severity.WARNING,
                        "high_multi",
                    ))
            else:
                maybe_x = _RE_INVALID_MULTIPLIER.search(cmd_trim)
                if maybe_x and not maybe_x.group(1).isdigit():
                    token_str = f"x{maybe_x.group(1)}"
                    token_pos = cmd_start_global + cmd_trim.rfind(token_str)
                    diagnostics.append(_make_diag(
                        line_number,
                        token_pos,
                        token_pos + len(token_str),
                        f"Invalid multiplier '{maybe_x.group(1)}' (use xNumber).",
                        Severity.ERROR,
                        "invalid_multiplier",
                    ))

    return diagnostics


# -- File-level validation ----------------------------------------------------


def validate_file(
    file_path: str | Path,
    raise_on_error: bool = True,
) -> list[Diagnostic]:
    """Read and validate a trigger/command file.

    Args:
        file_path: Path to the file.
        raise_on_error:
            If True and at least one ERROR-level diagnostic exists, raise
            ValueError with a summary.

    Returns:
        List of Diagnostic objects.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If ``raise_on_error`` is True and errors are found.
    """
    path = Path(file_path)

    if not path.is_file():
        raise FileNotFoundError(f"Actions file not found: {file_path}")

    text = path.read_text(encoding="utf-8")
    diags = validate_text(text)

    errors = [d for d in diags if d.severity == Severity.ERROR]
    if errors and raise_on_error:
        log.info("[VALIDATOR] Errors found:")
        print_diagnostics(diags)
        raise ValueError(
            "Validation failed: actions file contains errors. "
            "See output above."
        )

    return diags
