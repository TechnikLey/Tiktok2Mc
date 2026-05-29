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
                {"key": "enabled", "type": "boolean", "default": False},
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

    def test_put_invalid_type_422(self, client, fake_plugins_dir):
        payload = {"enabled": "not_a_bool", "port": 5000}
        resp = client.put("/api/v1/plugins/test-plugin/config", json=payload)
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert "errors" in detail
        assert any("boolean" in e for e in detail["errors"])

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
        assert len(body["schema"]["fields"]) == 3

    def test_get_schema_no_schema(self, client, fake_plugins_dir):
        plugin_dir = fake_plugins_dir / "no-schema"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(
            json.dumps({"name": "no-schema"}), encoding="utf-8"
        )

        resp = client.get("/api/v1/plugins/no-schema/config/schema")
        assert resp.status_code == 200
        assert resp.json()["schema"] is None

    def test_get_schema_unknown_plugin_404(self, client, fake_plugins_dir):
        resp = client.get("/api/v1/plugins/unknown-plugin/config/schema")
        assert resp.status_code == 404
