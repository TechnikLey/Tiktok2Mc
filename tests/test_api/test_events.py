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

    def test_inject_event_rejects_non_string_type(self, client):
        resp = client.post("/api/v1/events", json={"type": 42, "data": {}})
        assert resp.status_code == 422

    def test_inject_event_rejects_non_dict_data(self, client):
        resp = client.post(
            "/api/v1/events",
            json={"type": "test.event", "data": "not_a_dict"},
        )
        assert resp.status_code == 422

    @pytest.mark.skip(
        reason="TestClient blocks on open SSE stream (httpx limitation). "
        "EventBus logic is covered by test_eventbus.py.",
    )
    def test_sse_stream_connects(self, client):
        with client.stream("GET", "/api/v1/events/stream") as r:
            assert r.status_code == 200
            assert r.headers.get("content-type") == "text/event-stream"

    @pytest.mark.skip(
        reason="TestClient blocks on open SSE stream (httpx limitation).",
    )
    def test_sse_filtered_by_type(self, client):
        with client.stream("GET", "/api/v1/events/stream?types=log,status") as r:
            assert r.status_code == 200
