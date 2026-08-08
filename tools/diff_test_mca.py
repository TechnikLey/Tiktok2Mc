#!/usr/bin/env python3
"""
Differential testing: compare Python MCA validator vs JS language server.

Generates hundreds of valid and invalid MCA snippets, runs both
implementations, and reports every mismatch.

Usage:
    python tools/diff_test_mca.py [--count N] [--seed S]
"""

import json
import random
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

# Add src to path for importing the Python validator
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from core.validator import validate_text

# ── Test case generators ────────────────────────────────────────────────

VALID_TRIGGER_NAMES = [
    "follow", "join", "comment", "likes", "like_2", "share",
    "test", "my_trigger", "abc123", "A", "z", "0", "_",
    "gift_12345", "custom_event", "on_message",
]

QUOTED_TRIGGER_NAMES = [
    "'my trigger'", "'Tom the Tomato'", "'a'", "'hello world'",
    "'test 123'", "'my_custom trigger'",
]

INVALID_TRIGGER_NAMES = [
    "bad-trigger", "trigger!", "@trigger", "#trigger", ".trigger",
    "trigger name", "trigger,name", "trigger$", "trigger%",
]

INVALID_QUOTED = [
    "'bad-trigger!'", "'trigger@name'", "'a,b'", "'bad.name'",
    "'test<script>'", "''", "'unclosed", "unclosed'",
]

COMMAND_BODIES = [
    "/say hello", "/give @a diamond", "/execute at @a run summon creeper",
    "/clear @a *", "/kill @a", "/tp @a ~ ~5 ~",
    "!tnt 2 0.1 2 Notch", "!cmd arg1 arg2",
    "$random", "$my_script",
    "&curl http://localhost:29191/add", "&echo hello",
    ">>Welcome!|{user} joined!|5",
    ">>Title", ">>Title|Subtitle",
    ">>{user} wrote:|{comment}",
    "@screen>>Title|Subtitle|3",
]

INVALID_COMMANDS = [
    "%bad command", "missingprefix", "@incomplete", "@|>>bad",
]

MULTIPLIERS = ["x2", "x5", "x10", "x50", "x100"]

INVALID_MULTIPLIERS = ["xabc", "x", "x1.5", "x-1"]

BRACKET_VARIANTS = [
    "/say [test]", "/say {nbt}", "/say [{nested}]",
    "/say [unclosed", "/say {unclosed", "/say ]extra",
    "/say }extra", '/say "keep [balanced"', "/say 'keep [balanced'",
    "/say [it\\'s ok]",
]


def generate_valid_line(rng: random.Random) -> str:
    """Generate a syntactically valid MCA line."""
    name = rng.choice(VALID_TRIGGER_NAMES + QUOTED_TRIGGER_NAMES)
    cmd_count = rng.randint(1, 3)
    cmds = rng.sample(COMMAND_BODIES, min(cmd_count, len(COMMAND_BODIES)))

    # Maybe add a multiplier to a non-overlay command
    result_cmds = []
    for cmd in cmds:
        if rng.random() < 0.3 and not cmd.startswith(">>") and not cmd.startswith("@"):
            mult = rng.choice(MULTIPLIERS)
            result_cmds.append(f"{cmd} {mult}")
        else:
            result_cmds.append(cmd)

    line = f"{name}:{'; '.join(result_cmds)}"

    # Maybe add inline comment
    if rng.random() < 0.1:
        line += " # inline comment"

    return line


