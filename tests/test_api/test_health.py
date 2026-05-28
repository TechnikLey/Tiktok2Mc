import pytest


class TestHealthEndpoints:
    def test_health_returns_ok(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["api_version"] == "1.0.0"

    def test_status_returns_running(self, client):
        resp = client.get("/api/v1/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["server"] == "running"
        assert isinstance(body["plugins_active"], int)
        assert isinstance(body["plugins_total"], int)
        assert body["config_loaded"] is True
        assert isinstance(body["uptime_seconds"], (int, float))
        assert body["uptime_seconds"] >= 0
