#!/usr/bin/env python3
"""Validator for trigger/command definition files (.mca format).

Provides line-level validation of trigger syntax, bracket balance,
command prefixes, multipliers, and duplicate detection.
"""

import logging
import re
from pathlib import Path

from core.diagnostics import Diagnostic, Severity, _make_diag

log = logging.getLogger(__name__)

__all__ = [
    "COMMAND_PREFIX_CHARS",
    "Diagnostic",
    "Severity",
    "print_diagnostics",
    "validate_file",
    "validate_text",
]


# -- Regex patterns -----------------------------------------------------------

_RE_TRAILING_SEMICOLON = re.compile(r";\s*$")
_RE_OVERLAY_PREFIX = re.compile(r"@(\w+)>>")
_RE_MULTIPLIER = re.compile(r"\s+x(\d+)\s*$")
_RE_INVALID_MULTIPLIER = re.compile(r"\s+x([^\s]+)\s*$")
_RE_DYNAMIC_VANILLA = re.compile(r"\s+!rc\s*$")

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
    "missing_colon": DiagnosticCodeInfo(
        "ERROR", "Missing colon: each line must define a trigger."
    ),
    "space_after_colon": DiagnosticCodeInfo(
        "WARNING",
        "Space after colon is unusual (expected 'trigger:command' without space).",
    ),
    "no_content_after_colon": DiagnosticCodeInfo(
        "ERROR", "No content after ':' (no commands)."
    ),
    "trailing_colons": DiagnosticCodeInfo("ERROR", "Trailing colon at end of command."),
    "trailing_semicolon": DiagnosticCodeInfo(
        "INFO", "Unnecessary semicolon at end of line."
    ),
    "unmatched_close_square": DiagnosticCodeInfo(
        "ERROR", "Unmatched closing square bracket ']'."
    ),
    "unbalanced_square": DiagnosticCodeInfo(
        "ERROR", "Unbalanced opening square bracket '[' (check selectors!)."
    ),
    "unmatched_close_curly": DiagnosticCodeInfo(
        "ERROR", "Unmatched closing curly bracket '}'."
    ),
    "unbalanced_curly": DiagnosticCodeInfo(
        "ERROR", "Unbalanced opening curly bracket '{' (check NBT data!)."
    ),
    "invalid_trigger_name": DiagnosticCodeInfo(
        "ERROR", "Invalid trigger name (allowed: A-Z, a-z, 0-9, _)."
    ),
    "duplicate_trigger": DiagnosticCodeInfo(
        "ERROR", "Duplicate trigger defined multiple times."
    ),
    "duplicate_trigger_disabled": DiagnosticCodeInfo(
        "WARNING",
        "Disabled trigger is already defined as an active trigger; activating it would cause a duplicate trigger error.",
    ),
    "empty_command_block": DiagnosticCodeInfo(
        "WARNING", "Empty command block (double semicolon?)."
    ),
    "invalid_prefix": DiagnosticCodeInfo(
        "ERROR", "Each command must start with '/', '$', '!', '&' or '>>'."
    ),
    "comment_placeholder_wrong_trigger": DiagnosticCodeInfo(
        "ERROR", "'{comment}' is only valid on the 'comment' trigger."
    ),
    "overlay_multiplier": DiagnosticCodeInfo(
        "ERROR", "Multiplier is not allowed on overlay commands (>> or @name>>)."
    ),
    "high_multi": DiagnosticCodeInfo(
        "WARNING", "Performance warning: multiplier is very high (add # ignore-lag)."
    ),
    "invalid_multiplier": DiagnosticCodeInfo(
        "ERROR", "Invalid multiplier (use xNumber)."
    ),
    "user_placeholder_needs_rc": DiagnosticCodeInfo(
        "WARNING",
        "Vanilla command uses {user} but lacks !rc suffix — {user} will NOT be substituted. Add ' !rc' to send via RCON for dynamic substitution.",
    ),
}


# -- Helpers ------------------------------------------------------------------


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


