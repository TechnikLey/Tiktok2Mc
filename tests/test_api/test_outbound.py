"""API tests for the outbound channel endpoints."""

from __future__ import annotations

import pytest

import core.api.outbound_dispatcher as od
from core.api.outbound_dispatcher import OutboundChannel, OutboundDispatcher
from core.overlay_base import OverlayClient


def _channel(name: str = "ch") -> OutboundChannel:
    return OutboundChannel(
        name=name,
        url="https://example.com/hook",
        events=["tiktok.*"],
        breaker=OverlayClient(name=name, max_fails=3, cooldown=10),
    )


@pytest.fixture()
def dispatcher(monkeypatch):
    """Fresh dispatcher singleton with a stubbed _post."""
    monkeypatch.setattr(od, "_dispatcher", None)
    monkeypatch.setattr(OutboundDispatcher, "_post", staticmethod(lambda u, b, t: 200))

    d = od.get_outbound_dispatcher()
    d._master_enabled = True
    d._channels = {"ch": _channel("ch")}
    yield d
    od._dispatcher = None


class TestOutboundRoutes:
    def test_list_channels(self, client, dispatcher):
        resp = client.get("/api/v1/outbound/channels")
        assert resp.status_code == 200
        body = resp.json()
        assert body["enabled"] is True
        assert len(body["channels"]) == 1
        entry = body["channels"][0]
        assert entry["name"] == "ch"
        assert entry["url"] == "https://example.com/<masked>"
        assert entry["sent"] == 0

    def test_list_empty_when_nothing_configured(self, client, dispatcher):
        dispatcher._channels = {}
        resp = client.get("/api/v1/outbound/channels")
        assert resp.status_code == 200
        assert resp.json()["channels"] == []

    def test_test_endpoint_success(self, client, dispatcher):
        resp = client.post("/api/v1/outbound/channels/ch/test")
        assert resp.status_code == 200
        assert resp.json() == {
            "name": "ch",
            "ok": True,
            "detail": "delivered (HTTP 200)",
        }

    def test_test_endpoint_unknown_channel_is_404(self, client, dispatcher):
        resp = client.post("/api/v1/outbound/channels/ghost/test")
        assert resp.status_code == 404

    def test_test_endpoint_disabled_channel(self, client, dispatcher):
        ch = _channel("off")
        ch.enabled = False
        dispatcher._channels = {ch.name: ch}
        resp = client.post("/api/v1/outbound/channels/off/test")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert "disabled" in body["detail"]
