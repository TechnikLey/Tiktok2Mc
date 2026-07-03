#!/usr/bin/env python3
"""Generate a shared MCA language specification JSON from the Python implementation.

This script introspects the Python source files that define the MCA language
(validator.py, actions.py) and emits a machine-readable JSON spec that can be
consumed by the VS Code language server (Node.js), test frameworks, and other
tooling.

Usage:
    python tools/generate_mca_spec.py [--output path/to/mca-spec.json]

The Python implementation remains the single source of truth.
Whenever the MCA language is updated, run this script to regenerate the spec.
"""

import re
import json
import sys
import os
from pathlib import Path
from typing import Any


def _find_project_root() -> Path:
    """Walk up from this script to find the repo root (contains .git or build.py)."""
    current = Path(__file__).resolve().parent
    for _ in range(10):
        if (current / ".git").exists() or (current / "build.py").exists():
            return current
        current = current.parent
    return Path.cwd()


def _extract_set_from_source(filepath: Path, var_name: str) -> list[str]:
    """Extract a set literal assigned to *var_name* from a Python source file."""
    src = filepath.read_text(encoding="utf-8")
    # Match: VAR_NAME: set[str] = {"a", "b", ...}
    pat = re.compile(
        rf"{re.escape(var_name)}\s*:\s*set\[str\]\s*=\s*" r"\{(.*?)\}",
        re.DOTALL,
    )
    m = pat.search(src)
    if not m:
        # Try without type annotation
        pat2 = re.compile(
            rf"{re.escape(var_name)}\s*=\s*" r"\{(.*?)\}", re.DOTALL
        )
        m = pat2.search(src)
    if m:
        content = m.group(1)
        items = re.findall(r"\"([^\"]+)\"", content)
        return items
    return []


def _extract_dict_from_source(filepath: Path, var_name: str) -> dict[str, Any]:
    """Extract a dict literal assigned to *var_name* from a Python source file."""
    src = filepath.read_text(encoding="utf-8")
    # Match: VAR_NAME: dict[str, str] = { ... }
    # This is simplified; works for flat string→string dicts
    pat = re.compile(
        rf"{re.escape(var_name)}\s*:\s*dict\[str,\s*str\]\s*=\s*" r"\{(.*?)\}",
        re.DOTALL,
    )
    m = pat.search(src)
    if not m:
        pat2 = re.compile(
            rf"{re.escape(var_name)}\s*=\s*" r"\{(.*?)\}", re.DOTALL
        )
        m = pat2.search(src)
    if m:
        content = m.group(1)
        pairs = re.findall(r'"(.)":\s*"([^"]+)"', content)
        return dict(pairs)
    return {}


def _extract_regex_from_source(filepath: Path, var_name: str) -> str | None:
    """Extract a compiled regex pattern string assigned to *var_name*."""
    src = filepath.read_text(encoding="utf-8")
    pat = re.compile(
        rf"{re.escape(var_name)}\s*=\s*re\.compile\(r\"([^\"]+)\"\)"
    )
    m = pat.search(src)
    if m:
        return m.group(1)
    # Try raw single-quote strings
    pat2 = re.compile(
        rf"{re.escape(var_name)}\s*=\s*re\.compile\(r\'([^\']+)\'\)"
    )
    m2 = pat2.search(src)
    if m2:
        return m2.group(1)
    return None


def _extract_doc_for_prefix(prefix: str) -> str:
    """Return documentation for a command prefix."""
    docs = {
        "/": "Minecraft command executed via datapack .mcfunction files. "
             "The command body (after /) is written to a .mcfunction file "
             "and invoked via /function namespace:triggername.",
        "!": "RCON-only command sent directly to the Minecraft server "
             "via the RCON protocol. Not written to the datapack.",
        "$": "Hook script action. The name after $ is looked up in the "
             "HOOK_ACTIONS registry and the registered Python handler "
             "is called. Built-in: $random.",
        "&": "Shell command executed on the host PC via subprocess. "
             "{user} is NOT replaced in shell commands — they receive "
             "the raw body from the MCA file.",
        ">>": "Overlay text. Syntax: >>Title|Subtitle|Duration. "
              "Parts are pipe-separated. Only Title is required. "
              "Duration defaults to 3 seconds if omitted or non-numeric. "
              "{user} and {comment} are replaced.",
    }
    return docs.get(prefix, "")


