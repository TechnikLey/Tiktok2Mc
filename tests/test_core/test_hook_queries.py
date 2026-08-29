"""Tests for synchronous hook-to-hook queries.

``api.register_query(name, fn)`` exposes a handler; another hook calls it
via ``api.query_hook(target, query, args)``. In-process, inline execution;
exceptions are isolated (HOOK-0011) and unknown targets return ``None``.
"""

import asyncio

import pytest

from core.hook_api import (
    HOOK_ACTIONS,
    HOOK_EVENT_SUBSCRIPTIONS,
    HOOK_LIFECYCLE,
    HOOK_QUERIES,
    HOOK_TIMERS,
    HookAPI,
    clear_hook_registrations,
)


@pytest.fixture(autouse=True)
def _clean_state():
    saved = {
        "actions": dict(HOOK_ACTIONS),
        "lifecycle": {k: dict(v) for k, v in HOOK_LIFECYCLE.items()},
        "events": {k: dict(v) for k, v in HOOK_EVENT_SUBSCRIPTIONS.items()},
        "timers": {k: list(v) for k, v in HOOK_TIMERS.items()},
        "queries": {k: dict(v) for k, v in HOOK_QUERIES.items()},
    }
    clear_hook_registrations()
    yield
    clear_hook_registrations()
    HOOK_ACTIONS.update(saved["actions"])
    for key, value in saved["lifecycle"].items():
        HOOK_LIFECYCLE[key].update(value)
    for key, value in saved["events"].items():
        HOOK_EVENT_SUBSCRIPTIONS[key].update(value)
    for key, value in saved["timers"].items():
        HOOK_TIMERS[key] = value
    for key, value in saved["queries"].items():
        HOOK_QUERIES[key] = value


@pytest.fixture
def make_api():
    loop = asyncio.new_event_loop()

    def _make(hook_name: str) -> HookAPI:
        api = HookAPI(asyncio.Queue(), asyncio.Queue(), loop, {}, set())
        return api.for_hook(hook_name)

    yield _make


class TestHookQueries:
    def test_register_and_call(self, make_api):
        provider = make_api("provider")
        consumer = make_api("consumer")

        assert provider.register_query("top", lambda args: {"n": len(args)}) is True
        result = consumer.query_hook("provider", "top", {"x": 1})
        assert result == {"n": 1}

    def test_unknown_target_returns_none(self, make_api):
        consumer = make_api("consumer")
        assert consumer.query_hook("ghost", "anything") is None

    def test_unknown_query_returns_none(self, make_api):
        make_api("provider").register_query("known", lambda a: 1)
        consumer = make_api("consumer")
        assert consumer.query_hook("provider", "unknown") is None

    def test_broken_handler_isolated(self, make_api):
        def broken(args):
            raise RuntimeError("boom")

        make_api("bad").register_query("explode", broken)
        consumer = make_api("consumer")
        assert consumer.query_hook("bad", "explode", {}) is None

    def test_last_registration_wins(self, make_api):
        api = make_api("prov")
        api.register_query("q", lambda a: "first")
        api.register_query("q", lambda a: "second")
        assert make_api("caller").query_hook("prov", "q") == "second"

    def test_invalid_registrations_rejected(self, make_api):
        api = make_api("prov")
        assert api.register_query("", lambda a: 1) is False
        assert api.register_query("   ", lambda a: 1) is False
        assert api.register_query("nope", "not-callable") is False
        assert not HOOK_QUERIES

    def test_args_are_copied(self, make_api):
        seen = {}
        api = make_api("prov")

        def handler(args):
            seen.update(args)
            args["injected"] = True
            return True

        api.register_query("mutating", handler)
        payload = {"k": "v"}
        make_api("caller").query_hook("prov", "mutating", payload)
        assert seen == {"k": "v"}
        assert payload == {"k": "v"}  # caller dict not mutated

    def test_clear_removes_queries(self, make_api):
        make_api("prov").register_query("q", lambda a: None)
        clear_hook_registrations()
        assert not HOOK_QUERIES
