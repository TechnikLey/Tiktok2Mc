"""Shared diagnostic types for validation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any


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


def _make_diag(
    line: int,
    start: int,
    end: int,
    message: str,
    severity: Severity,
    code: str | None = None,
) -> Diagnostic:
    """Create a Diagnostic with consistent coordinate handling."""
    return Diagnostic(
        line=line,
        start_char=start,
        end_char=end,
        message=message,
        severity=severity,
        code=code,
    )


# ---------------------------------------------------------------------------
#  Crash diagnostics report generation
# ---------------------------------------------------------------------------


def generate_diagnostics_report(crash_manager: Any | None) -> dict[str, Any]:
    """Generate a full JSON diagnostics report from a CrashManager."""
    if crash_manager is None:
        return {"error": "CrashManager not available"}

    try:
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "module": crash_manager.module_name,
            "crash_count": crash_manager.get_crash_count(),
            "history": crash_manager.get_crash_history(),
            "stats": crash_manager.get_stats(),
        }
    except Exception as e:
        return {"error": f"Failed to generate report: {e}"}


def generate_diagnostics_markdown(crash_manager: Any | None) -> str:
    """Generate a human-readable Markdown diagnostics report."""
    if crash_manager is None:
        return "# Diagnostics Report\n\nCrashManager not available.\n"

    try:
        stats = crash_manager.get_stats()
        history = crash_manager.get_crash_history()

        lines = [
            f"# Diagnostics Report: {stats.get('module', 'unknown')}",
            f"**Generated:** {datetime.now(timezone.utc).isoformat()}",
            f"**Crash Count:** {stats.get('crash_count', 0)}",
            f"**History Size:** {stats.get('history_size', 0)}",
            "",
            "## Recent Crashes",
        ]

        if not history:
            lines.append("*No crashes recorded.*")
        else:
            for i, crash in enumerate(reversed(history), 1):
                lines.append(f"### {i}. {crash.get('code', 'UNKNOWN')}")
                lines.append(f"- **Timestamp:** {crash.get('timestamp', 'N/A')}")
                lines.append(f"- **Severity:** {crash.get('severity', 'N/A')}")
                lines.append(f"- **Module:** {crash.get('module', 'N/A')}")
                lines.append(f"- **Exception:** {crash.get('exception', 'N/A')}")
                if crash.get("context"):
                    lines.append(f"- **Context:** {crash['context']}")
                if crash.get("stack"):
                    lines.append(f"- **Stack:**\n```\n{crash['stack']}\n```")
                lines.append("")

        return "\n".join(lines)
    except Exception as e:
        return f"# Diagnostics Report\n\nError generating report: {e}\n"