def generate_spec(project_root: Path) -> dict[str, Any]:
    """Generate the complete MCA language specification."""
    validator_py = project_root / "src" / "core" / "validator.py"
    actions_py = project_root / "src" / "core" / "api" / "services" / "actions.py"

    # -- Extract event triggers --
    event_triggers = _extract_set_from_source(actions_py, "EVENT_TRIGGERS")

    # -- Extract prefix type map --
    prefix_map = _extract_dict_from_source(actions_py, "TRIGGER_TYPE_MAP")

    # -- Extract regex patterns from validator.py --
    patterns = {
        "trailing_semicolon": _extract_regex_from_source(validator_py, "_RE_TRAILING_SEMICOLON"),
        "overlay_prefix": _extract_regex_from_source(validator_py, "_RE_OVERLAY_PREFIX"),
        "multiplier": _extract_regex_from_source(validator_py, "_RE_MULTIPLIER"),
        "invalid_multiplier": _extract_regex_from_source(validator_py, "_RE_INVALID_MULTIPLIER"),
    }

    # -- Extract overlay prefix from actions.py too --
    actions_overlay = _extract_regex_from_source(actions_py, "_RE_OVERLAY_PREFIX")
    if actions_overlay and not patterns.get("overlay_prefix"):
        patterns["overlay_prefix"] = actions_overlay

    # -- Build command prefix metadata --
    command_prefixes = {}
    for ch, type_name in sorted(prefix_map.items()):
        label_map = {
            "vanilla": "Vanilla Minecraft",
            "rcon": "RCON",
            "script": "Script",
            "shell": "Shell",
        }
        command_prefixes[ch] = {
            "type": type_name,
            "label": label_map.get(type_name, type_name.title()),
            "doc": _extract_doc_for_prefix(ch),
        }
    # Add overlay separately (it's not in TRIGGER_TYPE_MAP)
    command_prefixes[">>"] = {
        "type": "overlay",
        "label": "Overlay",
        "doc": _extract_doc_for_prefix(">>"),
    }

    # -- Build validation rules metadata --
    validation_rules = {
        "high_multi_threshold": 50,
        "allow_comment_placeholder_on": ["comment"],
        "valid_unquoted_trigger": "^[A-Za-z0-9_]+$",
        "valid_quoted_trigger": "^'[A-Za-z0-9_ ]+'$",
        "valid_prefix_chars": ["/", "!", "$", "&"],
        "disabled_prefix": "##",
        "comment_prefix": "#",
        "inline_comment_char": "#",
        "command_separator": ";",
        "trigger_colon": ":",
        "multiplier_prefix": "x",
    }

    # -- Build diagnostic metadata from validator.py source --
    diagnostic_codes = [
        {
            "code": "missing_colon",
            "severity": "ERROR",
            "message": "Missing colon: each line must define a trigger.",
        },
        {
            "code": "space_after_colon",
            "severity": "WARNING",
            "message": "Space after colon is unusual (expected 'trigger:command' without space).",
        },
        {
            "code": "no_content_after_colon",
            "severity": "ERROR",
            "message": "No content after ':' (no commands).",
        },
        {
            "code": "trailing_colons",
            "severity": "ERROR",
            "message": "Trailing colon at end of command.",
        },
        {
            "code": "trailing_semicolon",
            "severity": "INFO",
            "message": "Unnecessary semicolon at end of line.",
        },
        {
            "code": "unmatched_close_square",
            "severity": "ERROR",
            "message": "Unmatched closing square bracket ']'.",
        },
        {
            "code": "unbalanced_square",
            "severity": "ERROR",
            "message": "Unbalanced opening square bracket '[' (check selectors!).",
        },
        {
            "code": "unmatched_close_curly",
            "severity": "ERROR",
            "message": "Unmatched closing curly bracket '}'.",
        },
        {
            "code": "unbalanced_curly",
            "severity": "ERROR",
            "message": "Unbalanced opening curly bracket '{' (check NBT data!).",
        },
        {
            "code": "invalid_trigger_name",
            "severity": "ERROR",
            "message": "Invalid trigger name (allowed: A-Z, a-z, 0-9, _).",
        },
        {
            "code": "duplicate_trigger",
            "severity": "ERROR",
            "message": "Duplicate trigger defined multiple times.",
        },
        {
            "code": "empty_command_block",
            "severity": "WARNING",
            "message": "Empty command block (double semicolon?).",
        },
        {
            "code": "invalid_prefix",
            "severity": "ERROR",
            "message": "Each command must start with '/', '$', '!', '&' or '>>'.",
        },
        {
            "code": "comment_placeholder_wrong_trigger",
            "severity": "ERROR",
            "message": "'{comment}' is only valid on the 'comment' trigger.",
        },
        {
            "code": "overlay_multiplier",
            "severity": "ERROR",
            "message": "Multiplier is not allowed on overlay commands (>> or @name>>).",
        },
        {
            "code": "high_multi",
            "severity": "WARNING",
            "message": "Performance warning: multiplier is very high (add # ignore-lag).",
        },
        {
            "code": "invalid_multiplier",
            "severity": "ERROR",
            "message": "Invalid multiplier (use xNumber).",
        },
    ]

    # -- Placeholder metadata --
    placeholders = [
        {
            "name": "{user}",
            "triggers": ["all"],
            "doc": "Replaced with the triggering user's display name. "
                   "Available on all triggers.",
        },
        {
            "name": "{comment}",
            "triggers": ["comment"],
            "doc": "Replaced with comment text. "
                   "Only works on the 'comment' trigger. "
                   "Using it elsewhere produces a validation error.",
        },
    ]

    # -- Event trigger metadata --
    event_trigger_docs = [
        {
            "name": "follow",
            "doc": "Fires when someone follows the stream.",
        },
        {
            "name": "join",
            "doc": "Fires when someone joins the stream.",
        },
        {
            "name": "comment",
            "doc": "Fires when someone sends a chat comment. "
                   "This is the only trigger that supports the {comment} placeholder.",
        },
        {
            "name": "likes",
            "doc": "Fires every N likes (configurable in config.yaml). "
                   "Default interval is 100 likes.",
        },
        {
            "name": "like_2",
            "doc": "Fires at a bigger milestone (default: 100_000 likes).",
        },
        {
            "name": "share",
            "doc": "Fires when someone shares the stream.",
        },
    ]

    spec = {
        "_comment": "AUTO-GENERATED by tools/generate_mca_spec.py. DO NOT EDIT.",
        "version": "1.0",
        "generated_by": "tools/generate_mca_spec.py",
        "generated_from": [
            "src/core/validator.py",
            "src/core/api/services/actions.py",
        ],
        "event_triggers": event_triggers,
        "event_trigger_docs": event_trigger_docs,
        "command_prefixes": command_prefixes,
        "patterns": {k: v for k, v in patterns.items() if v is not None},
        "validation_rules": validation_rules,
        "diagnostic_codes": diagnostic_codes,
        "placeholders": placeholders,
    }

    return spec


