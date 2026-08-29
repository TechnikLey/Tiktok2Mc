"""Tests for the namespaced PersistenceService (plugin/hook storage)."""

from __future__ import annotations

import json

import pytest

from core.api.services.persistence_service import (
    PersistenceError,
    PersistenceService,
)


@pytest.fixture()
def svc(tmp_path):
    return PersistenceService(storage_dir=tmp_path)


class TestValidation:
    def test_rejects_bad_namespace(self, svc):
        with pytest.raises(PersistenceError):
            svc.get_store("../evil")

    @pytest.mark.parametrize(
        "bad",
        ["", "a/b", "..", "with space", "x" * 65],
    )
    def test_rejects_invalid_namespaces(self, svc, bad):
        with pytest.raises(PersistenceError):
            svc.set(bad, "key", 1)

    @pytest.mark.parametrize("bad", ["", "a b", "k/l", "y" * 129])
    def test_rejects_invalid_keys(self, svc, bad):
        with pytest.raises(PersistenceError):
            svc.set("good-name", bad, 1)

    def test_accepts_valid_namespace_and_key(self, svc):
        svc.set("leaderboard", "scores.user-1", {"points": 10})
        found, value = svc.get("leaderboard", "scores.user-1")
        assert found is True
        assert value == {"points": 10}


class TestStoreOperations:
    def test_get_store_empty_when_absent(self, svc):
        assert svc.get_store("no-such-plugin") == {}

    def test_set_and_get_roundtrip(self, svc, tmp_path):
        svc.set("plugin-a", "counter", 42)
        found, value = svc.get("plugin-a", "counter")
        assert (found, value) == (True, 42)
        assert (tmp_path / "plugin-a.json").is_file()

    def test_nested_values_survive_json(self, svc):
        payload = {"list": [1, "zwei", None], "nested": {"deep": True}}
        svc.set("plugin-a", "blob", payload)
        _, value = svc.get("plugin-a", "blob")
        assert value == payload

    def test_overwrite_existing_key(self, svc):
        svc.set("plugin-a", "k", "old")
        svc.set("plugin-a", "k", "new")
        _, value = svc.get("plugin-a", "k")
        assert value == "new"

    def test_namespaces_are_isolated(self, svc):
        svc.set("plugin-a", "shared-key", "a")
        svc.set("plugin-b", "shared-key", "b")
        assert svc.get("plugin-a", "shared-key")[1] == "a"
        assert svc.get("plugin-b", "shared-key")[1] == "b"
        assert set(svc.get_store("plugin-a")) == {"shared-key"}

    def test_get_missing_key(self, svc):
        found, value = svc.get("plugin-a", "missing")
        assert found is False
        assert value is None

    def test_delete_existing_key(self, svc):
        svc.set("plugin-a", "gone", 1)
        assert svc.delete("plugin-a", "gone") is True
        assert svc.get("plugin-a", "gone")[0] is False

    def test_delete_missing_key_returns_false(self, svc):
        assert svc.delete("plugin-a", "never-there") is False

    def test_file_is_valid_json(self, svc, tmp_path):
        svc.set("plugin-a", "x", [1, 2])
        data = json.loads((tmp_path / "plugin-a.json").read_text(encoding="utf-8"))
        assert data == {"x": [1, 2]}

    def test_corrupt_file_reads_as_empty(self, svc, tmp_path):
        target = tmp_path / "broken.json"
        target.write_text("{not json", encoding="utf-8")
        assert svc.get_store("broken") == {}


class TestSingleton:
    def test_singleton(self):
        from core.api.services.persistence_service import get_persistence_service

        assert get_persistence_service() is get_persistence_service()
