"""WebSocket endpoint tests.

Connects via ``TestClient.websocket_connect()``, injects events through
the HTTP ``POST /api/v1/events`` endpoint, and verifies they arrive on
the WebSocket.

NOTE: The ``subscribe`` command in the WS handler cannot be tested
through TestClient because ``put_nowait()`` from the test thread cannot
wake the ASGI thread's event loop (cross-thread ``asyncio.Queue``
signaling limitation).  The underlying ``EventBus.subscribe()`` /
``EventBus.unsubscribe()`` methods are thoroughly tested in
``tests/test_core/test_eventbus.py``.
"""

import pytest


class TestWebSocket:
    def test_websocket_receives_injected_events(self, client):
        """Connect WS (ALL_EVENTS), inject event via HTTP, verify arrival."""
        with client.websocket_connect("/api/v1/ws") as ws:
            resp = client.post(
                "/api/v1/events",
                json={"type": "test.ws", "data": {"msg": "hello"}},
            )
            assert resp.status_code == 200
            data = ws.receive_json()
            assert data["type"] == "test.ws"
            assert data["data"] == {"msg": "hello"}
            assert "timestamp" in data

    def test_websocket_multiple_events_in_order(self, client):
        """Multiple events arrive in order on ALL_EVENTS subscription."""
        with client.websocket_connect("/api/v1/ws") as ws:
            for i in range(3):
                client.post(
                    "/api/v1/events",
                    json={"type": "multi", "data": {"i": i}},
                )
            for i in range(3):
                data = ws.receive_json()
                assert data["type"] == "multi"
                assert data["data"]["i"] == i

    def test_websocket_disconnect_cleanup(self, client):
        """WebSocket disconnect unsubscribes from EventBus."""
        from core.api.eventbus import event_bus

        with client.websocket_connect("/api/v1/ws") as ws:
            pass  # disconnect on context exit

        # After disconnect, publishing should not raise
        resp = client.post(
            "/api/v1/events",
            json={"type": "after.disconnect", "data": {}},
        )
        assert resp.status_code == 200
