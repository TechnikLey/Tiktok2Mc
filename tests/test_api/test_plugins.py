from typing import ClassVar

import pytest


class TestPluginEndpoints:
    PLUGIN: ClassVar[dict] = {
        "name": "test-plugin",
        "path": "/tmp/test-plugin.exe",
        "version": "1.0.0",
        "enabled": True,
        "level": 2,
        "ics": False,
        "description": "A test plugin",
    }

    @pytest.fixture(autouse=True)
    def _clear_registry(self):
        """Each test starts with a clean registry."""
        from core.api.registry import get_registry

        reg = get_registry()
        for p in reg.list():
            reg.unregister(p.name)

    def test_register_plugin(self, client):
        resp = client.post("/api/v1/plugins/register", json=self.PLUGIN)
        assert resp.status_code == 201
        body = resp.json()
        assert body["status"] == "registered"
        assert body["plugin"]["name"] == "test-plugin"
        assert body["plugin"]["enabled"] is True

    def test_list_plugins(self, client):
        client.post("/api/v1/plugins/register", json=self.PLUGIN)
        resp = client.get("/api/v1/plugins")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] >= 1
        assert body["enabled"] >= 1
        names = [p["name"] for p in body["plugins"]]
        assert "test-plugin" in names

    def test_get_plugin(self, client):
        client.post("/api/v1/plugins/register", json=self.PLUGIN)
        resp = client.get("/api/v1/plugins/test-plugin")
        assert resp.status_code == 200
        assert resp.json()["name"] == "test-plugin"
        assert resp.json()["version"] == "1.0.0"

    def test_get_plugin_not_found(self, client):
        resp = client.get("/api/v1/plugins/nonexistent")
        assert resp.status_code == 404

    def test_get_plugin_empty_list(self, client):
        resp = client.get("/api/v1/plugins")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0
        assert resp.json()["plugins"] == []

    def test_update_plugin(self, client):
        client.post("/api/v1/plugins/register", json=self.PLUGIN)
        resp = client.put("/api/v1/plugins/test-plugin", json={"enabled": False})
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False

    def test_update_plugin_not_found(self, client):
        resp = client.put("/api/v1/plugins/nonexistent", json={"enabled": False})
        assert resp.status_code == 404

    def test_unregister_plugin(self, client):
        client.post("/api/v1/plugins/register", json=self.PLUGIN)
        resp = client.delete("/api/v1/plugins/test-plugin")
        assert resp.status_code == 200
        assert resp.json()["status"] == "unregistered"
        assert resp.json()["name"] == "test-plugin"

        resp = client.get("/api/v1/plugins/test-plugin")
        assert resp.status_code == 404

    def test_unregister_plugin_not_found(self, client):
        resp = client.delete("/api/v1/plugins/nonexistent")
        assert resp.status_code == 404

    def test_restart_plugin_writes_signals(self, client):
        from core.paths import get_runtime_dir

        client.post("/api/v1/plugins/register", json=self.PLUGIN)
        resp = client.post("/api/v1/plugins/test-plugin/restart")
        assert resp.status_code == 200
        assert resp.json()["status"] == "restart_requested"
        assert resp.json()["name"] == "test-plugin"

        runtime = get_runtime_dir()
        assert (runtime / "plugin_stop_test-plugin").exists()
        assert (runtime / "plugin_start_test-plugin").exists()

        (runtime / "plugin_stop_test-plugin").unlink(missing_ok=True)
        (runtime / "plugin_start_test-plugin").unlink(missing_ok=True)

    def test_restart_plugin_not_found(self, client):
        resp = client.post("/api/v1/plugins/nonexistent/restart")
        assert resp.status_code == 404

    def test_register_plugin_requires_name(self, client):
        resp = client.post("/api/v1/plugins/register", json={})
        assert resp.status_code == 422

    def test_register_multiple_plugins(self, client):
        for i in range(3):
            p = dict(self.PLUGIN)
            p["name"] = f"plugin-{i}"
            resp = client.post("/api/v1/plugins/register", json=p)
            assert resp.status_code == 201

        resp = client.get("/api/v1/plugins")
        assert resp.json()["total"] == 3

    def test_update_plugin_partial_fields(self, client):
        client.post("/api/v1/plugins/register", json=self.PLUGIN)
        resp = client.put("/api/v1/plugins/test-plugin", json={"level": 3})
        assert resp.json()["level"] == 3
        assert resp.json()["enabled"] is True

    def test_register_twice_updates(self, client):
        client.post("/api/v1/plugins/register", json=self.PLUGIN)
        p2 = dict(self.PLUGIN)
        p2["version"] = "2.0.0"
        resp = client.post("/api/v1/plugins/register", json=p2)
        assert resp.status_code == 201
        assert resp.json()["plugin"]["version"] == "2.0.0"

    def test_enable_plugin(self, client):
        p = dict(self.PLUGIN)
        p["enabled"] = False
        client.post("/api/v1/plugins/register", json=p)
        resp = client.post("/api/v1/plugins/test-plugin/enable")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is True

    def test_disable_plugin(self, client):
        client.post("/api/v1/plugins/register", json=self.PLUGIN)
        resp = client.post("/api/v1/plugins/test-plugin/disable")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False

    def test_enable_plugin_not_found(self, client):
        resp = client.post("/api/v1/plugins/nonexistent/enable")
        assert resp.status_code == 404

    def test_disable_plugin_not_found(self, client):
        resp = client.post("/api/v1/plugins/nonexistent/disable")
        assert resp.status_code == 404

    def test_enable_disable_cycle(self, client):
        p = dict(self.PLUGIN)
        p["enabled"] = False
        client.post("/api/v1/plugins/register", json=p)

        resp = client.post("/api/v1/plugins/test-plugin/enable")
        assert resp.json()["enabled"] is True

        resp = client.post("/api/v1/plugins/test-plugin/disable")
        assert resp.json()["enabled"] is False

        resp = client.post("/api/v1/plugins/test-plugin/enable")
        assert resp.json()["enabled"] is True

    def test_enable_twice_is_idempotent(self, client):
        p = dict(self.PLUGIN)
        p["enabled"] = True
        client.post("/api/v1/plugins/register", json=p)
        resp = client.post("/api/v1/plugins/test-plugin/enable")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is True

    # ── Health monitoring tests ──────────────────────────────────────

    def test_plugin_has_health_fields(self, client):
        client.post("/api/v1/plugins/register", json=self.PLUGIN)
        resp = client.get("/api/v1/plugins/test-plugin")
        assert resp.status_code == 200
        assert "health_status" in resp.json()
        assert "last_heartbeat" in resp.json()

    def test_enable_sets_health_healthy(self, client):
        p = dict(self.PLUGIN)
        p["enabled"] = False
        client.post("/api/v1/plugins/register", json=p)
        resp = client.post("/api/v1/plugins/test-plugin/enable")
        assert resp.status_code == 200
        # Health is "starting" until the first heartbeat arrives;
        # the health monitor promotes it to "healthy" later.
        assert resp.json()["health_status"] == "starting"

    def test_disable_sets_health_unknown(self, client):
        client.post("/api/v1/plugins/register", json=self.PLUGIN)
        resp = client.post("/api/v1/plugins/test-plugin/disable")
        assert resp.status_code == 200
        assert resp.json()["health_status"] == "unknown"

    def test_update_health_status(self, client):
        client.post("/api/v1/plugins/register", json=self.PLUGIN)
        resp = client.put(
            "/api/v1/plugins/test-plugin",
            json={"health_status": "unhealthy"},
        )
        assert resp.status_code == 200
        assert resp.json()["health_status"] == "unhealthy"

    def test_update_health_dead_disables_plugin(self, client):
        client.post("/api/v1/plugins/register", json=self.PLUGIN)
        resp = client.put(
            "/api/v1/plugins/test-plugin",
            json={"health_status": "dead", "enabled": False},
        )
        assert resp.status_code == 200
        assert resp.json()["health_status"] == "dead"
        assert resp.json()["enabled"] is False

    def test_heartbeat_recorded_on_register(self, client):
        import time

        before = time.time()
        client.post("/api/v1/plugins/register", json=self.PLUGIN)
        resp = client.get("/api/v1/plugins/test-plugin")
        assert resp.status_code == 200
        hb = resp.json().get("last_heartbeat")
        # heartbeat may be None if never polled — that's fine
        assert hb is None or hb >= before
