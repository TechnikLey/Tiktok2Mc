"""Unit tests for the outbound webhook dispatcher."""

from __future__ import annotations

import asyncio
import json

import pytest

import core.api.outbound_dispatcher as od
from core.api.outbound_dispatcher import (
    OutboundChannel,
    OutboundDispatcher,
    format_discord_message,
    load_outbound_channels,
    mask_url,
)
from core.overlay_base import OverlayClient


def _channel(name: str = "ch", **kwargs) -> OutboundChannel:
    defaults = {"url": "https://example.com/hook", "events": ["tiktok.*"]}
    defaults.update(kwargs)
    return OutboundChannel(
        name=name,
        breaker=OverlayClient(name=name, max_fails=3, cooldown=10),
        **defaults,
    )


# ---------------------------------------------------------------------------
#  Formatting / masking helpers
# ---------------------------------------------------------------------------


class TestFormatDiscord:
    def test_fills_user_type_and_data_keys(self):
        msg = format_discord_message(
            "**{user}** did {type} ({gift_id})",
            "tiktok.gift",
            {"user": "alice", "gift_id": 5},
        )
        assert msg == "**alice** did tiktok.gift (5)"

    def test_missing_keys_become_empty(self):
        msg = format_discord_message("[{user}]{comment}|{unknown}", "tiktok.follow", {})
        assert msg == "[]|"

    def test_non_string_values_are_json_encoded(self):
        msg = format_discord_message("{data}", "x", {"data": {"a": 1}})
        assert msg == '{"a": 1}'

    def test_empty_template_still_formats(self):
        assert format_discord_message("", "t", {}) == ""


class TestMaskUrl:
    def test_hides_path_query_and_userinfo(self):
        masked = mask_url(
            "https://user:secret@discord.com/api/webhooks/123/abc?wait=true"
        )
        assert masked == "https://user:secret@discord.com/<masked>"

    def test_invalid_url(self):
        assert mask_url("not-a-url") == "<invalid-url>"
        assert mask_url("") == "<invalid-url>"


# ---------------------------------------------------------------------------
#  Channel loading (pure config parsing)
# ---------------------------------------------------------------------------


class TestLoadChannels:
    def _section(self, channels=None, **extra):
        section = {
            "enabled": True,
            "max_fails": 2,
            "cooldown": 7,
            "retries": 2,
            "timeout": 4,
            "channels": channels if channels is not None else [],
        }
        section.update(extra)
        return {"outbound": section}

    def test_valid_entry_parsed_with_defaults(self):
        cfg = self._section(
            [
                {
                    "name": "dc",
                    "url": "https://example.com/x",
                    "events": ["tiktok.gift"],
                    "format": "discord",
                    "template": "{user}",
                    "enabled": True,
                }
            ]
        )
        channels = load_outbound_channels(cfg)
        ch = channels["dc"]
        assert ch.events == ["tiktok.gift"]
        assert ch.fmt == "discord"
        assert ch.retries == 2
        assert ch.timeout == 4
        assert ch.breaker is not None
        assert ch.breaker.max_fails == 2
        assert ch.breaker.cooldown == 7

    def test_master_disabled_yields_nothing(self):
        cfg = self._section([{"name": "x", "url": "https://e.com/"}], enabled=False)
        assert load_outbound_channels(cfg) == {}

    def test_missing_section_yields_nothing(self):
        assert load_outbound_channels({}) == {}

    def test_invalid_entries_skipped(self):
        cfg = self._section(
            [
                "not-a-dict",
                {"url": "https://e.com/"},  # no name
                {"name": "nourl"},  # no url
                {"name": "bad", "url": "ftp://e.com/"},  # unsupported scheme
            ]
        )
        assert load_outbound_channels(cfg) == {}

    def test_duplicate_name_keeps_first(self):
        cfg = self._section(
            [
                {"name": "dup", "url": "https://first.com/"},
                {"name": "dup", "url": "https://second.com/"},
            ]
        )
        channels = load_outbound_channels(cfg)
        assert list(channels) == ["dup"]
        assert channels["dup"].url == "https://first.com/"

    def test_unknown_format_falls_back_to_raw(self):
        cfg = self._section([{"name": "x", "url": "https://e.com/", "format": "xml"}])
        assert load_outbound_channels(cfg)["x"].fmt == "raw"

    def test_retries_and_timeout_are_floored(self):
        cfg = self._section(
            [{"name": "x", "url": "https://e.com/", "retries": -3, "timeout": 0.1}]
        )
        ch = load_outbound_channels(cfg)["x"]
        assert ch.retries == 0
        assert ch.timeout == 1.0

    def test_events_default_to_all(self):
        cfg = self._section([{"name": "x", "url": "https://e.com/"}])
        ch = load_outbound_channels(cfg)["x"]
        assert ch.matches("anything.at.all")
        assert not _channel(events=["tiktok.*"]).matches("system.started")


