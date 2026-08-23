"""Tests for hook unload lifecycle and the register_timer() abstraction.

Hooks cannot import threading (import whitelist), so periodic work goes
through ``HookAPI.register_timer(interval, fn)`` which runs on the loader's
shared scheduler thread. ``api.on_unload(fn)`` registers a dispose callback
that runs before a runtime reload clears the hook's registrations.
"""

import asyncio
import time

import pytest

from core.hook_api import (
    HOOK_LIFECYCLE,
    HOOK_TIMERS,
    HookAPI,
    clear_hook_registrations,
)
from core.hook_loader import (
    _stop_timer_thread,
    fire_hook_lifecycle,
    start_timer_scheduler,
    unload_event_hooks,
)


@pytest.fixture(autouse=True)
def _clean_state():
    saved_lifecycle = {k: dict(v) for k, v in HOOK_LIFECYCLE.items()}
    saved_timers = {k: list(v) for k, v in HOOK_TIMERS.items()}
    clear_hook_registrations()
    yield
    _stop_timer_thread()
    clear_hook_registrations()
    for key, value in saved_lifecycle.items():
        HOOK_LIFECYCLE[key].clear()
        HOOK_LIFECYCLE[key].update(value)
    HOOK_TIMERS.clear()
    HOOK_TIMERS.update(saved_timers)


@pytest.fixture
def bound_api():
    loop = asyncio.new_event_loop()
    api = HookAPI(asyncio.Queue(), asyncio.Queue(), loop, {}, set())
    return api.for_hook("timer-hook")


class TestUnloadLifecycle:
    def test_unload_callback_fires_before_clear(self):
        calls = []
        HOOK_LIFECYCLE["unload"]["my-hook"] = lambda: calls.append("unloaded")
        removed = unload_event_hooks()
        assert "unloaded" in calls
        # The unload callback itself was registered outside the normal flow;
        # no actions existed, so nothing else is removed.
        assert removed == 0

    def test_on_unload_shortcut_registers(self, bound_api):
        calls = []
        bound_api.on_unload(lambda: calls.append(1))
        assert "timer-hook" in HOOK_LIFECYCLE["unload"]

    def test_fire_hook_lifecycle_unknown_event(self):
        assert fire_hook_lifecycle("does_not_exist") == 0

    def test_broken_unload_does_not_block_others(self):
        calls = []

        def broken():
            raise RuntimeError("boom")

        HOOK_LIFECYCLE["unload"]["bad-hook"] = broken
        HOOK_LIFECYCLE["unload"]["good-hook"] = lambda: calls.append("ok")
        fired = fire_hook_lifecycle("unload")
        assert fired == 2
        assert calls == ["ok"]

    def test_clear_removes_unload_callbacks(self, bound_api):
        bound_api.on_unload(lambda: None)
        assert HOOK_LIFECYCLE["unload"]
        clear_hook_registrations()
        assert not any(HOOK_LIFECYCLE.values())


class TestRegisterTimer:
    def test_register_valid_timer(self, bound_api):
        assert bound_api.register_timer(1.0, lambda: None) is True
        timers = HOOK_TIMERS["timer-hook"]
        assert len(timers) == 1
        assert timers[0]["interval"] == 1.0
        assert callable(timers[0]["fn"])

    def test_register_rejects_non_callable(self, bound_api):
        assert bound_api.register_timer(1.0, "not-callable") is False
        assert not HOOK_TIMERS

    def test_register_rejects_invalid_interval(self, bound_api):
        assert bound_api.register_timer("abc", lambda: None) is False
        assert not HOOK_TIMERS

    def test_interval_clamped_to_minimum(self, bound_api):
        bound_api.register_timer(0.001, lambda: None)
        assert HOOK_TIMERS["timer-hook"][0]["interval"] == 0.1

    def test_clear_registrations_removes_timers(self, bound_api):
        bound_api.register_timer(1.0, lambda: None)
        clear_hook_registrations()
        assert not HOOK_TIMERS


class TestTimerScheduler:
    def test_scheduler_runs_due_callbacks(self, bound_api):
        calls = []
        bound_api.register_timer(0.1, lambda: calls.append(time.monotonic()))
        start_timer_scheduler()
        deadline = time.monotonic() + 3.0
        while len(calls) < 2 and time.monotonic() < deadline:
            time.sleep(0.02)
        assert len(calls) >= 2
        assert calls[1] - calls[0] < 1.0  # ran again quickly (interval ~0.1s)

    def test_broken_timer_does_not_block_others(self, bound_api):
        def broken():
            raise RuntimeError("boom")

        calls = []
        bound_api.register_timer(0.1, broken)
        api2 = bound_api.for_hook("other-timer-hook")
        api2.register_timer(0.1, lambda: calls.append(1))
        start_timer_scheduler()
        deadline = time.monotonic() + 3.0
        while not calls and time.monotonic() < deadline:
            time.sleep(0.02)
        assert calls  # healthy timer kept running despite the broken one

    def test_stop_stops_execution(self, bound_api):
        calls = []
        bound_api.register_timer(0.1, lambda: calls.append(1))
        start_timer_scheduler()
        time.sleep(0.4)
        _stop_timer_thread()
        count_after_stop = len(calls)
        time.sleep(0.3)
        assert len(calls) <= count_after_stop + 1

    def test_start_without_timers_is_noop(self):
        # Must not raise and must not leave a thread behind.
        start_timer_scheduler()