def main():
    project_root = _find_project_root()
    default_output = project_root / "mca-language-server" / "mca-spec.json"

    parser = __import__("argparse").ArgumentParser(
        description="Generate MCA language specification JSON from Python sources"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(default_output),
        help=f"Output path (default: {default_output})",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check if generated spec matches existing file (exit 1 if not)",
    )
    args = parser.parse_args()

    spec = generate_spec(project_root)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    json_bytes = json.dumps(spec, indent=2, ensure_ascii=False) + "\n"

    if args.check:
        if output_path.exists():
            existing = output_path.read_text(encoding="utf-8")
            if existing == json_bytes:
                print(f"OK: {output_path} is up to date.")
                return
            print(
                f"MISMATCH: {output_path} differs from generated spec.\n"
                f"Run `python tools/generate_mca_spec.py` to regenerate.",
                file=sys.stderr,
            )
            sys.exit(1)
        else:
            print(f"MISSING: {output_path} does not exist.", file=sys.stderr)
            sys.exit(1)
    else:
        output_path.write_text(json_bytes, encoding="utf-8")
        print(f"Generated: {output_path}")
        print(f"  event_triggers:      {len(spec['event_triggers'])}")
        print(f"  command_prefixes:    {len(spec['command_prefixes'])}")
        print(f"  diagnostic_codes:    {len(spec['diagnostic_codes'])}")
        print(f"  placeholders:        {len(spec['placeholders'])}")
        print(f"  patterns:            {len(spec['patterns'])}")


if __name__ == "__main__":
    main()