# ---------------------------------------------------------------------------
#  Dispatcher dispatch behaviour (_post patched — no real HTTP)
# ---------------------------------------------------------------------------


@pytest.fixture()
def dispatcher(monkeypatch):
    """Fresh dispatcher with a no-op _post and instant retries."""
    monkeypatch.setattr(od, "RETRY_DELAY", 0)
    calls: list[tuple[str, bytes]] = []

    def fake_post(url: str, body: bytes, timeout: float) -> int:
        calls.append((url, body))
        return 200

    monkeypatch.setattr(OutboundDispatcher, "_post", staticmethod(fake_post))
    d = OutboundDispatcher()
    d._master_enabled = True
    d._channels = {}
    return d, calls


class TestDispatch:
    async def test_delivers_to_matching_channel_only(self, dispatcher):
        d, calls = dispatcher
        d._channels = {
            "hit": _channel("hit", events=["tiktok.*"]),
            "miss": _channel("miss", events=["system.*"]),
        }
        d._dispatch({"type": "tiktok.gift", "data": {"user": "u"}, "timestamp": 1.0})
        await _drain_inflight(d)
        assert [name for name, _ in calls] == ["https://example.com/hook"]
        assert d.status()["channels"][0]["sent"] == 1

    async def test_non_matching_event_sends_nothing(self, dispatcher):
        d, calls = dispatcher
        d._channels = {"ch": _channel("ch", events=["tiktok.gift"])}
        d._dispatch({"type": "tiktok.like", "data": {}, "timestamp": 1.0})
        await _drain_inflight(d)
        assert calls == []

    async def test_master_switch_blocks_delivery(self, dispatcher):
        d, calls = dispatcher
        d._master_enabled = False
        d._channels = {"ch": _channel()}
        d._dispatch({"type": "tiktok.gift", "data": {}, "timestamp": 1.0})
        await _drain_inflight(d)
        assert calls == []

    async def test_open_breaker_drops_without_send(self, dispatcher):
        d, calls = dispatcher
        ch = _channel("tripped")
        assert ch.breaker is not None
        for _ in range(3):
            ch.breaker.mark_failure()
        d._channels = {"tripped": ch}
        d._dispatch({"type": "tiktok.gift", "data": {}, "timestamp": 1.0})
        await _drain_inflight(d)
        assert calls == []
        status = d.status()["channels"][0]
        assert status["dropped"] == 1
        assert status["breaker_open"] is True

    async def test_payload_is_json_envelope_for_raw(self, dispatcher):
        d, calls = dispatcher
        ch = _channel("raw", fmt="raw")
        d._channels = {ch.name: ch}
        d._dispatch(
            {"type": "tiktok.comment", "data": {"user": "bob"}, "timestamp": 42.0}
        )
        await _drain_inflight(d)
        body = json.loads(calls[0][1])
        assert body == {
            "type": "tiktok.comment",
            "data": {"user": "bob"},
            "timestamp": 42.0,
        }

    async def test_payload_uses_template_for_discord(self, dispatcher):
        d, calls = dispatcher
        ch = _channel("dc", fmt="discord", template="{user}: {comment}")
        d._channels = {ch.name: ch}
        d._dispatch(
            {
                "type": "tiktok.comment",
                "data": {"user": "bob", "comment": "hi"},
                "timestamp": 1.0,
            }
        )
        await _drain_inflight(d)
        assert json.loads(calls[0][1]) == {"content": "bob: hi"}


async def _drain_inflight(dispatcher: OutboundDispatcher) -> None:
    """Wait until the dispatcher has no inflight delivery tasks left."""
    for _ in range(100):
        if not dispatcher._inflight:
            return
        await asyncio.sleep(0)
    raise AssertionError("delivery tasks never settled")


# ---------------------------------------------------------------------------
#  Retries + circuit breaker interaction
# ---------------------------------------------------------------------------


