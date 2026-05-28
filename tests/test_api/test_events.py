import json
import pytest


class TestEventEndpoints:
    def test_inject_event(self, client):
        resp = client.post(
            "/api/v1/events",
            json={"type": "test.event", "data": {"msg": "hello"}},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["event"] == "test.event"

    def test_inject_event_defaults(self, client):
        resp = client.post("/api/v1/events", json={"data": {}})
        assert resp.status_code == 200
        assert resp.json()["event"] == "external.event"

    def test_sse_stream_connects(self, client):
        """Verify the SSE endpoint responds with correct content type."""
        with client.stream("GET", "/api/v1/events/stream", timeout=3) as r:
            assert r.status_code == 200
            assert r.headers.get("content-type") == "text/event-stream"

    def test_sse_filtered_by_type(self, client):
        with client.stream(
            "GET", "/api/v1/events/stream?types=log,status", timeout=3
        ) as r:
            assert r.status_code == 200
