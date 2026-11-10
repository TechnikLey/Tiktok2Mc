"""Loop-safe task teardown (``core.api.task_utils``).

Regression tests for the cross-loop cancellation hazard: background
singleton tasks are created inside one app-portal event loop, while
lifespan shutdown (and thus ``stop()``) may run on a different, later
loop. Cancelling and awaiting a foreign task either raises
"attached to a different loop" or blocks forever — which used to hang
the TestClient teardown when the combined pytest session left stale
singleton tasks behind."""

from __future__ import annotations

import asyncio
import threading
import time

import pytest

from core.api.task_utils import stop_task_safely


def _start_loop_thread(holder: dict) -> threading.Thread:
    """Run a *kept-alive* event loop in a helper thread.

    Creates a task owned by the helper loop and stores loop/task in
    *holder*. ``asyncio.run`` is deliberately avoided there: it would
    cancel the pending task on exit and destroy the cross-loop scenario
    these tests must reproduce."""

    ready = threading.Event()

    def runner() -> None:
        loop = asyncio.new_event_loop()
        holder["loop"] = loop

        async def worker() -> None:
            await asyncio.sleep(60)

        holder["task"] = loop.create_task(worker())
        ready.set()
        loop.run_forever()

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    ready.wait(timeout=5.0)
    return thread


def _stop_loop_thread(holder: dict, thread: threading.Thread) -> None:
    """Stop the helper loop and wait for its thread to finish."""
    holder["loop"].call_soon_threadsafe(holder["loop"].stop)
    thread.join(timeout=5.0)
    assert not thread.is_alive()


@pytest.mark.unit
class TestStopTaskSafely:
    """Behaviour of :func:`stop_task_safely` across loop boundaries."""

    def test_same_loop_cancel_and_await(self) -> None:
        """A task of the current loop is cancelled and awaited normally."""

        async def scenario() -> bool:
            async def worker() -> None:
                await asyncio.sleep(60)

            task = asyncio.create_task(worker())
            await asyncio.sleep(0.01)  # let the worker start
            await stop_task_safely(task)
            return task.done()

        assert asyncio.run(scenario()) is True

    def test_abandoned_callback_called_for_none_and_done_tasks(self) -> None:
        """``None`` and already-finished tasks return without side effects."""

        async def scenario() -> list[bool]:
            calls: list[bool] = []

            async def quick() -> None:
                await asyncio.sleep(0)

            await stop_task_safely(None, on_abandoned=lambda: calls.append(True))
            task = asyncio.create_task(quick())
            await task
            await stop_task_safely(task, on_abandoned=lambda: calls.append(True))
            return calls

        assert asyncio.run(scenario()) == []

    def test_foreign_running_loop_returns_quickly_and_abandons(self) -> None:
        """A task on a *foreign* (still running) loop: cancel is scheduled on
        its own loop and the abandon hook runs on the caller side."""

        holder: dict = {}
        thread = _start_loop_thread(holder)
        calls: list[bool] = []
        try:
            asyncio.run(
                stop_task_safely(
                    holder["task"], on_abandoned=lambda: calls.append(True)
                )
            )
            # The cancel was scheduled on the foreign loop; give it a moment
            # to process before that loop is stopped (call_soon_threadsafe
            # callbacks never run once the loop is stopped — stopping too
            # early would leave the task pending and flake this assertion).
            for _ in range(100):
                if holder["task"].cancelled():
                    break
                time.sleep(0.02)
        finally:
            _stop_loop_thread(holder, thread)
        assert calls == [True]
        assert holder["task"].cancelled()

    def test_closed_owner_loop_still_returns_quickly(self) -> None:
        """A task whose owner loop is closed: no raise, abandon hook runs."""

        holder: dict = {}

        loop = asyncio.new_event_loop()

        async def worker() -> None:
            await asyncio.sleep(60)

        holder["task"] = loop.create_task(worker())
        loop.run_until_complete(asyncio.sleep(0.01))
        loop.close()  # leave the task pending-but-abandoned

        calls: list[bool] = []
        asyncio.run(
            stop_task_safely(holder["task"], on_abandoned=lambda: calls.append(True))
        )
        assert calls == [True]
