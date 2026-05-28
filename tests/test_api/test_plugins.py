import pytest


class TestPluginEndpoints:
    PLUGIN = {
        "name": "test-plugin",
        "path": "/tmp/test-plugin.exe",
        "version": "1.0.0",
        "enabled": True,
        "level": 2,
        "port": 9999,
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
        resp = client.put("/api/v1/plugins/test-plugin", json={"level": 3, "port": 7777})
        assert resp.json()["level"] == 3
        assert resp.json()["port"] == 7777
        assert resp.json()["enabled"] is True

    def test_register_twice_updates(self, client):
        client.post("/api/v1/plugins/register", json=self.PLUGIN)
        p2 = dict(self.PLUGIN)
        p2["version"] = "2.0.0"
        resp = client.post("/api/v1/plugins/register", json=p2)
        assert resp.status_code == 201
        assert resp.json()["plugin"]["version"] == "2.0.0"
