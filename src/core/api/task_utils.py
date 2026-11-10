#!/usr/bin/env python3
"""Loop-safe helpers for cancelling background tasks.

Background singletons (event bridge, outbound dispatcher, trackers) are
shared across the process, while each FastAPI app instance runs its
lifespan in its own event-loop portal (TestClient in tests; in-process
server restart in the supervisor). Cancelling a task that was created on
a *foreign* loop and awaiting it from the current loop either raises
"attached to a different loop" or blocks forever, and the finally-block
cleanup (e.g. ``event_bus.unsubscribe``) then never runs — leaking
subscriber queues that later turn every ``log.unified`` publish into a
queue-full storm.

:meth:`stop_task_safely` centralises the safe pattern: cancel + await
only when the current loop owns the task; otherwise schedule the cancel
on the task's own loop when that loop is still running, and always call
back the caller's abandon hook so bus subscriptions can be released
explicitly.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

log = logging.getLogger(__name__)


async def stop_task_safely(
    task: asyncio.Task | None,
    on_abandoned: Callable[[], None] | None = None,
) -> None:
    """Cancel *task* without cross-loop hazards.

    Args:
        task: The task to stop, or ``None`` (no-op).
        on_abandoned: Called synchronously when the task's ``finally``
            cleanup cannot be reliably awaited (task owned by a foreign
            or already-closed loop). Use it to release resources the
            task normally frees on exit, e.g. event-bus subscriptions
            (``unsubscribe`` is idempotent).
    """
    if task is None or task.done():
        return

    try:
        owner_loop = task.get_loop()
    except RuntimeError:  # task impl detail unavailable — treat as done
        return

    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    if current_loop is not None and owner_loop is current_loop:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        return

    # Foreign loop: awaiting the task here would block or raise. Schedule
    # the cancellation on the task's own loop when it is still usable;
    # the abandoned-callback releases what the task's finally would have.
    if on_abandoned is not None:
        try:
            on_abandoned()
        except Exception as exc:  # cleanup is best-effort
            log.warning("stop_task_safely: on_abandoned callback failed: %s", exc)
    if not owner_loop.is_closed():
        try:
            owner_loop.call_soon_threadsafe(task.cancel)
        except RuntimeError as exc:  # loop closed between check and call
            log.debug("stop_task_safely: owner loop closed: %s", exc)
