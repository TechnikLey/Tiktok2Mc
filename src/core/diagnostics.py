"""Runtime diagnostics report system.

Generates a comprehensive snapshot of the application's health,
including all component states, recent errors, crash history,
queue statistics, thread statistics, and async task information.

This report is designed to make debugging production issues
significantly easier.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any

from core.error_codes import list_all_codes
from core.health_monitor import get_health_monitor

log = logging.getLogger(__name__)


def _get_thread_stats() -> dict[str, Any]:
    """Collect statistics about running threads."""
    threads = threading.enumerate()
    active_count = threading.active_count()
    thread_details = []
    for t in threads:
        thread_details.append({
            "name": t.name,
            "daemon": t.daemon,
            "alive": t.is_alive(),
            "ident": t.ident,
        })
    return {
        "active_count": active_count,
        "total_count": len(threads),
        "threads": thread_details,
    }


def _get_async_tasks() -> list[dict[str, Any]]:
    """Collect statistics about asyncio tasks."""
    tasks = []
    try:
        loop = asyncio.get_running_loop()
        all_tasks = asyncio.all_tasks(loop)
        for t in all_tasks:
            tasks.append({
                "name": t.get_name(),
                "done": t.done(),
                "cancelled": t.cancelled(),
                "exception": str(t.exception()) if t.done() and not t.cancelled() and t.exception() else None,
            })
    except RuntimeError:
        pass
    return tasks


def _get_memory_stats() -> dict[str, Any]:
    """Collect memory statistics if psutil is available."""
    try:
        import psutil
        proc = psutil.Process()
        mem = proc.memory_info()
        return {
            "rss_mb": round(mem.rss / (1024 * 1024), 2),
            "vms_mb": round(mem.vms / (1024 * 1024), 2),
            "percent": round(proc.memory_percent(), 2),
            "cpu_percent": proc.cpu_percent(interval=0.1),
        }
    except ImportError:
        return {}
    except Exception:  # diagnostics are best-effort, must never raise
        return {}


def _get_queue_stats(crash_manager: Any = None) -> dict[str, Any]:
    """Collect queue statistics from the bridge context if available."""
    stats = {}
    try:
        import sys as _sys
        if "src.python.main" in _sys.modules:
            ctx = _sys.modules["src.python.main"].ctx
            stats["trigger_queue"] = {
                "size": ctx.trigger_queue.qsize() if hasattr(ctx, "trigger_queue") else -1,
                "maxsize": ctx.trigger_queue.maxsize if hasattr(ctx, "trigger_queue") else -1,
            }
            stats["rcon_queue"] = {
                "size": ctx.rcon_queue.qsize() if hasattr(ctx, "rcon_queue") else -1,
                "maxsize": ctx.rcon_queue.maxsize if hasattr(ctx, "rcon_queue") else -1,
            }
        else:
            stats["bridge"] = "not loaded in this process"
    except Exception:  # diagnostics are best-effort, must never raise
        stats["bridge"] = "not available"
    return stats


def generate_diagnostics_report(crash_manager: Any | None = None, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """Generate a comprehensive diagnostics snapshot.

    This is the main entry point for runtime diagnostics.
    Returns a dictionary suitable for JSON serialization.
    """
    health = get_health_monitor()

    report: dict[str, Any] = {
        "generated_at": time.time(),
        "generated_at_iso": _timestamp_iso(),
        "application": {
            "python_version": sys.version,
            "platform": sys.platform,
            "cwd": str(Path.cwd()),
            "pid": os.getpid(),
        },
        "health": health.summary(),
        "threads": _get_thread_stats(),
        "async_tasks": _get_async_tasks(),
        "memory": _get_memory_stats(),
        "queue_stats": _get_queue_stats(crash_manager),
        "error_codes": {
            "total": len(list_all_codes()),
        },
    }

    if crash_manager is not None:
        report["crash_manager"] = crash_manager.get_stats()
        report["crash_history"] = crash_manager.get_crash_history()

    if extra:
        report["extra"] = extra

    return report


def generate_diagnostics_markdown(crash_manager: Any | None = None, extra: dict[str, Any] | None = None) -> str:
    """Generate a human-readable diagnostics report in Markdown format."""
    report = generate_diagnostics_report(crash_manager, extra)
    lines: list[str] = []

    lines.append("# TikTok2Mc Diagnostics Report")
    lines.append(f"Generated: {report['generated_at_iso']}")
    lines.append(f"PID: {report['application']['pid']}  |  Platform: {report['application']['platform']}")
    lines.append("")

    # Health summary
    health = report["health"]
    lines.append("## Health Status")
    lines.append(f"- Uptime: {health['uptime_seconds']:.0f}s")
    lines.append(f"- Components: {health['total_components']} total, {health['running']} running, "
                 f"{health['degraded']} degraded, {health['failed']} failed")
    if health["failed_components"]:
        lines.append(f"- **Failed**: {', '.join(health['failed_components'])}")
    if health["degraded_components"]:
        lines.append(f"- **Degraded**: {', '.join(health['degraded_components'])}")
    if health["last_error"]:
        lines.append(f"- Last error: {health['last_error']}")
    lines.append("")

    # Component states
    lines.append("## Component States")
    for comp, state in sorted(health["states"].items()):
        icon = {"RUNNING": "OK", "DEGRADED": "!", "FAILED": "X", "STOPPED": "-", "UNKNOWN": "?"}.get(state, "?")
        lines.append(f"- [{icon}] {comp}: **{state}**")
    lines.append("")

    # Thread stats
    lines.append("## Threads")
    threads = report["threads"]
    lines.append(f"- Active threads: {threads['active_count']}")
    for t in threads["threads"]:
        daemon = " (daemon)" if t["daemon"] else ""
        alive = "alive" if t["alive"] else "dead"
        lines.append(f"  - {t['name']}: {alive}{daemon}")
    lines.append("")

    # Memory
    mem = report["memory"]
    if mem:
        lines.append("## Memory")
        lines.append(f"- RSS: {mem.get('rss_mb', 'N/A')} MB")
        lines.append(f"- VMS: {mem.get('vms_mb', 'N/A')} MB")
        lines.append(f"- CPU: {mem.get('cpu_percent', 'N/A')}%")
        lines.append("")

    # Queue stats
    lines.append("## Queues")
    for qname, qstats in report["queue_stats"].items():
        if isinstance(qstats, dict):
            lines.append(f"- {qname}: {qstats.get('size', '?')}/{qstats.get('maxsize', '?')} items")
        else:
            lines.append(f"- {qname}: {qstats}")
    lines.append("")

    # Crash history
    if "crash_history" in report:
        lines.append("## Crash History")
        lines.append(f"- Total crashes: {report['crash_manager'].get('crash_count', 0)}")
        for crash in report["crash_history"][-10:]:
            lines.append(f"- [{crash.get('code', '?')}] {crash.get('exception', crash.get('detail', ''))}")
        lines.append("")

    # Error codes reference
    lines.append("## Error Codes")
    lines.append(f"- Total defined: {report['error_codes']['total']}")
    lines.append("")

    return "\n".join(lines)


def _timestamp_iso() -> str:
    from datetime import UTC, datetime
    return datetime.now(tz=UTC).isoformat()
