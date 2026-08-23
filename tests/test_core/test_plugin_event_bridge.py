"""Tests for the API-side PluginEventBridge.

Covers manifest declaration loading, subscription pattern matching,
tiktok_event dispatch and comment_handler delivery — the replacement
for the historical bridge-local event bridge that enqueued into an
orphaned in-process command queue.
"""

import json
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def plugins_dir(tmp_path):
    """Create a fake plugins directory with manifests."""
    root = tmp_path / "plugins"
    root.mkdir()
    return root


def _make_plugin(plugins_dir, name, manifest_extra=None):
    plugin_dir = plugins_dir / name
    plugin_dir.mkdir()
    manifest = {"name": name, "entry_point": f"{name}.py"}
    if manifest_extra:
        manifest.update(manifest_extra)
    (plugin_dir / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
    return plugin_dir


# =========================================================================
# match_event
# =========================================================================


class TestMatchEvent:
    def test_exact_match(self):
        from core.api.plugin_event_bridge import match_event

        assert match_event("tiktok.gift", "tiktok.gift") is True

    def test_wildcard_match(self):
        from core.api.plugin_event_bridge import match_event

        assert match_event("tiktok.gift", "tiktok.*") is True
        assert match_event("tiktok.comment", "tiktok.*") is True
        assert match_event("minecraft.player_death", "minecraft.*") is True

    def test_catch_all_match(self):
        from core.api.plugin_event_bridge import match_event

        assert match_event("tiktok.gift", "*") is True
        assert match_event("server.started", "*") is True
        assert match_event("anything", "*") is True

    def test_no_match(self):
        from core.api.plugin_event_bridge import match_event

        assert match_event("minecraft.player_death", "tiktok.*") is False
        assert match_event("tiktok.like", "tiktok.gift") is False

    def test_wildcard_requires_dot(self):
        from core.api.plugin_event_bridge import match_event

        assert match_event("tiktoklike", "tiktok.*") is False


# =========================================================================
# load_manifest_declarations
# =========================================================================


class TestLoadManifestDeclarations:
    def test_empty_dir(self, tmp_path):
        from core.api.plugin_event_bridge import load_manifest_declarations

        subs, handlers = load_manifest_declarations(tmp_path / "missing")
        assert subs == {}
        assert handlers == {}

    def test_subscriptions_collected(self, plugins_dir):
        from core.api.plugin_event_bridge import load_manifest_declarations

        _make_plugin(
            plugins_dir,
            "alpha",
            {"event_subscriptions": ["tiktok.gift", "tiktok.*"]},
        )
        _make_plugin(plugins_dir, "beta", {"event_subscriptions": ["tiktok.gift"]})

        subs, handlers = load_manifest_declarations(plugins_dir)

        assert subs["tiktok.gift"] == ["alpha", "beta"]
        assert subs["tiktok.*"] == ["alpha"]
        assert handlers == {}

    def test_comment_handler_enabled(self, plugins_dir):
        from core.api.plugin_event_bridge import load_manifest_declarations

        _make_plugin(
            plugins_dir, "tts", {"comment_handler": {"prefix": "$", "enabled": True}}
        )

        _, handlers = load_manifest_declarations(plugins_dir)
        assert handlers == {"tts": {"prefix": "$"}}

    def test_comment_handler_disabled(self, plugins_dir):
        from core.api.plugin_event_bridge import load_manifest_declarations

        _make_plugin(
            plugins_dir, "tts", {"comment_handler": {"prefix": "$", "enabled": False}}
        )

        _, handlers = load_manifest_declarations(plugins_dir)
        assert handlers == {}

    def test_comment_handler_defaults(self, plugins_dir):
        """Missing prefix falls back to '$'; missing enabled counts as on."""
        from core.api.plugin_event_bridge import (
            DEFAULT_COMMENT_PREFIX,
            load_manifest_declarations,
        )

        _make_plugin(plugins_dir, "tts", {"comment_handler": {}})

        _, handlers = load_manifest_declarations(plugins_dir)
        assert handlers == {"tts": {"prefix": DEFAULT_COMMENT_PREFIX}}


# =========================================================================
# Dispatch logic (command_queue mocked)
# =========================================================================


class TestDispatch:
    @pytest.fixture
    def bridge(self):
        from core.api.plugin_event_bridge import PluginEventBridge

        return PluginEventBridge()

    @pytest.fixture
    def enqueued(self, monkeypatch):
        calls = []

        def fake_enqueue(plugin_name, command, **kwargs):
            calls.append({"target": plugin_name, "command": command, **kwargs})
            return "fake-id"

        monkeypatch.setattr(
            "core.api.plugin_overlay.command_queue",
            MagicMock(enqueue=fake_enqueue),
        )
        return calls

    def test_non_tiktok_event_delivered_as_bus_event(self, bridge, enqueued):
        """J.3 #14: generic bus sources reach subscribers without a user."""
        bridge._subscriptions = {"minecraft.player_death": ["death-ui"]}

        bridge._dispatch(
            "minecraft.player_death", {"player": "Steve", "message": "died"}
        )

        assert len(enqueued) == 1
        cmd = enqueued[0]
        assert cmd["target"] == "death-ui"
        assert cmd["command"] == "bus_event"
        assert cmd["event_type"] == "minecraft.player_death"
        assert cmd["data"] == {"player": "Steve", "message": "died"}

    def test_bus_wildcard_subscription(self, bridge, enqueued):
        bridge._subscriptions = {"minecraft.*": ["mc-logger"]}

        bridge._dispatch("minecraft.player_respawn", {"player": "Steve"})

        assert len(enqueued) == 1
        assert enqueued[0]["target"] == "mc-logger"
        assert enqueued[0]["command"] == "bus_event"

    def test_catch_all_subscription_receives_everything(self, bridge, enqueued):
        bridge._subscriptions = {"*": ["audit-log"]}

        bridge._dispatch("server.started", {"port": 25565})
        bridge._dispatch("tiktok.gift", {"user": "fan", "gift_id": "5299"})

        commands = [c["command"] for c in enqueued]
        assert commands.count("bus_event") == 1
        assert commands.count("tiktok_event") == 1

    def test_unsubscribed_bus_event_ignored(self, bridge, enqueued):
        bridge._subscriptions = {"tiktok.*": ["alpha"]}

        bridge._dispatch("timer.tick", {"name": "pomodoro"})
        assert enqueued == []

    def test_dispatches_to_subscribers(self, bridge, enqueued):
        bridge._subscriptions = {"tiktok.gift": ["alpha"], "tiktok.*": ["beta"]}

        bridge._dispatch("tiktok.gift", {"user": "fan", "gift_id": "5299"})

        targets = [(c["target"], c["command"]) for c in enqueued]
        assert ("alpha", "tiktok_event") in targets
        assert ("beta", "tiktok_event") in targets
        cmd = next(c for c in enqueued if c["target"] == "alpha")
        assert cmd["event_type"] == "tiktok.gift"
        assert cmd["user"] == "fan"
        assert cmd["data"] == {"gift_id": "5299"}

    def test_no_recipients_no_enqueue(self, bridge, enqueued):
        bridge._subscriptions = {"tiktok.like": ["alpha"]}

        bridge._dispatch("tiktok.gift", {"user": "fan"})
        assert enqueued == []

    def test_missing_user_skipped(self, bridge, enqueued):
        bridge._subscriptions = {"tiktok.*": ["alpha"]}

        bridge._dispatch("tiktok.gift", {})
        assert enqueued == []

    def test_comment_handler_strips_prefix(self, bridge, enqueued):
        bridge._comment_handlers = {"tts": {"prefix": "$"}}

        bridge._dispatch("tiktok.comment", {"user": "fan", "comment": "$play halo"})

        assert len(enqueued) == 1
        assert enqueued[0]["target"] == "tts"
        assert enqueued[0]["command"] == "comment"
        assert enqueued[0]["text"] == "play halo"
        assert enqueued[0]["username"] == "fan"

    def test_comment_without_matching_prefix_ignored(self, bridge, enqueued):
        bridge._comment_handlers = {"tts": {"prefix": "$"}}

        bridge._dispatch("tiktok.comment", {"user": "fan", "comment": "hello"})

        assert enqueued == []

    def test_comment_and_subscription_independent(self, bridge, enqueued):
        """A plugin subscribed to tiktok.comment gets the raw event;
        a comment_handler plugin gets the parsed comment."""
        bridge._subscriptions = {"tiktok.comment": ["logger"]}
        bridge._comment_handlers = {"tts": {"prefix": "$"}}

        bridge._dispatch("tiktok.comment", {"user": "fan", "comment": "$hi"})

        commands = sorted(c["command"] for c in enqueued)
        assert commands == ["comment", "tiktok_event"]

    def test_non_comment_events_skip_comment_handlers(self, bridge, enqueued):
        bridge._comment_handlers = {"tts": {"prefix": "$"}}

        bridge._dispatch("tiktok.follow", {"user": "fan"})
        assert enqueued == []


# =========================================================================
# Lifecycle
# =========================================================================


class TestLifecycle:
    def test_singleton(self):
        from core.api.plugin_event_bridge import get_plugin_event_bridge

        assert get_plugin_event_bridge() is get_plugin_event_bridge()

    def test_start_loads_subscriptions(self, monkeypatch, tmp_path):
        import asyncio

        import core.api.plugin_event_bridge as mod
        from core.api.plugin_event_bridge import PluginEventBridge

        _make_plugin(tmp_path, "alpha", {"event_subscriptions": ["tiktok.*"]})
        monkeypatch.setattr(mod, "discover_plugins_dir", lambda: tmp_path)

        bridge = PluginEventBridge()

        created = {}

        def fake_create_task(coro):
            created["coro"] = coro
            coro.close()  # never run it
            return MagicMock()

        monkeypatch.setattr(asyncio, "create_task", fake_create_task)
        bridge.start()

        assert bridge._running is True
        assert bridge._subscriptions == {"tiktok.*": ["alpha"]}
        assert bridge._task is not None

        # Cleanup: mark stopped so health monitor state stays sane
        bridge._running = False


# =========================================================================
# End-to-end: real EventBus → bridge loop → real CommandQueue
# =========================================================================


class TestEndToEndDelivery:
    """Integration test (J.1 #3): a real tiktok.comment published on the
    API-side EventBus must land as commands in the CommandQueue plugins poll."""

    @pytest.mark.asyncio
    async def test_real_comment_reaches_plugin_queue(self):
        import asyncio
        import contextlib
        import time

        from core.api.eventbus import event_bus
        from core.api.plugin_event_bridge import PluginEventBridge
        from core.api.plugin_overlay import command_queue

        command_queue.clear("e2e-tts")

        bridge = PluginEventBridge()
        bridge._subscriptions = {"tiktok.comment": ["e2e-tts"]}
        bridge._comment_handlers = {"e2e-tts": {"prefix": "$"}}
        bridge._running = True

        task = asyncio.create_task(bridge._loop())
        cmds: list[dict] = []
        try:
            # Yield once so the loop task reaches its subscribe() call.
            await asyncio.sleep(0)
            await event_bus.publish(
                "tiktok.comment", {"user": "fan", "comment": "$play halo"}
            )
            deadline = time.time() + 2.0
            while time.time() < deadline:
                cmds = command_queue.dequeue_all("e2e-tts")
                if len(cmds) >= 2:
                    break
                await asyncio.sleep(0.02)
        finally:
            bridge._running = False
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

        by_cmd = {c["command"]: c for c in cmds}
        assert "tiktok_event" in by_cmd, f"commands seen: {cmds}"
        assert "comment" in by_cmd, f"commands seen: {cmds}"

        ev = by_cmd["tiktok_event"]
        assert ev["args"]["event_type"] == "tiktok.comment"
        assert ev["args"]["user"] == "fan"
        assert ev["args"]["data"] == {"comment": "$play halo"}
        assert all(k in ev for k in ("id", "timestamp"))

        comment = by_cmd["comment"]
        assert comment["args"] == {"text": "play halo", "username": "fan"}

    @pytest.mark.asyncio
    async def test_unsubscribed_plugin_receives_nothing(self):
        import asyncio
        import contextlib

        from core.api.eventbus import event_bus
        from core.api.plugin_event_bridge import PluginEventBridge
        from core.api.plugin_overlay import command_queue

        command_queue.clear("e2e-other")
        bridge = PluginEventBridge()
        bridge._subscriptions = {"tiktok.gift": ["e2e-other"]}
        bridge._running = True

        task = asyncio.create_task(bridge._loop())
        try:
            await asyncio.sleep(0)
            await event_bus.publish(
                "tiktok.comment", {"user": "fan", "comment": "hello"}
            )
            for _ in range(5):
                await asyncio.sleep(0.03)
            cmds = command_queue.dequeue_all("e2e-other")
        finally:
            bridge._running = False
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

        assert cmds == []

    @pytest.mark.asyncio
    async def test_real_minecraft_event_reaches_plugin_queue(self):
        """J.3 #14: a non-TikTok bus event lands as ``bus_event``."""
        import asyncio
        import contextlib
        import time

        from core.api.eventbus import event_bus
        from core.api.plugin_event_bridge import PluginEventBridge
        from core.api.plugin_overlay import command_queue

        command_queue.clear("e2e-mc")
        bridge = PluginEventBridge()
        bridge._subscriptions = {"minecraft.player_death": ["e2e-mc"]}
        bridge._running = True

        task = asyncio.create_task(bridge._loop())
        cmds: list[dict] = []
        try:
            await asyncio.sleep(0)
            await event_bus.publish(
                "minecraft.player_death", {"player": "Steve", "message": "boom"}
            )
            deadline = time.time() + 2.0
            while time.time() < deadline:
                cmds = command_queue.dequeue_all("e2e-mc")
                if cmds:
                    break
                await asyncio.sleep(0.02)
        finally:
            bridge._running = False
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

        assert len(cmds) == 1
        cmd = cmds[0]
        assert cmd["command"] == "bus_event"
        assert cmd["args"]["event_type"] == "minecraft.player_death"
        assert cmd["args"]["data"] == {"player": "Steve", "message": "boom"}
