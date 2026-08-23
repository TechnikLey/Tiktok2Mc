"""Tests for the NotificationDispatcher (J.3 Nr. 13).

Covers channel resolution (defaults, overrides, unknown channels),
fan-out bookkeeping (sent/failed/skipped) and the REST surface.
Channel handlers are replaced with fakes — no real overlay, audio,
TTS or HTTP is touched.
"""

import json

import pytest


@pytest.fixture
def dispatcher(monkeypatch):
    """A fresh dispatcher with config loading stubbed out."""
    from core.api.notification_dispatcher import NotificationDispatcher

    monkeypatch.setattr(
        "core.api.notification_dispatcher.load_notification_config",
        lambda: {},
    )
    return NotificationDispatcher()


@pytest.fixture
def fake_handlers(monkeypatch):
    """Replace built-in handlers with recorders.

    Returns ``{"calls": [...], "install": fn}`` — each call is recorded as
    ``(title, body, level, config)`` with a copy of the received params.
    """
    import core.api.notification_dispatcher as mod

    calls: list[tuple[str, str, str, dict]] = []

    def make(ok: bool):
        def handler(title, body, level, config):
            calls.append((title, body, level, dict(config)))
            return ok

        return handler

    def install(name: str, ok: bool = True):
        handler = make(ok)
        monkeypatch.setitem(mod.CHANNEL_HANDLERS, name, handler)
        return handler

    return {"calls": calls, "install": install}


class TestResolveChannels:
    def test_no_config_falls_back_to_log(self, dispatcher):
        targets, skipped = dispatcher.resolve_channels(None)
        assert targets == ["log"]
        assert skipped == []

    def test_explicit_channels(self, dispatcher, fake_handlers):
        fake_handlers["install"]("overlay")
        fake_handlers["install"]("discord")
        targets, skipped = dispatcher.resolve_channels(["overlay", "discord"])
        assert targets == ["overlay", "discord"]
        assert skipped == []

    def test_unknown_channel_warned_and_skipped(
        self, dispatcher, fake_handlers, caplog
    ):
        import logging

        fake_handlers["install"]("log")
        with caplog.at_level(logging.WARNING):
            targets, skipped = dispatcher.resolve_channels(["log", "carrier-pigeon"])
        assert targets == ["log"]
        assert skipped == ["carrier-pigeon"]
        assert "NOTIF-0002" in caplog.text
        assert "carrier-pigeon" in caplog.text

    def test_disabled_dispatcher_skips_everything(self, dispatcher, monkeypatch):
        monkeypatch.setattr(
            "core.api.notification_dispatcher.load_notification_config",
            lambda: {"enabled": False},
        )
        dispatcher.reload()
        targets, skipped = dispatcher.resolve_channels(None)
        assert targets == []
        assert skipped == ["log"]


class TestNotify:
    @pytest.mark.asyncio
    async def test_fan_out_records_results(self, dispatcher, fake_handlers):
        fake_handlers["install"]("good")
        fake_handlers["install"]("bad", ok=False)

        result = await dispatcher.notify(
            "Hello", body="World", channels=["good", "bad"]
        )

        assert result["sent"] == ["good"]
        assert result["failed"] == ["bad"]
        assert result["skipped"] == []
        assert len(fake_handlers["calls"]) == 2
        title, body, level, _tag = fake_handlers["calls"][0]
        assert (title, body, level) == ("Hello", "World", "info")

    @pytest.mark.asyncio
    async def test_handler_exception_counts_as_failed(self, dispatcher, monkeypatch):
        import core.api.notification_dispatcher as mod

        def exploding(title, body, level, config):
            raise RuntimeError("boom")

        monkeypatch.setitem(mod.CHANNEL_HANDLERS, "exploding", exploding)
        result = await dispatcher.notify("Hi", channels=["exploding"])
        assert result["failed"] == ["exploding"]
        assert result["sent"] == []


