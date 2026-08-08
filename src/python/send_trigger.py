#!/usr/bin/env python3
"""Standalone trigger testing tool.

Packaged as ``test_trigger.exe`` by the build system.

This is a thin CLI frontend to the shared ``TriggerEngine``.
It does **not** contain any trigger execution, validation, or
payload-construction logic — all of that lives in
``core.trigger_engine``.

Usage
-----
    python send_trigger.py <trigger_name> [options]

Examples
--------
    python send_trigger.py follow --user TestUser
    python send_trigger.py comment --user TestUser --text "Hello World"
    python send_trigger.py gift --user TestUser --gift-id 5655
    python send_trigger.py --list
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger("send_trigger")

from core.trigger_engine import EngineConfig, TriggerEngine  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Send a test trigger or comment to the TikTok bridge.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "trigger",
        nargs="?",
        default=None,
        help="Trigger name (e.g. follow, like, join, share, comment, gift, or custom name)",
    )
    p.add_argument("--user", default="System", help="Simulated username")
    p.add_argument("--gift-id", default=None, help="Gift ID (for gift events)")
    p.add_argument("--gift-name", default=None, help="Gift display name")
    p.add_argument("--text", default=None, help="Comment text (for comment events)")
    p.add_argument(
        "--moderator", action="store_true", help="Mark comment as from a moderator"
    )
    p.add_argument(
        "--superfan", action="store_true", help="Mark comment as from a superfan"
    )
    p.add_argument(
        "--fanclub", action="store_true", help="Mark comment as from a fanclub member"
    )
    p.add_argument("--host", default="127.0.0.1", help="Bridge host")
    p.add_argument("--port", type=int, default=29188, help="Bridge webhook port")
    p.add_argument(
        "--timeout", type=float, default=5.0, help="Bridge request timeout (seconds)"
    )
    p.add_argument(
        "--list", action="store_true", help="List available trigger types and exit"
    )
    p.add_argument("--json", action="store_true", help="Output result as JSON")
    p.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")
    return p


def _list_types(engine: TriggerEngine) -> None:
    defs = engine.get_trigger_definitions()
    print("Available trigger types:")
    print("=" * 60)
    for d in defs:
        flags = []
        if d.requires_gift_selection:
            flags.append("requires gift-id")
        if d.supports_comment_text:
            flags.append("supports comment text")
        flag_str = f"  [{', '.join(flags)}]" if flags else ""
        print(f"  {d.name:12s}  {d.display_name:8s}  {d.description}{flag_str}")
    print()
    print("Custom triggers:  Any trigger name that is valid in actions.mca")
    print("                 can be sent (e.g. a numeric gift ID).")


def _format_result(result, verbose: bool = False) -> str:
    lines = []
    icon = "\u2713" if result.success else "\u2717"
    lines.append(f"{icon} Trigger:  {result.trigger_name}")
    lines.append(f"  Status:   {result.status.value}")
    lines.append(f"  Time:     {result.execution_time_ms:.0f} ms")
    if result.payload:
        lines.append(f"  Payload:  {json.dumps(result.payload)}")
    if result.warnings:
        for w in result.warnings:
            lines.append(f"  Warning:  {w}")
    if result.validation_errors:
        lines.append("  Validation errors:")
        for e in result.validation_errors:
            lines.append(f"    - {e.field}: {e.message}")
    if result.error_message:
        lines.append(f"  Message:  {result.error_message}")
    if result.error_code:
        lines.append(f"  Code:     {result.error_code}")
    if result.suggested_fix:
        lines.append(f"  Fix:      {result.suggested_fix}")
    if verbose and result.exception_detail:
        lines.append(f"  Detail:   {result.exception_detail}")
    if verbose and result.bridge_response:
        lines.append(f"  Bridge:   {json.dumps(result.bridge_response)}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.verbose:
        logging.getLogger("core.trigger_engine").setLevel(logging.DEBUG)

    config = EngineConfig(
        bridge_host=args.host,
        bridge_port=args.port,
        bridge_timeout=args.timeout,
    )
    engine = TriggerEngine(config=config)

    if args.list:
        _list_types(engine)
        return 0

    if not args.trigger:
        parser.print_help()
        return 1

    trigger_name = args.trigger.strip().lower()

    if trigger_name == "comment" and args.text is not None:
        result = engine.execute_comment(
            user=args.user,
            text=args.text,
            moderator=args.moderator,
            superfan=args.superfan,
            fanclub=args.fanclub,
        )
    elif trigger_name == "gift" and args.gift_id:
        result = engine.execute_trigger(
            trigger_name=args.gift_id,
            user=args.user,
            gift_id=args.gift_id,
            gift_name=args.gift_name,
        )
    else:
        result = engine.execute_trigger(
            trigger_name=trigger_name,
            user=args.user,
            gift_id=args.gift_id,
            gift_name=args.gift_name,
        )

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(_format_result(result, verbose=args.verbose))

    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
