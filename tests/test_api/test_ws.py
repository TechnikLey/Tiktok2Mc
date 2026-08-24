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

        with client.websocket_connect("/api/v1/ws") as ws:
            pass  # disconnect on context exit

        # After disconnect, publishing should not raise
        resp = client.post(
            "/api/v1/events",
            json={"type": "after.disconnect", "data": {}},
        )
        assert resp.status_code == 200

    def test_websocket_rejects_cross_origin_handshake(self, client):
        """Cross-site WebSocket hijacking is blocked by the origin guard.

        A browser page opening ``ws://127.0.0.1:<port>/api/v1/ws`` always
        sends a foreign ``Origin`` header — the handshake must be closed
        before it completes instead of streaming events to the attacker.
        """
        import pytest
        from starlette.websockets import WebSocketDisconnect

        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(
                "/api/v1/ws", headers={"origin": "https://evil.example"}
            ):
                pass  # pragma: no cover - never reached on rejection

    def test_websocket_allows_same_origin_handshake(self, client):
        """A same-origin handshake (dashboard tab reconnecting) passes."""
        with client.websocket_connect(
            "/api/v1/ws", headers={"origin": "http://testserver"}
        ) as ws:
            resp = client.post(
                "/api/v1/events",
                json={"type": "same.origin", "data": {"ok": True}},
            )
            assert resp.status_code == 200
            data = ws.receive_json()
            assert data["type"] == "same.origin"
