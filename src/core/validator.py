# validator.py
import re
from enum import Enum
from dataclasses import dataclass
from typing import List, Optional, Set

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
    code: Optional[str] = None

# --- Helper functions -------------------------------------------------------
def _make_diag(line, start, end, msg, severity, code=None) -> Diagnostic:
    return Diagnostic(line=line, start_char=start, end_char=end, message=msg, severity=severity, code=code)


def print_diagnostics(diags: List[Diagnostic]) -> None:
    """Clean console output (1-based line numbers)."""
    if not diags:
        print("[VALIDATOR] No errors found.")
        return

    for d in diags:
        lvl = d.severity.value
        ln = d.line + 1
        print(f"[{lvl}] Line {ln}: chars {d.start_char}-{d.end_char} | {d.message} (code={d.code})")


    # --- Validation logic ----------------------------------------------------
def validate_text(text: str) -> List[Diagnostic]:
    diagnostics: List[Diagnostic] = []
    seen_triggers: Set[str] = set()

    lines = text.splitlines()
    for line_number, raw_line in enumerate(lines):
        # 1) Cut off comment part (everything after '#')
        line_no_comment = raw_line.split("#", 1)[0]

        # if comment-only / empty => skip
        if line_no_comment.strip() == "":
            continue

        # base offset: index in raw_line where code-part starts
        base_offset = raw_line.find(line_no_comment)
        if base_offset < 0:
            base_offset = 0

        # A: Check colon
        if ":" not in line_no_comment:
            diagnostics.append(_make_diag(
                line_number, 0, max(1, len(raw_line)),
                "Missing colon: each line must define a trigger.",
                Severity.ERROR, "missing_colon"
            ))
            continue

        colon_index_rel = line_no_comment.index(":")
        colon_index_global = base_offset + colon_index_rel

        # B: no space directly after ':'
        if colon_index_rel + 1 < len(line_no_comment):
            char_after = line_no_comment[colon_index_rel + 1]
            if char_after in (" ", "\t"):
                diagnostics.append(_make_diag(
                    line_number, colon_index_global + 1, colon_index_global + 2,
                    "Formatting error: no space is allowed after the colon.",
                    Severity.ERROR, "no_space_after_colon"
                ))
        else:
            # ":" is the last character -> no content after ':'
            diagnostics.append(_make_diag(
                line_number, colon_index_global, colon_index_global + 1,
                "Syntax error: no content after ':' (no commands).",
                Severity.ERROR, "no_content_after_colon"
            ))
            continue

        # C: trailing colons (e.g. "trigger::" or "trigger:   :")
        if re.search(r":[:\s]*$", line_no_comment):
            last_colon = base_offset + line_no_comment.rindex(":")
            diagnostics.append(_make_diag(
                line_number, last_colon, base_offset + len(line_no_comment),
                "Syntax error: trailing colons at the end of the command.",
                Severity.ERROR, "trailing_colons"
            ))

        # D: unnecessary semicolon at the end (info)
        if re.search(r";\s*$", line_no_comment):
            last_sc = base_offset + line_no_comment.rindex(";")
            diagnostics.append(_make_diag(
                line_number, last_sc, last_sc + 1,
                "Unnecessary semicolon at the end of the line.",
                Severity.INFO, "trailing_semicolon"
            ))

        # E: check bracket balance [] and {}
        square = 0
        curly = 0
        for ch in line_no_comment:
            if ch == "[":
                square += 1
            elif ch == "]":
                square -= 1
            elif ch == "{":
                curly += 1
            elif ch == "}":
                curly -= 1
        if square != 0:
            diagnostics.append(_make_diag(
                line_number, 0, base_offset + len(line_no_comment),
                "Unbalanced square brackets [] (check selectors!).",
                Severity.ERROR, "unbalanced_square"
            ))
        if curly != 0:
            diagnostics.append(_make_diag(
                line_number, 0, base_offset + len(line_no_comment),
                "Unbalanced curly brackets {} (check NBT data!).",
                Severity.ERROR, "unbalanced_curly"
            ))

        # F: trigger validation (name & duplicates)
        trigger_raw = line_no_comment[:colon_index_rel]
        trigger = trigger_raw.strip()
        # compute where trigger starts in global coordinates
        trigger_rel_index = line_no_comment.find(trigger_raw)
        trigger_global_start = base_offset + trigger_rel_index + trigger_raw.find(trigger) if trigger_raw.strip() != "" else base_offset

        if not re.fullmatch(r"[A-Za-z0-9_]+", trigger):
            diagnostics.append(_make_diag(
                line_number, trigger_global_start, trigger_global_start + len(trigger),
                f"Invalid trigger name '{trigger}' (allowed: A-Z, 0-9, _).",
                Severity.ERROR, "invalid_trigger_name"
            ))

        if trigger in seen_triggers:
            diagnostics.append(_make_diag(
                line_number, trigger_global_start, trigger_global_start + len(trigger),
                f"Critical error: trigger '{trigger}' defined multiple times.",
                Severity.ERROR, "duplicate_trigger"
            ))
        seen_triggers.add(trigger)

        # G: parse commands (semicolon-separated)
        commands_part_rel = line_no_comment[colon_index_rel + 1:]
        commands = commands_part_rel.split(";")
        # compute starting search offset in raw_line for commands
        current_offset_global = base_offset + colon_index_rel + 1

        for idx, cmd_raw in enumerate(commands):
            cmd_trim = cmd_raw.strip()
            # find start position in raw_line (best-effort)
            cmd_start_global = raw_line.find(cmd_trim, current_offset_global) if cmd_trim else current_offset_global
            if cmd_start_global == -1:
                cmd_start_global = current_offset_global

            # update offset for next search (approx)
            current_offset_global = cmd_start_global + max(len(cmd_trim), len(cmd_raw)) + 1

            # empty command block (double semicolon)
            if cmd_trim == "":
                if idx < len(commands) - 1:
                    diagnostics.append(_make_diag(
                        line_number, cmd_start_global, cmd_start_global + 1,
                        "Empty command block detected (double semicolon?).",
                        Severity.WARNING, "empty_command_block"
                    ))
                continue

            # Check prefix: '/', '$', '!' or '>>'
            if cmd_trim.startswith(">>"):
                # Overlay command — no further prefix checks needed
                pass
            elif cmd_trim[0] not in ("/", "$", "!"):
                diagnostics.append(_make_diag(
                    line_number, cmd_start_global, cmd_start_global + len(cmd_trim),
                    f"Each command must start with '/', '$', '!' or '>>' (found: '{cmd_trim[0]}').",
                    Severity.ERROR, "invalid_prefix"
                ))

            # '!' may only appear at the beginning (skip for >> overlay commands)
            idx_bang = cmd_trim.find("!")
            if idx_bang > 0 and not cmd_trim.startswith(">>"):
                # position of the bad '!' relative to line
                diagnostics.append(_make_diag(
                    line_number, cmd_start_global + idx_bang, cmd_start_global + idx_bang + 1,
                    "'!' is only allowed at the start of a plugin command",
                    Severity.ERROR, "bang_in_middle"
                ))

            # Check multiplier: " xN" at the end
            mm = re.search(r"\s+x(\d+)\s*$", cmd_trim)
            if mm:
                amount = int(mm.group(1))
                # Warning for very high values (performance)
                if amount > 50 and "# ignore-lag" not in raw_line:
                    x_token = f"x{amount}"
                    token_pos = cmd_start_global + cmd_trim.rfind(x_token)
                    diagnostics.append(_make_diag(
                        line_number, token_pos, token_pos + len(x_token),
                        f"Performance warning: x{amount} is very high.",
                        Severity.WARNING, "high_multi"
                    ))
            else:
                maybe_x = re.search(r"\s+x([^\s]+)\s*$", cmd_trim)
                if maybe_x and not maybe_x.group(1).isdigit():
                    token_str = f"x{maybe_x.group(1)}"
                    token_pos = cmd_start_global + cmd_trim.rfind(token_str)
                    diagnostics.append(_make_diag(
                        line_number, token_pos, token_pos + len(token_str),
                        f"Invalid multiplier '{maybe_x.group(1)}' (use xNumber).",
                        Severity.ERROR, "invalid_multiplier"
                    ))

    return diagnostics


def validate_file(file_path: str, raise_on_error: bool = True) -> List[Diagnostic]:
    """
    Validates a file and returns a list of diagnostics.
    If raise_on_error=True and at least one ERROR exists, ValueError is raised.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as fh:
            text = fh.read()
    except FileNotFoundError:
        raise FileNotFoundError(f"Actions file not found: {file_path}")

    diags = validate_text(text)

    # separate errors/warnings/info
    errors = [d for d in diags if d.severity == Severity.ERROR]
    if errors and raise_on_error:
        # Print for users and raise exception with all messages
        print("[VALIDATOR] Errors found:")
        print_diagnostics(diags)
        raise ValueError("Validation failed: actions file contains errors. See output above.")
    return diags