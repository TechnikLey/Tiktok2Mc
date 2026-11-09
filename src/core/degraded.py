#!/usr/bin/env python3
"""Structured reporting for *degraded but running* components.

A degraded state is one where the application keeps running after a
configuration or data file could not be loaded, and falls back to safe
defaults (empty mappings, empty catalogs, factory config). The previous,
silent ``log.warning`` + fallback pattern made "program runs but nothing
works" failures invisible to user-facing tooling.

:meth:`report_degraded` is the single helper every such fallback must go
through. It performs three things:

1. Report via :class:`~core.crash_manager.CrashManager` with a structured
   error code (visible in crash history / diagnostics endpoints).
2. Move the component to ``HealthState.DEGRADED`` in the health monitor
   (visible in health endpoints).
3. Publish a ``config.degraded`` event on the in-process event bus, so
   connected dashboards can surface the problem immediately (best
   effort — skipped when no asyncio loop is running).

Callers keep full control over whether they continue using their fallback
value; this helper never raises and never changes control flow.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from core.crash_manager import get_crash_manager
from core.error_codes import ErrorCode
from core.health_monitor import HealthState, get_health_monitor

log = logging.getLogger(__name__)

EVENT_TYPE = "config.degraded"
"""Event type published on the event bus for degraded fallbacks."""


def report_degraded(
    error_code: ErrorCode,
    component: str,
    detail: str,
    *,
    path: str | None = None,
    health: bool = True,
    publish: bool = True,
) -> None:
    """Report a degraded fallback condition through all visibility channels.

    Args:
        error_code: Structured code from ``core.error_codes`` (e.g.
            ``CONFIG_0009``) describing the fallback that was applied.
        component: Component identifier as used by the health monitor,
            e.g. ``"event_command_mapper"`` or ``"gift_catalog"``.
        detail: Occurrence-specific description (what failed, and which
            fallback value is now active).
        path: File system path of the offending file, when known.
        health: Whether to move *component* to ``DEGRADED`` (defaults to
            ``True``).
        publish: Whether to publish a ``config.degraded`` event on the
            event bus (defaults to ``True``).
    """
    context: dict[str, Any] = {"component": component}
    if path is not None:
        context["path"] = path

    try:
        get_crash_manager().report_error(
            error_code, detail=detail, context_info=context
        )
    except Exception as exc:  # noqa: BLE001 - visibility must never break callers
        log.warning("Failed to report degraded state via crash manager: %s", exc)

    if health:
        try:
            monitor = get_health_monitor()
            # Register with STARTING so an unknown component can legally go
            # STARTING -> DEGRADED (UNKNOWN -> DEGRADED is not allowed).
            monitor.register(component, HealthState.STARTING)
            monitor.set_state(component, HealthState.DEGRADED)
        except Exception as exc:  # noqa: BLE001 - visibility must never break callers
            log.warning(
                "Failed to mark '%s' degraded in health monitor: %s", component, exc
            )

    if publish:
        _publish_best_effort(
            {
                "code": error_code.code,
                "severity": error_code.severity.label(),
                "component": component,
                "message": error_code.message,
                "detail": detail,
                "path": path,
                "timestamp": time.time(),
            }
        )


def _publish_best_effort(data: dict[str, Any]) -> None:
    """Publish a degraded event on the event bus when a loop is available.

    Inside a running asyncio loop the publish is scheduled as a task.
    Outside of one (e.g. during synchronous module init) the publish is
    skipped with a debug log — the crash report and health state still
    carry the information.

    Args:
        data: Event payload (code, component, detail, path, timestamp).
    """
    from core.api.eventbus import event_bus  # local import breaks circulars

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        log.debug("No running loop; skip event bus publish for degraded event")
        return
    loop.create_task(event_bus.publish(EVENT_TYPE, data))
