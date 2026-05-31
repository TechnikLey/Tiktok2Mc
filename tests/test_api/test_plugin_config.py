import json
import pytest
from pathlib import Path

from core.yaml_utils import save_yaml


@pytest.fixture
def fake_plugins_dir(tmp_path, monkeypatch):
    """Create a temporary plugins directory with a well-known test plugin."""
    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir()

    plugin_dir = plugins_dir / "test-plugin"
    plugin_dir.mkdir()
    manifest = {
        "name": "test-plugin",
        "version": "1.0.0",
        "config_schema": {
            "version": 1,
            "fields": [
                {"key": "port", "type": "integer", "default": 8080, "min": 1024, "max": 65535},
                {"key": "label", "type": "string", "default": "Test"},
            ],
        },
    }
    (plugin_dir / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
    save_yaml(plugin_dir / "config.yaml", {"enabled": True, "port": 9000}, backup=False)

    monkeypatch.setattr(
        "core.api.routes.plugin_config.discover_plugins_dir", lambda: plugins_dir
    )
    monkeypatch.setattr(
        "core.plugin_config.discover_plugins_dir", lambda: plugins_dir
    )
    return plugins_dir


class TestGetPluginConfig:
    def test_get_existing_config(self, client, fake_plugins_dir):
        resp = client.get("/api/v1/plugins/test-plugin/config")
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "test-plugin"
        assert body["config"]["enabled"] is True
        assert body["config"]["port"] == 9000

    def test_get_unknown_plugin_404(self, client, fake_plugins_dir):
        resp = client.get("/api/v1/plugins/unknown-plugin/config")
        assert resp.status_code == 404


class TestUpdatePluginConfig:
    def test_put_valid_config(self, client, fake_plugins_dir):
        payload = {"enabled": False, "port": 5000, "label": "Updated"}
        resp = client.put("/api/v1/plugins/test-plugin/config", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["config"]["enabled"] is False
        assert body["config"]["port"] == 5000
        assert body["config"]["label"] == "Updated"

    def test_put_creates_backup_by_default(self, client, fake_plugins_dir, project_dir):
        payload = {"enabled": False, "port": 5001, "label": "BackupTest"}
        resp = client.put("/api/v1/plugins/test-plugin/config", json=payload)
        assert resp.status_code == 200

        # Backup file should exist in centralized backups
        backup_files = list(
            (project_dir / "data" / "backups" / "plugins" / "test-plugin").glob("*")
        )
        assert len(backup_files) == 1

    def test_put_respects_disable_backup(self, client, fake_plugins_dir, project_dir):
        # Remove any existing backups first
        backup_dir = project_dir / "data" / "backups" / "plugins" / "test-plugin"
        if backup_dir.exists():
            for bak in backup_dir.glob("*"):
                bak.unlink()

        payload = {"enabled": True, "port": 5002, "label": "NoBackup", "_backup": False}
        resp = client.put("/api/v1/plugins/test-plugin/config", json=payload)
        assert resp.status_code == 200

        backup_files = list(backup_dir.glob("*"))
        assert len(backup_files) == 0

    def test_put_invalid_type_422(self, client, fake_plugins_dir):
        # Framework fields like "enabled" are not validated against plugin
        # schema; invalid values are corrected on next load. Test that
        # plugin-defined fields still reject invalid types.
        payload = {"port": "not_an_int", "label": "Test"}
        resp = client.put("/api/v1/plugins/test-plugin/config", json=payload)
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert "errors" in detail

    def test_put_out_of_range_422(self, client, fake_plugins_dir):
        payload = {"enabled": True, "port": 100}
        resp = client.put("/api/v1/plugins/test-plugin/config", json=payload)
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert any("1024" in e for e in detail["errors"])

    def test_put_unknown_plugin_404(self, client, fake_plugins_dir):
        resp = client.put(
            "/api/v1/plugins/unknown-plugin/config",
            json={"enabled": True},
        )
        assert resp.status_code == 404

    def test_round_trip_consistency(self, client, fake_plugins_dir):
        payload = {"enabled": False, "port": 7777, "label": "RT"}
        put_resp = client.put("/api/v1/plugins/test-plugin/config", json=payload)
        assert put_resp.status_code == 200

        get_resp = client.get("/api/v1/plugins/test-plugin/config")
        assert get_resp.status_code == 200
        body = get_resp.json()
        assert body["config"]["enabled"] is False
        assert body["config"]["port"] == 7777
        assert body["config"]["label"] == "RT"

    def test_put_no_schema_plugin(self, client, fake_plugins_dir):
        plugin_dir = fake_plugins_dir / "no-schema"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(
            json.dumps({"name": "no-schema"}), encoding="utf-8"
        )
        save_yaml(plugin_dir / "config.yaml", {"value": 1}, backup=False)

        resp = client.put(
            "/api/v1/plugins/no-schema/config",
            json={"value": 2},
        )
        assert resp.status_code == 200
        get_resp = client.get("/api/v1/plugins/no-schema/config")
        assert get_resp.json()["config"]["value"] == 2


class TestGetPluginSchema:
    def test_get_schema(self, client, fake_plugins_dir):
        resp = client.get("/api/v1/plugins/test-plugin/config/schema")
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "test-plugin"
        assert body["schema"] is not None
        assert body["schema"]["version"] == 1
        # enabled (framework), port, label
        assert len(body["schema"]["fields"]) == 3
        # enabled should be marked as framework-managed
        enabled_field = next(f for f in body["schema"]["fields"] if f["key"] == "enabled")
        assert enabled_field["framework"] is True
        assert enabled_field["default"] is True

    def test_get_schema_no_schema(self, client, fake_plugins_dir):
        plugin_dir = fake_plugins_dir / "no-schema"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(
            json.dumps({"name": "no-schema"}), encoding="utf-8"
        )

        resp = client.get("/api/v1/plugins/no-schema/config/schema")
        assert resp.status_code == 200
        schema = resp.json()["schema"]
        # framework injects enabled even when plugin has no schema
        assert schema is not None
        assert len(schema["fields"]) == 1
        assert schema["fields"][0]["key"] == "enabled"
        assert schema["fields"][0]["framework"] is True

    def test_get_schema_unknown_plugin_404(self, client, fake_plugins_dir):
        resp = client.get("/api/v1/plugins/unknown-plugin/config/schema")
        assert resp.status_code == 404