class _ValidationContext:
    """Per-line state passed through the validation helpers.

    Carries the raw line plus the already-extracted ``base_offset`` and
    comment-stripped text so every helper reports diagnostics with the same
    (line, start_char, end_char) coordinates the original single-pass
    implementation produced.
    """

    __slots__ = (
        "base_offset",
        "line_no_comment",
        "line_number",
        "raw_line",
    )

    def __init__(
        self,
        line_number: int,
        raw_line: str,
        line_no_comment: str,
        base_offset: int,
    ) -> None:
        self.line_number = line_number
        self.raw_line = raw_line
        self.line_no_comment = line_no_comment
        self.base_offset = base_offset


def _diag(
    ctx: _ValidationContext, start: int, end: int, code: str, message: str
) -> Diagnostic:
    """Build a Diagnostic using the global coordinate offset."""
    return _make_diag(
        ctx.line_number,
        start,
        end,
        message,
        Severity(DIAGNOSTIC_CODES[code].severity),
        code,
    )


def _validate_colon(ctx: _ValidationContext, diagnostics: list[Diagnostic]) -> int:
    """Validate the ':' separator. Returns the colon index in line_no_comment,
    or -1 to signal the line must be skipped."""
    line = ctx.line_no_comment
    if ":" not in line:
        diagnostics.append(
            _diag(
                ctx,
                0,
                max(1, len(ctx.raw_line)),
                "missing_colon",
                DIAGNOSTIC_CODES["missing_colon"].message,
            )
        )
        return -1
    colon_index_rel = line.index(":")
    colon_index_global = ctx.base_offset + colon_index_rel
    if colon_index_rel + 1 < len(line):
        char_after = line[colon_index_rel + 1]
        if char_after in (" ", "\t"):
            diagnostics.append(
                _diag(
                    ctx,
                    colon_index_global + 1,
                    colon_index_global + 2,
                    "space_after_colon",
                    DIAGNOSTIC_CODES["space_after_colon"].message,
                )
            )
    else:
        diagnostics.append(
            _diag(
                ctx,
                colon_index_global,
                colon_index_global + 1,
                "no_content_after_colon",
                DIAGNOSTIC_CODES["no_content_after_colon"].message,
            )
        )
        return -1
    return colon_index_rel


def _validate_trailing_colons(
    ctx: _ValidationContext, diagnostics: list[Diagnostic]
) -> None:
    line = ctx.line_no_comment
    if line.count(":") > 1 and line.rstrip().endswith(":"):
        last_colon_global = ctx.base_offset + line.rindex(":")
        diagnostics.append(
            _diag(
                ctx,
                last_colon_global,
                ctx.base_offset + len(line),
                "trailing_colons",
                DIAGNOSTIC_CODES["trailing_colons"].message,
            )
        )


def _validate_trailing_semicolon(
    ctx: _ValidationContext, diagnostics: list[Diagnostic]
) -> None:
    line = ctx.line_no_comment
    if _RE_TRAILING_SEMICOLON.search(line):
        last_sc_global = ctx.base_offset + line.rindex(";")
        diagnostics.append(
            _diag(
                ctx,
                last_sc_global,
                last_sc_global + 1,
                "trailing_semicolon",
                DIAGNOSTIC_CODES["trailing_semicolon"].message,
            )
        )


def _validate_brackets(ctx: _ValidationContext, diagnostics: list[Diagnostic]) -> None:
    """Check square/curly bracket balance, skipping quoted strings."""
    line = ctx.line_no_comment
    square = 0
    curly = 0
    in_single_quote = False
    in_double_quote = False
    i = 0

    while i < len(line):
        ch = line[i]
        if ch == "\\" and i + 1 < len(line):
            i += 2
            continue
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
                    diagnostics.append(
                        _diag(
                            ctx,
                            ctx.base_offset + i,
                            ctx.base_offset + i + 1,
                            "unmatched_close_square",
                            DIAGNOSTIC_CODES["unmatched_close_square"].message,
                        )
                    )
                    square = 0
            elif ch == "{":
                curly += 1
            elif ch == "}":
                curly -= 1
                if curly < 0:
                    diagnostics.append(
                        _diag(
                            ctx,
                            ctx.base_offset + i,
                            ctx.base_offset + i + 1,
                            "unmatched_close_curly",
                            DIAGNOSTIC_CODES["unmatched_close_curly"].message,
                        )
                    )
                    curly = 0
        i += 1

    if square > 0:
        diagnostics.append(
            _diag(
                ctx,
                0,
                ctx.base_offset + len(line),
                "unbalanced_square",
                DIAGNOSTIC_CODES["unbalanced_square"].message,
            )
        )
    if curly > 0:
        diagnostics.append(
            _diag(
                ctx,
                0,
                ctx.base_offset + len(line),
                "unbalanced_curly",
                DIAGNOSTIC_CODES["unbalanced_curly"].message,
            )
        )