class TestInlineChannelParams:
    """Per-request params let plugins/hooks stay self-contained."""

    @pytest.mark.asyncio
    async def test_inline_params_reach_handler(self, dispatcher, fake_handlers):
        fake_handlers["install"]("discord")

        result = await dispatcher.notify(
            "Hi",
            channels={"discord": {"webhook_url": "https://example.com/hook"}},
        )

        assert result == {"sent": ["discord"], "failed": [], "skipped": []}
        _, _, _, cfg = fake_handlers["calls"][0]
        assert cfg == {"webhook_url": "https://example.com/hook"}

    @pytest.mark.asyncio
    async def test_inline_params_override_global(self, monkeypatch):
        import core.api.notification_dispatcher as mod

        monkeypatch.setattr(
            mod,
            "load_notification_config",
            lambda: {
                "enabled": True,
                "channels": {"overlay": {"duration": 4, "overlay_name": "default"}},
            },
        )
        dispatcher = mod.NotificationDispatcher()
        captured: dict = {}

        def handler(title, body, level, config):
            captured.update(config)
            return True

        monkeypatch.setitem(mod.CHANNEL_HANDLERS, "overlay", handler)
        await dispatcher.notify("Hi", channels={"overlay": {"duration": 9}})
        assert captured == {"duration": 9, "overlay_name": "default"}

    @pytest.mark.asyncio
    async def test_unknown_channel_in_dict_skipped(
        self, dispatcher, fake_handlers, caplog
    ):
        import logging

        fake_handlers["install"]("log")
        with caplog.at_level(logging.WARNING):
            result = await dispatcher.notify(
                "Hi", channels={"log": {}, "smoke-signal": {}}
            )
        assert result["sent"] == ["log"]
        assert result["skipped"] == ["smoke-signal"]
        assert "NOTIF-0002" in caplog.text

    @pytest.mark.asyncio
    async def test_empty_params_dict_is_valid(self, dispatcher, fake_handlers):
        handler = fake_handlers["install"]("sound")
        result = await dispatcher.notify("Hi", channels={"sound": {}})
        assert result["sent"] == ["sound"]
        assert fake_handlers["calls"][0][3] == {}


class TestBuiltInHandlers:
    def test_log_handler_returns_true(self, caplog):
        import logging

        from core.api.notification_dispatcher import _send_log

        with caplog.at_level(logging.INFO):
            assert _send_log("Title", "Body", "info", {}) is True
        assert "[NOTIF] Title — Body" in caplog.text

    def test_sound_missing_file_fails(self, monkeypatch):
        from core.api.notification_dispatcher import _send_sound

        result = _send_sound("t", "", "info", {"file": "does/not/exist.wav"})
        assert result is False

    def test_discord_invalid_webhook_fails(self):
        from core.api.notification_dispatcher import _send_discord

        assert _send_discord("t", "", "info", {"webhook_url": ""}) is False

    def test_discord_posts_content(self, monkeypatch):
        import core.api.notification_dispatcher as mod

        sent = {}

        class FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read(self):
                return b""

        def fake_urlopen(req, timeout=None):
            sent["url"] = req.full_url
            sent["body"] = json.loads(req.data.decode())
            return FakeResp()

        monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)
        ok = mod._send_discord(
            "Title",
            "Body",
            "info",
            {"webhook_url": "https://discord.com/api/webhooks/abc/def"},
        )
        assert ok is True
        assert sent["body"] == {"content": "**Title**\nBody"}
        assert sent["url"].startswith("https://discord.com/api/webhooks/")


class TestNotificationRoutes:
    def test_send_notification_endpoint(self, client, monkeypatch):
        from core.api.notification_dispatcher import (
            NotificationDispatcher,
            get_notification_dispatcher,
        )

        async def fake_notify(self, title, body="", level="info", channels=None):
            return {"sent": ["log"], "failed": [], "skipped": []}

        monkeypatch.setattr(NotificationDispatcher, "notify", fake_notify)
        resp = client.post(
            "/api/v1/notifications",
            json={"title": "Test", "body": "Hello", "channels": ["log"]},
        )
        assert resp.status_code == 200
        assert resp.json() == {
            "sent": ["log"],
            "failed": [],
            "skipped": [],
        }
        # Touch the singleton so it exists in this process.
        assert get_notification_dispatcher() is not None

    def test_send_notification_accepts_inline_channels(self, client, monkeypatch):
        from core.api.notification_dispatcher import NotificationDispatcher

        captured: dict = {}

        async def fake_notify(self, title, body="", level="info", channels=None):
            captured["channels"] = channels
            return {"sent": ["discord"], "failed": [], "skipped": []}

        monkeypatch.setattr(NotificationDispatcher, "notify", fake_notify)
        resp = client.post(
            "/api/v1/notifications",
            json={
                "title": "T",
                "channels": {"discord": {"webhook_url": "https://x/y"}},
            },
        )
        assert resp.status_code == 200
        assert captured["channels"] == {"discord": {"webhook_url": "https://x/y"}}

    def test_channels_endpoint(self, client):
        resp = client.get("/api/v1/notifications/channels")
        assert resp.status_code == 200
        body = resp.json()
        assert "enabled" in body
        assert "log" in body["built_in"]

    def test_reload_endpoint(self, client):
        resp = client.post("/api/v1/notifications/reload")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_title_required(self, client):
        resp = client.post("/api/v1/notifications", json={})
        assert resp.status_code == 422
