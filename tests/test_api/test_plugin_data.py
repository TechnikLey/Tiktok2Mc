"""API tests for the namespaced plugin data endpoints."""

from __future__ import annotations

import pytest

import core.api.services.persistence_service as persistence_module


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    """Point the persistence singleton at a fresh temp directory."""
    monkeypatch.setattr(persistence_module, "get_plugin_data_dir", lambda: tmp_path)
    monkeypatch.setattr(persistence_module, "_persistence_service", None)
    yield tmp_path
    persistence_module._persistence_service = None


class TestPluginDataEndpoints:
    def test_set_and_get_key(self, client, data_dir):
        resp = client.put(
            "/api/v1/plugins/leaderboard/data/scores.user-1",
            json={"value": {"points": 10}},
        )
        assert resp.status_code == 200
        assert resp.json()["value"] == {"points": 10}

        resp = client.get("/api/v1/plugins/leaderboard/data/scores.user-1")
        assert resp.status_code == 200
        assert resp.json() == {
            "name": "leaderboard",
            "key": "scores.user-1",
            "value": {"points": 10},
        }

    def test_get_whole_store(self, client, data_dir):
        client.put("/api/v1/plugins/p1/data/a", json={"value": 1})
        client.put("/api/v1/plugins/p1/data/b", json={"value": [2]})
        resp = client.get("/api/v1/plugins/p1/data")
        assert resp.status_code == 200
        assert resp.json()["data"] == {"a": 1, "b": [2]}

    def test_get_unknown_store_is_empty(self, client, data_dir):
        resp = client.get("/api/v1/plugins/ghost/data")
        assert resp.status_code == 200
        assert resp.json()["data"] == {}

    def test_get_missing_key_returns_404(self, client, data_dir):
        resp = client.get("/api/v1/plugins/p1/data/nope")
        assert resp.status_code == 404

    def test_overwrite_and_delete(self, client, data_dir):
        client.put("/api/v1/plugins/p1/data/k", json={"value": "old"})
        client.put("/api/v1/plugins/p1/data/k", json={"value": "new"})
        assert client.get("/api/v1/plugins/p1/data/k").json()["value"] == "new"

        resp = client.delete("/api/v1/plugins/p1/data/k")
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True
        assert client.get("/api/v1/plugins/p1/data/k").status_code == 404

        # Deleting again is a 404
        assert client.delete("/api/v1/plugins/p1/data/k").status_code == 404

    def test_null_value_is_storable(self, client, data_dir):
        resp = client.put("/api/v1/plugins/p1/data/nullish", json={"value": None})
        assert resp.status_code == 200
        assert client.get("/api/v1/plugins/p1/data/nullish").json()["value"] is None

    def test_rejects_invalid_key(self, client, data_dir):
        resp = client.put("/api/v1/plugins/p1/data/bad%20key", json={"value": 1})
        assert resp.status_code == 422
        assert not (data_dir / "p1.json").exists()

    def test_rejects_bad_body(self, client, data_dir):
        resp = client.put("/api/v1/plugins/p1/data/k", json={})
        assert resp.status_code == 422
