import pytest


class TestPluginFieldValidation:
    @pytest.fixture(autouse=True)
    def _clear_registry(self):
        from core.api.registry import get_registry

        reg = get_registry()
        for p in reg.list():
            reg.unregister(p.name)

    def test_register_empty_name_rejected(self, client):
        resp = client.post(
            "/api/v1/plugins/register",
            json={"name": ""},
        )
        assert resp.status_code == 422

    def test_register_invalid_level_rejected(self, client):
        resp = client.post(
            "/api/v1/plugins/register",
            json={"name": "p", "level": 99},
        )
        assert resp.status_code == 422

    def test_register_non_bool_ics_coerced(self, client):
        resp = client.post(
            "/api/v1/plugins/register",
            json={"name": "p", "ics": "yes"},
        )
        # Pydantic v2 coerces truthy strings to True
        assert resp.status_code == 201
        assert resp.json()["plugin"]["ics"] is True

    def test_update_invalid_level_rejected(self, client):
        resp = client.put(
            "/api/v1/plugins/p",
            json={"level": 99},
        )
        assert resp.status_code == 422

    def test_update_with_empty_body_keeps_existing(self, client):
        client.post(
            "/api/v1/plugins/register",
            json={"name": "existing_plugin"},
        )
        resp = client.put(
            "/api/v1/plugins/existing_plugin",
            json={},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "existing_plugin"


class TestPluginEmptyList:
    def test_list_mixed_enabled_counts(self, client):
        resp = client.get("/api/v1/plugins")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] >= 0
        assert isinstance(body["enabled"], int)


class TestPluginUpsert:
    @pytest.fixture(autouse=True)
    def _clear_registry(self):
        from core.api.registry import get_registry

        reg = get_registry()
        for p in reg.list():
            reg.unregister(p.name)

    def test_register_with_all_fields(self, client):
        resp = client.post(
            "/api/v1/plugins/register",
            json={
                "name": "full_plugin",
                "path": "/some/path",
                "version": "2.1.0",
                "enabled": True,
                "level": 3,
                "ics": True,
                "description": "A full plugin",
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["status"] == "registered"
        p = body["plugin"]
        assert p["name"] == "full_plugin"
        assert p["path"] == "/some/path"
        assert p["version"] == "2.1.0"
        assert p["enabled"] is True
        assert p["level"] == 3
        assert p["ics"] is True
        assert p["description"] == "A full plugin"