def _validate_trigger_name(
    ctx: _ValidationContext,
    diagnostics: list[Diagnostic],
    seen_triggers: set[str],
    seen_disabled_triggers: set[str],
    colon_index_rel: int,
    is_disabled: bool,
) -> tuple[str, str, bool]:
    """Validate the trigger name and duplicate-state handling.

    Returns ``(trigger_raw, trigger, is_quoted)`` — the caller advances the
    seen-sets, matching the original ordering (name check first, then dup).
    """
    line = ctx.line_no_comment
    trigger_raw = line[:colon_index_rel]
    trigger = trigger_raw.strip()
    leading_whitespace = len(trigger_raw) - len(trigger_raw.lstrip())
    trigger_global_start = ctx.base_offset + leading_whitespace

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
        diagnostics.append(
            _diag(
                ctx,
                trigger_global_start,
                trigger_global_start + len(trigger),
                "invalid_trigger_name",
                msg,
            )
        )

    if is_disabled:
        if trigger in seen_triggers:
            diagnostics.append(
                _diag(
                    ctx,
                    trigger_global_start,
                    trigger_global_start + len(trigger),
                    "duplicate_trigger_disabled",
                    f"Disabled trigger '{trigger}' is already defined as an "
                    "active trigger. Activating it would cause a duplicate "
                    "trigger error.",
                )
            )
        seen_disabled_triggers.add(trigger)
    else:
        if trigger in seen_triggers:
            diagnostics.append(
                _diag(
                    ctx,
                    trigger_global_start,
                    trigger_global_start + len(trigger),
                    "duplicate_trigger",
                    f"Duplicate trigger: '{trigger}' defined multiple times.",
                )
            )
        elif trigger in seen_disabled_triggers:
            diagnostics.append(
                _diag(
                    ctx,
                    trigger_global_start,
                    trigger_global_start + len(trigger),
                    "duplicate_trigger_disabled",
                    f"Trigger '{trigger}' is also defined as a disabled "
                    "trigger (##). Activating the disabled line would cause a "
                    "duplicate trigger error.",
                )
            )
        seen_triggers.add(trigger)

    return trigger_raw, trigger, is_quoted


