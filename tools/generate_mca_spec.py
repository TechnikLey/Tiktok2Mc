#!/usr/bin/env python3
"""Generate a shared MCA language specification JSON from the Python implementation.

This script calls into core.mca_spec.export_spec() which reads the live
Python runtime definitions (validator.py, actions.py) and produces a
machine-readable JSON spec consumed by the VS Code language server,
test frameworks, and other tooling.

Usage:
    python tools/generate_mca_spec.py [--output path/to/mca-spec.json]
    python tools/generate_mca_spec.py --check   # verify existing spec is current
"""

import json
import sys
from pathlib import Path

# Ensure src/ is on the path for runtime imports
_src = str(Path(__file__).resolve().parent.parent / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from core.mca_spec import export_spec  # noqa: E402


def main() -> None:
    project_root = Path(__file__).resolve().parent.parent
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

    spec = export_spec()
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
