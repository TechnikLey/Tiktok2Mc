class TestHealthEndpoints:
    def test_health_returns_ok(self, client):
        from core.version import TOOL_VERSION

        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["version"] == "1.0.0"
        assert body["api_version"] == "1.0.0"
        assert body["tool_version"] == TOOL_VERSION

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

    def test_status_includes_tiktok_live_fields(self, client):
        resp = client.get("/api/v1/status")
        assert resp.status_code == 200
        body = resp.json()
        # Fields exist and are null until the bridge reports a state.
        assert "tiktok_live" in body
        assert body["tiktok_live"] is None
        assert "tiktok_live_last_update" in body
        assert "tiktok_live_last_event" in body
        assert "tiktok_live_source" in body
        assert body["tiktok_live_source"] == ""

    def test_tiktok_live_tracker_updates_status(self, client):
        from core.api.tiktok_live import get_tiktok_live_tracker

        tracker = get_tiktok_live_tracker()
        tracker.set_connected(True, source="tiktok_bridge")
        try:
            resp = client.get("/api/v1/status")
            assert resp.status_code == 200
            body = resp.json()
            assert body["tiktok_live"] is True
            assert body["tiktok_live_source"] == "tiktok_bridge"
            assert body["tiktok_live_last_update"] > 0
        finally:
            tracker.set_connected(False, source="tiktok_bridge")
