import pytest

pytestmark = pytest.mark.skip(
    reason="TestClient blocks on open WebSocket streams (httpx limitation).",
)


class TestWebSocketEndpoint:
    def test_websocket_connects(self, client):
        with client.websocket_connect("/api/v1/ws") as ws:
            data = ws.receive_json(timeout=2)
            assert "type" in data

    def test_websocket_subscribe_command(self, client):
        with client.websocket_connect("/api/v1/ws") as ws:
            ws.send_json({"type": "subscribe", "events": ["log"]})
            data = ws.receive_json(timeout=2)
            assert data["type"] == "ping" or isinstance(data["type"], str)
