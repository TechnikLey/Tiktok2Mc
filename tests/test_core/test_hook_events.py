"""Tests for B.3 #2/#7: hook event subscriptions and publishing.

Hooks can subscribe to bus events via ``api.register_event(pattern, fn)``
(fan-out happens in the bridge's background executor) and publish custom
events under their own namespace via ``api.publish_event()``.
"""

import asyncio
import json
from unittest.mock import patch

import pytest

from core.hook_api import (
    HOOK_EVENT_SUBSCRIPTIONS,
    HookAPI,
    clear_hook_registrations,
)
from core.hook_loader import fire_hook_event, matching_event_hooks


@pytest.fixture(autouse=True)
def _clean_subscriptions():
    saved = {k: dict(v) for k, v in HOOK_EVENT_SUBSCRIPTIONS.items()}
    HOOK_EVENT_SUBSCRIPTIONS.clear()
    yield
    HOOK_EVENT_SUBSCRIPTIONS.clear()
    HOOK_EVENT_SUBSCRIPTIONS.update(saved)


@pytest.fixture
def api():
    loop = asyncio.new_event_loop()
    rcon_q = asyncio.Queue()
    trigger_q = asyncio.Queue()
    return HookAPI(rcon_q, trigger_q, loop, {}, set(), {})


@pytest.fixture
def bound_api(api):
    view = api.for_hook("combo-hook", permissions=["events"])
    return view


class TestRegisterEvent:
    def test_exact_pattern_registration(self, bound_api):
        calls = []
        bound_api.register_event("tiktok.gift", lambda t, d: calls.append((t, d)))
        assert "tiktok.gift" in HOOK_EVENT_SUBSCRIPTIONS

    def test_fire_matches_exact(self, bound_api):
        seen = []
        bound_api.register_event("tiktok.gift", lambda t, d: seen.append(t))
        assert fire_hook_event("tiktok.gift", {"user": "x"}) == 1
        assert seen == ["tiktok.gift"]

    def test_fire_matches_prefix_wildcard(self, bound_api):
        seen = []
        bound_api.register_event("minecraft.*", lambda t, d: seen.append(t))
        assert fire_hook_event("minecraft.player_death", {}) == 1
        assert seen == ["minecraft.player_death"]
        assert fire_hook_event("tiktok.follow", {}) == 0

    def test_fire_matches_catch_all(self, bound_api):
        seen = []
        bound_api.register_event("*", lambda t, d: seen.append(t))
        matching_event_hooks("tiktok.like")
        assert fire_hook_event("tiktok.like", {}) == 1
        assert seen == ["tiktok.like"]

    def test_handler_receives_data_copy(self, bound_api):
        seen = []
        bound_api.register_event("tiktok.gift", lambda t, d: seen.append(d))
        data = {"user": "alice"}
        fire_hook_event("tiktok.gift", data)
        assert seen[0] == data
        assert seen[0] is not data

    def test_broken_handler_does_not_block_others(self, api, bound_api):
        def broken(t, d):
            raise RuntimeError("boom")

        ok_calls = []
        api2 = api.for_hook("other-hook")
        api2.register_event("tiktok.*", broken)
        bound_api.register_event("tiktok.*", lambda t, d: ok_calls.append(t))
        fired = fire_hook_event("tiktok.follow", {})
        assert fired == 2
        assert ok_calls == ["tiktok.follow"]

    def test_clear_registrations_removes_subscriptions(self, bound_api):
        bound_api.register_event("tiktok.gift", lambda t, d: None)
        assert HOOK_EVENT_SUBSCRIPTIONS
        clear_hook_registrations()
        assert not HOOK_EVENT_SUBSCRIPTIONS

    def test_invalid_pattern_ignored(self, bound_api):
        bound_api.register_event("", lambda t, d: None)
        bound_api.register_event("tiktok.gift", None)
        assert not HOOK_EVENT_SUBSCRIPTIONS


class TestPublishEvent:
    def test_publish_namespaced_event(self, bound_api):
        captured = {}

        class FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return b'{"status": "ok"}'

        def fake_urlopen(req, timeout=None):
            captured["url"] = req.full_url
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return FakeResp()

        with patch("urllib.request.urlopen", fake_urlopen):
            assert bound_api.publish_event("combo-hook.milestone", {"n": 5}) is True
        assert captured["url"].endswith("/api/v1/events")
        assert captured["body"] == {
            "type": "combo-hook.milestone",
            "data": {"n": 5},
        }

    def test_publish_rejects_foreign_namespace(self, bound_api, caplog):
        with patch("urllib.request.urlopen") as mock_open:
            assert bound_api.publish_event("tiktok.gift", {}) is False
        mock_open.assert_not_called()

    def test_publish_requires_permission(self, api):
        view = api.for_hook("no-perm", permissions=["store"])
        with patch("urllib.request.urlopen") as mock_open:
            assert view.publish_event("no-perm.thing", {}) is False
        mock_open.assert_not_called()

    def test_publish_invalid_type_rejected(self, bound_api):
        with patch("urllib.request.urlopen") as mock_open:
            assert bound_api.publish_event("", {}) is False
        mock_open.assert_not_called()