def _validate_command(
    ctx: _ValidationContext,
    diagnostics: list[Diagnostic],
    cmd_trim: str,
    cmd_start_global: int,
    trigger: str,
) -> None:
    """Validate a single command: prefix, overlay rules, {comment}/{user}, multipler."""
    is_overlay = (
        cmd_trim.startswith(">>") or _RE_OVERLAY_PREFIX.match(cmd_trim) is not None
    )

    if is_overlay:
        if "{comment}" in cmd_trim and trigger.lower() != "comment":
            ph_pos = cmd_start_global + cmd_trim.find("{comment}")
            diagnostics.append(
                _diag(
                    ctx,
                    ph_pos,
                    ph_pos + len("{comment}"),
                    "comment_placeholder_wrong_trigger",
                    DIAGNOSTIC_CODES["comment_placeholder_wrong_trigger"].message,
                )
            )

        mm_overlay = _RE_MULTIPLIER.search(cmd_trim)
        if mm_overlay:
            token = f"x{mm_overlay.group(1)}"
            token_pos = cmd_start_global + cmd_trim.rfind(token)
            diagnostics.append(
                _diag(
                    ctx,
                    token_pos,
                    token_pos + len(token),
                    "overlay_multiplier",
                    DIAGNOSTIC_CODES["overlay_multiplier"].message,
                )
            )

    elif cmd_trim[0] not in COMMAND_PREFIX_CHARS:
        diagnostics.append(
            _diag(
                ctx,
                cmd_start_global,
                cmd_start_global + len(cmd_trim),
                "invalid_prefix",
                f"Each command must start with '/', '$', '!', '&' or '>>' "
                f"(found: '{cmd_trim[0]}').",
            )
        )

    # Vanilla {user} without !rc warning
    if cmd_trim.startswith("/"):
        has_dynamic_vanilla = _RE_DYNAMIC_VANILLA.search(cmd_trim) is not None
        if "{user}" in cmd_trim and not has_dynamic_vanilla:
            user_pos = cmd_start_global + cmd_trim.find("{user}")
            diagnostics.append(
                _diag(
                    ctx,
                    user_pos,
                    user_pos + len("{user}"),
                    "user_placeholder_needs_rc",
                    DIAGNOSTIC_CODES["user_placeholder_needs_rc"].message,
                )
            )

    # Multiplier validation
    mm = _RE_MULTIPLIER.search(cmd_trim)
    if mm:
        amount = int(mm.group(1))
        if amount > HIGH_MULTI_THRESHOLD and "# ignore-lag" not in ctx.raw_line:
            x_token = f"x{amount}"
            token_pos = cmd_start_global + cmd_trim.rfind(x_token)
            diagnostics.append(
                _diag(
                    ctx,
                    token_pos,
                    token_pos + len(x_token),
                    "high_multi",
                    DIAGNOSTIC_CODES["high_multi"].message,
                )
            )
    else:
        maybe_x = _RE_INVALID_MULTIPLIER.search(cmd_trim)
        if maybe_x and not maybe_x.group(1).isdigit():
            token_str = f"x{maybe_x.group(1)}"
            token_pos = cmd_start_global + cmd_trim.rfind(token_str)
            diagnostics.append(
                _diag(
                    ctx,
                    token_pos,
                    token_pos + len(token_str),
                    "invalid_multiplier",
                    DIAGNOSTIC_CODES["invalid_multiplier"].message,
                )
            )


def _validate_commands_section(
    ctx: _ValidationContext,
    diagnostics: list[Diagnostic],
    colon_index_rel: int,
    trigger: str,
) -> None:
    """Split the command section on ';' and validate each command."""
    line = ctx.line_no_comment
    commands_part_rel = line[colon_index_rel + 1 :]
    commands = commands_part_rel.split(";")
    current_offset_global = ctx.base_offset + colon_index_rel + 1

    for idx, cmd_raw in enumerate(commands):
        cmd_trim = cmd_raw.strip()
        if cmd_trim:
            cmd_start_global = ctx.raw_line.find(cmd_trim, current_offset_global)
            if cmd_start_global == -1:
                cmd_start_global = current_offset_global
        else:
            cmd_start_global = current_offset_global

        advance_by = max(len(cmd_trim), len(cmd_raw))
        current_offset_global = cmd_start_global + advance_by + 1

        if cmd_trim == "":
            if idx < len(commands) - 1:
                diagnostics.append(
                    _diag(
                        ctx,
                        cmd_start_global,
                        cmd_start_global + 1,
                        "empty_command_block",
                        DIAGNOSTIC_CODES["empty_command_block"].message,
                    )
                )
            continue

        _validate_command(ctx, diagnostics, cmd_trim, cmd_start_global, trigger)


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
        #   ##  → disabled trigger (kept as a template; it is OFF and
        #         must NOT count toward duplicate detection)
        #   #   → full-line comment (skip entirely)
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

        ctx = _ValidationContext(line_number, raw_line, line_no_comment, base_offset)

        # A. Missing colon / B. space after / no content after ':'
        colon_index_rel = _validate_colon(ctx, diagnostics)
        if colon_index_rel < 0:
            continue

        ctx2 = ctx  # colon now known valid
        _validate_trailing_colons(ctx2, diagnostics)
        _validate_trailing_semicolon(ctx2, diagnostics)
        _validate_brackets(ctx2, diagnostics)
        trigger_raw, trigger, _is_quoted = _validate_trigger_name(
            ctx2,
            diagnostics,
            seen_triggers,
            seen_disabled_triggers,
            colon_index_rel,
            is_disabled,
        )
        del trigger_raw  # retained for symmetry/documentation
        _validate_commands_section(ctx2, diagnostics, colon_index_rel, trigger)

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
            "Validation failed: actions file contains errors. See output above."
        )

    return diags