def generate_invalid_line(rng: random.Random) -> str:
    """Generate an invalid MCA line with one or more issues."""
    # Randomly choose an error type
    error_type = rng.randint(0, 10)

    if error_type == 0:
        # Missing colon
        name = rng.choice(VALID_TRIGGER_NAMES)
        cmd = rng.choice(COMMAND_BODIES)
        return f"{name} {cmd}"

    elif error_type == 1:
        # Invalid trigger name
        name = rng.choice(INVALID_TRIGGER_NAMES)
        cmd = rng.choice(COMMAND_BODIES)
        return f"{name}:{cmd}"

    elif error_type == 2:
        # Invalid quoted trigger
        name = rng.choice(INVALID_QUOTED)
        cmd = rng.choice(COMMAND_BODIES)
        return f"{name}:{cmd}"

    elif error_type == 3:
        # Invalid prefix
        name = rng.choice(VALID_TRIGGER_NAMES)
        cmd = rng.choice(INVALID_COMMANDS)
        return f"{name}:{cmd}"

    elif error_type == 4:
        # No content after colon
        name = rng.choice(VALID_TRIGGER_NAMES)
        return f"{name}:"

    elif error_type == 5:
        # Trailing colons
        name = rng.choice(VALID_TRIGGER_NAMES)
        cmd = rng.choice(COMMAND_BODIES)
        return f"{name}:{cmd}:"

    elif error_type == 6:
        # Invalid multiplier
        name = rng.choice(VALID_TRIGGER_NAMES)
        cmd = rng.choice(COMMAND_BODIES)
        mult = rng.choice(INVALID_MULTIPLIERS)
        return f"{name}:{cmd} {mult}"

    elif error_type == 7:
        # Overlay with multiplier
        name = rng.choice(VALID_TRIGGER_NAMES)
        mult = rng.choice(MULTIPLIERS)
        return f"{name}:>>Title {mult}"

    elif error_type == 8:
        # {comment} on non-comment trigger
        name = rng.choice([t for t in VALID_TRIGGER_NAMES if t != "comment"])
        return f"{name}:>>{name} said {{{{comment}}}}"

    elif error_type == 9:
        # Unmatched brackets
        name = rng.choice(VALID_TRIGGER_NAMES)
        bracket_case = rng.choice(["/say ]", "/say }", "/say [unclosed", "/say {unclosed"])
        return f"{name}:{bracket_case}"

    elif error_type == 10:
        # Space after colon
        name = rng.choice(VALID_TRIGGER_NAMES)
        cmd = rng.choice(COMMAND_BODIES)
        return f"{name}: {cmd}"

    return generate_valid_line(rng)


def generate_test_case(rng: random.Random) -> str:
    """Generate a complete test document (one or more lines)."""
    num_lines = rng.randint(1, 5)
    lines = []

    for _ in range(num_lines):
        if rng.random() < 0.3:
            # Comment line
            lines.append(f"# {rng.choice(['comment', 'disabled test', 'TODO', 'fix this'])}")
        elif rng.random() < 0.15:
            # Disabled trigger
            name = rng.choice(VALID_TRIGGER_NAMES)
            cmd = rng.choice(COMMAND_BODIES)
            lines.append(f"##{name}:{cmd}")
        elif rng.random() < 0.35:
            # Invalid line
            lines.append(generate_invalid_line(rng))
        else:
            # Valid line
            lines.append(generate_valid_line(rng))

    # Maybe add duplicate
    if rng.random() < 0.3 and len([l for l in lines if ":" in l and not l.strip().startswith("#")]) >= 2:
        valid_lines = [l for l in lines if ":" in l and not l.strip().startswith("#")]
        dup = rng.choice(valid_lines)
        dup_name = dup.split(":")[0].strip()
        lines.append(f"{dup_name}:/another_command")

    return "\n".join(lines)


# ── Python validator runner ─────────────────────────────────────────────

def run_python_validator(text: str) -> list[dict[str, Any]]:
    """Run the Python validator and return normalized diagnostics."""
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


# ── JS validator runner ─────────────────────────────────────────────────

def run_js_validator(text: str) -> list[dict[str, Any]]:
    """Run the JS language server validator via Node.js subprocess."""
    if not shutil.which("node"):
        print("Error: Node.js is not installed or not in PATH.", file=sys.stderr)
        print("Install it: https://nodejs.org/ or use your package manager:", file=sys.stderr)
        print("  sudo apt install nodejs    # Debian / Ubuntu", file=sys.stderr)
        print("  sudo pacman -S nodejs      # Arch", file=sys.stderr)
        print("  sudo dnf install nodejs    # Fedora", file=sys.stderr)
        return []

    js_runner = SCRIPT_DIR.parent / "mca-language-server" / "server" / "test" / "run_validator.js"

    # Escape the text for passing as argument
    escaped = json.dumps(text)

    result = subprocess.run(
        ["node", str(js_runner), escaped],
        capture_output=True, text=True, timeout=30,
        cwd=str(js_runner.parent),
    )

    if result.returncode != 0:
        print(f"JS validator error (exit {result.returncode}):", file=sys.stderr)
        print(result.stderr[:500], file=sys.stderr)
        return []

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        print(f"JSON parse error: {e}", file=sys.stderr)
        print(f"stdout: {result.stdout[:500]}", file=sys.stderr)
        return []


# ── Normalization & comparison ──────────────────────────────────────────

