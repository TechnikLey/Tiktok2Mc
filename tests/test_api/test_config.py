import pytest


class TestConfigEndpoints:
    def test_get_config_returns_config(self, client):
        resp = client.get("/api/v1/config")
        assert resp.status_code == 200
        body = resp.json()
        assert "path" in body
        assert "config" in body
        assert body["config"]["config_version"] == "1.0"
        assert body["config"]["overlay_text"]["enabled"] is False

    def test_get_config_path_matches_project(self, client, project_dir):
        resp = client.get("/api/v1/config")
        assert str(project_dir / "config.yaml") in resp.json()["path"]

    def test_update_config_persists_changes(self, client):
        current = client.get("/api/v1/config").json()
        original = current["config"]["server_host"]

        new_config = current["config"].copy()
        new_config["server_host"] = "0.0.0.0"
        resp = client.put("/api/v1/config", json={"config": new_config, "backup": False})
        assert resp.status_code == 200
        assert resp.json()["config"]["server_host"] == "0.0.0.0"

        reread = client.get("/api/v1/config").json()
        assert reread["config"]["server_host"] == "0.0.0.0"

        # Restore
        original_config = current["config"]
        original_config["server_host"] = original
        client.put("/api/v1/config", json={"config": original_config, "backup": False})

    def test_update_config_validates_schema(self, client):
        resp = client.put("/api/v1/config", json={"config": {"bad": "data"}, "backup": False})
        assert resp.status_code == 500

    def test_update_config_upgrades_version_on_write(self, client):
        current = client.get("/api/v1/config").json()
        cfg = current["config"].copy()
        cfg["config_version"] = "0.7"
        resp = client.put("/api/v1/config", json={"config": cfg, "backup": False})
        assert resp.status_code == 200
        assert resp.json()["config"]["config_version"] == "1.0"

    def test_update_config_backup_default_is_true(self, client):
        current = client.get("/api/v1/config").json()
        cfg = current["config"].copy()
        resp = client.put("/api/v1/config", json={"config": cfg})
        assert resp.status_code == 200

    def test_update_config_rejects_non_dict(self, client):
        resp = client.put("/api/v1/config", json={"config": "not_a_dict", "backup": False})
        assert resp.status_code == 422