class TestDeliverRetries:
    async def test_all_attempts_fail_marks_failure_once(self, dispatcher, monkeypatch):
        d, _ = dispatcher
        attempts: list[int] = []

        def failing_post(url: str, body: bytes, timeout: float) -> int:
            attempts.append(1)
            raise OSError("boom")

        monkeypatch.setattr(OutboundDispatcher, "_post", staticmethod(failing_post))
        ch = _channel("flaky", retries=2)
        d._channels = {ch.name: ch}
        await d._deliver(ch, b"x")
        assert len(attempts) == 3  # initial + 2 retries
        assert ch.failed_count == 1
        assert ch.sent_count == 0
        assert ch.breaker is not None and ch.breaker._fail_count == 1

    async def test_retry_then_success_counts_sent(self, dispatcher, monkeypatch):
        d, _ = dispatcher
        results = [OSError("down"), 200]

        def flaky_post(url: str, body: bytes, timeout: float) -> int:
            r = results.pop(0)
            if isinstance(r, Exception):
                raise r
            return r

        monkeypatch.setattr(OutboundDispatcher, "_post", staticmethod(flaky_post))
        ch = _channel("flaky", retries=1)
        await d._deliver(ch, b"x")
        assert ch.sent_count == 1
        assert ch.failed_count == 0
        assert ch.breaker is not None and ch.breaker._fail_count == 0


# ---------------------------------------------------------------------------
#  Manual test probe
# ---------------------------------------------------------------------------


class TestSendTest:
    async def test_unknown_channel_raises_lookup_error(self, dispatcher):
        d, _ = dispatcher
        with pytest.raises(LookupError):
            await d.send_test("ghost")

    async def test_disabled_channel_refuses(self, dispatcher):
        d, calls = dispatcher
        d._channels = {"off": _channel("off", enabled=False)}
        ok, detail = await d.send_test("off")
        assert ok is False
        assert "disabled" in detail
        assert calls == []

    async def test_successful_probe_does_not_touch_counters(self, dispatcher):
        d, calls = dispatcher
        ch = _channel("probe", fmt="raw")
        d._channels = {ch.name: ch}
        ok, detail = await d.send_test("probe")
        assert ok is True
        assert "delivered" in detail
        assert ch.sent_count == 0 and ch.failed_count == 0 and ch.dropped_count == 0
        body = json.loads(calls[0][1])
        assert body["type"] == "outbound.test"

    async def test_failed_probe_reports_detail(self, dispatcher, monkeypatch):
        d, _ = dispatcher

        def failing_post(url: str, body: bytes, timeout: float) -> int:
            raise OSError("nope")

        monkeypatch.setattr(OutboundDispatcher, "_post", staticmethod(failing_post))
        ch = _channel("probe")
        d._channels = {ch.name: ch}
        ok, detail = await d.send_test("probe")
        assert ok is False
        assert "delivery failed" in detail


# ---------------------------------------------------------------------------
#  Status + lifecycle
# ---------------------------------------------------------------------------


class TestStatusAndLifecycle:
    async def test_status_masks_urls(self, dispatcher):
        d, _ = dispatcher
        ch = _channel("s", url="https://secret-host.tld/private/path?key=1")
        d._channels = {ch.name: ch}
        entry = d.status()["channels"][0]
        assert entry["url"] == "https://secret-host.tld/<masked>"
        assert "/private/path" not in entry["url"]

    async def test_start_stop_roundtrip(self, dispatcher, monkeypatch):
        d, calls = dispatcher
        from core.api.eventbus import event_bus

        monkeypatch.setattr(od, "load_outbound_config", lambda: {"enabled": True})
        monkeypatch.setattr(
            od,
            "load_outbound_channels",
            lambda cfg: {"ch": _channel("ch", events=["system.*"])},
        )
        d.start()
        try:
            await asyncio.sleep(0)  # let the loop task subscribe first
            await event_bus.publish("system.started", {})
            for _ in range(50):
                if calls:
                    break
                await asyncio.sleep(0)
            assert calls, "event was not delivered"
            assert d.status()["enabled"] is True
        finally:
            await d.stop()

    async def test_stop_cancels_inflight(self, dispatcher, monkeypatch):
        d, _ = dispatcher
        import threading

        started = threading.Event()
        finished = threading.Event()

        def slow_post(url: str, body: bytes, timeout: float) -> int:
            started.set()
            import time as _time

            _time.sleep(0.3)
            finished.set()
            return 200

        monkeypatch.setattr(od, "RETRY_DELAY", 0)
        monkeypatch.setattr(OutboundDispatcher, "_post", staticmethod(slow_post))
        ch = _channel("slow")
        d._channels = {ch.name: ch}
        task = asyncio.create_task(d._deliver(ch, b"x"))
        d._inflight.add(task)
        task.add_done_callback(d._inflight.discard)
        for _ in range(100):
            if started.is_set():
                break
            await asyncio.sleep(0.02)
        assert started.is_set(), "delivery never started"
        await asyncio.wait_for(d.stop(), timeout=5)
        assert task.done()
        assert not d._inflight
        assert ch.sent_count == 1