SEVERITY_MAP = {
    "ERROR": 1,
    "WARNING": 2,
    "INFO": 3,
}

def normalize_severity(sev: str | int) -> int:
    """Convert severity to integer for comparison."""
    if isinstance(sev, int):
        return sev
    return SEVERITY_MAP.get(sev, 0)


def diagnostics_equal(a: dict, b: dict) -> bool:
    """Check if two diagnostics are equivalent (ignoring exact message wording)."""
    return (
        a["line"] == b["line"]
        and a["start_char"] == b["start_char"]
        and a["end_char"] == b["end_char"]
        and a["code"] == b["code"]
        and normalize_severity(a.get("severity", a.get("severity", 0))) == normalize_severity(b.get("severity", b.get("severity", 0)))
    )


def compare_diagnostics(
    py_diags: list[dict],
    js_diags: list[dict],
    text: str,
) -> list[str]:
    """Compare Python and JS diagnostics and return list of mismatch descriptions."""
    mismatches = []

    # Check for diagnostics in Python but not in JS (or different)
    for pd in py_diags:
        found = False
        for jd in js_diags:
            if diagnostics_equal(pd, jd):
                found = True
                break
        if not found:
            mismatches.append(
                f"  PY only: line {pd['line']} col {pd['start_char']}-{pd['end_char']} "
                f"[{pd['code']}] {pd['message'][:60]}"
            )

    # Check for diagnostics in JS but not in Python
    for jd in js_diags:
        found = False
        for pd in py_diags:
            if diagnostics_equal(jd, pd):
                found = True
                break
        if not found:
            mismatches.append(
                f"  JS only: line {jd['line']} col {jd['start_char']}-{jd['end_char']} "
                f"[{jd['code']}] {jd.get('message', '')[:60]}"
            )

    return mismatches


# ── Main ────────────────────────────────────────────────────────────────

def main():
    parser = __import__("argparse").ArgumentParser(
        description="Differential test: compare Python vs JS MCA validators"
    )
    parser.add_argument("--count", type=int, default=500, help="Number of test cases")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--save", type=str, default=None, help="Save test cases to file")
    parser.add_argument("--load", type=str, default=None, help="Load test cases from file")
    args = parser.parse_args()

    rng = random.Random(args.seed)

    if args.load:
        with open(args.load, "r") as f:
            test_cases = json.load(f)
        print(f"Loaded {len(test_cases)} test cases from {args.load}")
    else:
        test_cases = []
        for i in range(args.count):
            test_cases.append(generate_test_case(rng))

        if args.save:
            with open(args.save, "w") as f:
                json.dump(test_cases, f, indent=2)
            print(f"Saved {len(test_cases)} test cases to {args.save}")

    total_mismatches = 0
    total_cases = 0
    errors_in_py = 0
    errors_in_js = 0
    py_diag_count = 0
    js_diag_count = 0

    for idx, text in enumerate(test_cases):
        py_diags = run_python_validator(text)
        js_diags = run_js_validator(text)

        py_diag_count += len(py_diags)
        js_diag_count += len(js_diags)
        errors_in_py += sum(1 for d in py_diags if d.get("severity", d.get("severity", "")) in ("ERROR", 1))
        errors_in_js += sum(1 for d in js_diags if d.get("severity", d.get("severity", "")) in ("ERROR", 1))

        mismatches = compare_diagnostics(py_diags, js_diags, text)

        if mismatches:
            total_mismatches += 1
            total_cases += 1
            lines = text.split("\n")
            print(f"\n=== Mismatch #{total_mismatches} (case {idx}) ===")
            for li, l in enumerate(lines):
                print(f"  {li:3d}: {l}")
            print(f"  Python: {len(py_diags)} diag(s), JS: {len(js_diags)} diag(s)")
            for m in mismatches:
                print(m)
            if total_mismatches >= 20:
                print("\n... too many mismatches, stopping.")
                break

    test_count = len(test_cases)
    print(f"\n{'='*60}")
    print(f"Total test cases:     {test_count}")
    print(f"Cases with mismatches: {total_mismatches}")
    print(f"Python diagnostics:   {py_diag_count} ({errors_in_py} errors)")
    print(f"JS diagnostics:       {js_diag_count} ({errors_in_js} errors)")

    check = "OK" if total_mismatches == 0 else "FAIL"
    print(f"\n[{check}] {test_count} test cases: {total_mismatches} mismatches.")
    return 0 if total_mismatches == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
