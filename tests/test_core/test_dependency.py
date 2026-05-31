"""Tests for plugin dependency ordering and validation."""

import pytest


class TestTopologicalSort:
    def test_empty_list(self):
        from core.api.dependency import topological_sort
        assert topological_sort([]) == []

    def test_single_plugin_no_deps(self):
        from core.api.dependency import topological_sort
        plugins = [{"name": "a", "depends_on": []}]
        assert topological_sort(plugins) == plugins

    def test_simple_linear_deps(self):
        from core.api.dependency import topological_sort
        plugins = [
            {"name": "b", "depends_on": ["a"]},
            {"name": "a", "depends_on": []},
        ]
        result = topological_sort(plugins)
        names = [p["name"] for p in result]
        assert names.index("a") < names.index("b")

    def test_chain_deps(self):
        from core.api.dependency import topological_sort
        plugins = [
            {"name": "c", "depends_on": ["b"]},
            {"name": "b", "depends_on": ["a"]},
            {"name": "a", "depends_on": []},
        ]
        result = topological_sort(plugins)
        names = [p["name"] for p in result]
        assert names.index("a") < names.index("b") < names.index("c")

    def test_diamond_deps(self):
        from core.api.dependency import topological_sort
        plugins = [
            {"name": "d", "depends_on": ["b", "c"]},
            {"name": "b", "depends_on": ["a"]},
            {"name": "c", "depends_on": ["a"]},
            {"name": "a", "depends_on": []},
        ]
        result = topological_sort(plugins)
        names = [p["name"] for p in result]
        assert names.index("a") < names.index("b")
        assert names.index("a") < names.index("c")
        assert names.index("b") < names.index("d")
        assert names.index("c") < names.index("d")

    def test_multiple_deps(self):
        from core.api.dependency import topological_sort
        plugins = [
            {"name": "c", "depends_on": ["a", "b"]},
            {"name": "b", "depends_on": []},
            {"name": "a", "depends_on": []},
        ]
        result = topological_sort(plugins)
        names = [p["name"] for p in result]
        assert names.index("a") < names.index("c")
        assert names.index("b") < names.index("c")

    def test_circular_dep_raises_error(self):
        from core.api.dependency import topological_sort, DependencyError
        plugins = [
            {"name": "a", "depends_on": ["b"]},
            {"name": "b", "depends_on": ["a"]},
        ]
        with pytest.raises(DependencyError, match="Circular dependency"):
            topological_sort(plugins)

    def test_self_dep_raises_error(self):
        from core.api.dependency import topological_sort, DependencyError
        plugins = [
            {"name": "a", "depends_on": ["a"]},
        ]
        with pytest.raises(DependencyError, match="Circular dependency"):
            topological_sort(plugins)

    def test_missing_dep_ignored_with_warning(self, caplog):
        from core.api.dependency import topological_sort
        import logging
        caplog.set_level(logging.WARNING)
        plugins = [
            {"name": "b", "depends_on": ["missing"]},
            {"name": "a", "depends_on": []},
        ]
        result = topological_sort(plugins)
        names = [p["name"] for p in result]
        assert "b" in names
        assert "a" in names
        assert any("depends on 'missing'" in rec.message for rec in caplog.records)

    def test_no_depends_on_key(self):
        from core.api.dependency import topological_sort
        plugins = [
            {"name": "b"},
            {"name": "a"},
        ]
        result = topological_sort(plugins)
        assert len(result) == 2

    def test_custom_keys(self):
        from core.api.dependency import topological_sort
        plugins = [
            {"id": "b", "needs": ["a"]},
            {"id": "a", "needs": []},
        ]
        result = topological_sort(plugins, name_key="id", depends_on_key="needs")
        names = [p["id"] for p in result]
        assert names.index("a") < names.index("b")


class TestValidateDependencies:
    def test_no_deps(self):
        from core.api.dependency import validate_dependencies
        assert validate_dependencies("p", [], {"a": "x"}) == []

    def test_all_satisfied(self):
        from core.api.dependency import validate_dependencies
        assert validate_dependencies("p", ["a", "b"], {"a": "x", "b": "y"}) == []

    def test_some_missing(self):
        from core.api.dependency import validate_dependencies
        missing = validate_dependencies("p", ["a", "b"], {"a": "x"})
        assert missing == ["b"]

    def test_all_missing(self):
        from core.api.dependency import validate_dependencies
        missing = validate_dependencies("p", ["a", "b"], {})
        assert sorted(missing) == ["a", "b"]


class TestGetDependencyOrder:
    def test_returns_topological_order(self):
        from core.api.dependency import get_dependency_order
        plugins = [
            {"name": "b", "depends_on": ["a"]},
            {"name": "a", "depends_on": []},
        ]
        result = get_dependency_order(plugins)
        names = [p["name"] for p in result]
        assert names.index("a") < names.index("b")

    def test_falls_back_on_circular(self, caplog):
        from core.api.dependency import get_dependency_order
        import logging
        caplog.set_level(logging.WARNING)
        plugins = [
            {"name": "a", "depends_on": ["b"]},
            {"name": "b", "depends_on": ["a"]},
        ]
        result = get_dependency_order(plugins)
        # Falls back to alphabetical
        names = [p["name"] for p in result]
        assert names == ["a", "b"]
        assert any("falling back to alphabetical" in rec.message for rec in caplog.records)

    def test_empty_list(self):
        from core.api.dependency import get_dependency_order
        assert get_dependency_order([]) == []


class TestAppConfigDependency:
    def test_appconfig_has_depends_on(self):
        from core.models import AppConfig
        from pathlib import Path
        cfg = AppConfig(name="test", path=Path("."), enable=True, level=2, ics=False)
        assert hasattr(cfg, "depends_on")
        assert cfg.depends_on == []

    def test_appconfig_with_deps(self):
        from core.models import AppConfig
        from pathlib import Path
        cfg = AppConfig(name="test", path=Path("."), enable=True, level=2, ics=False, depends_on=["a", "b"])
        assert cfg.depends_on == ["a", "b"]

    def test_from_dict_preserves_depends_on(self):
        from core.models import AppConfig
        from pathlib import Path
        cfg = AppConfig.from_dict({
            "name": "test",
            "path": ".",
            "enable": True,
            "level": 2,
            "ics": False,
            "depends_on": ["a"],
        })
        assert cfg.depends_on == ["a"]

    def test_to_dict_includes_depends_on(self):
        from core.models import AppConfig
        from pathlib import Path
        cfg = AppConfig(name="test", path=Path("."), enable=True, level=2, ics=False, depends_on=["x"])
        d = cfg.to_dict()
        assert "depends_on" in d
        assert d["depends_on"] == ["x"]


class TestRegistrationDependencyValidation:
    @pytest.fixture(autouse=True)
    def _clear_registry(self):
        from core.api.registry import get_registry
        reg = get_registry()
        for p in reg.list():
            reg.unregister(p.name)

    def test_register_without_deps_succeeds(self, client):
        resp = client.post("/api/v1/plugins/register", json={
            "name": "standalone",
            "version": "1.0.0",
            "display_name": "Standalone",
            "entry_point": "test/main.py",
            "depends_on": [],
        })
        assert resp.status_code == 201

    def test_register_with_satisfied_deps_succeeds(self, client):
        client.post("/api/v1/plugins/register", json={
            "name": "dependency",
            "version": "1.0.0",
            "display_name": "Dependency",
            "entry_point": "test/dep.py",
        })
        resp = client.post("/api/v1/plugins/register", json={
            "name": "dependent",
            "version": "1.0.0",
            "display_name": "Dependent",
            "entry_point": "test/main.py",
            "depends_on": ["dependency"],
        })
        assert resp.status_code == 201

    def test_register_with_missing_dep_fails(self, client):
        resp = client.post("/api/v1/plugins/register", json={
            "name": "dependent",
            "version": "1.0.0",
            "display_name": "Dependent",
            "entry_point": "test/main.py",
            "depends_on": ["nonexistent"],
        })
        assert resp.status_code == 422
        data = resp.json()
        assert "nonexistent" in data["detail"]

    def test_register_with_multiple_missing_deps_fails(self, client):
        resp = client.post("/api/v1/plugins/register", json={
            "name": "dependent",
            "version": "1.0.0",
            "display_name": "Dependent",
            "entry_point": "test/main.py",
            "depends_on": ["missing_a", "missing_b"],
        })
        assert resp.status_code == 422
        data = resp.json()
        assert "missing_a" in data["detail"]
        assert "missing_b" in data["detail"]

    def test_put_with_unregistered_dep_fails(self, client):
        """PUT rejecting unregistered dependency should leave plugin unchanged."""
        client.post("/api/v1/plugins/register", json={
            "name": "dependent",
            "version": "1.0.0",
            "display_name": "Dependent",
            "entry_point": "test/main.py",
        })
        resp = client.put("/api/v1/plugins/dependent", json={
            "depends_on": ["missing_dep"],
        })
        assert resp.status_code == 422
        # Verify depends_on was NOT changed
        resp = client.get("/api/v1/plugins/dependent")
        assert resp.json()["depends_on"] == []

    def test_enable_with_unregistered_dep_fails(self, client):
        """Register dependency, register dependent, unregister dep, enable fails."""
        client.post("/api/v1/plugins/register", json={
            "name": "base",
            "version": "1.0.0",
            "display_name": "Base",
            "entry_point": "test/base.py",
        })
        client.post("/api/v1/plugins/register", json={
            "name": "dependent",
            "version": "1.0.0",
            "display_name": "Dependent",
            "entry_point": "test/main.py",
            "depends_on": ["base"],
        })
        # Unregister the dependency
        client.delete("/api/v1/plugins/base")
        resp = client.post("/api/v1/plugins/dependent/enable")
        assert resp.status_code == 422
        assert "base" in resp.json()["detail"]

    def test_enable_with_disabled_dep_fails(self, client):
        client.post("/api/v1/plugins/register", json={
            "name": "base",
            "version": "1.0.0",
            "display_name": "Base",
            "entry_point": "test/base.py",
        })
        client.post("/api/v1/plugins/register", json={
            "name": "dependent",
            "version": "1.0.0",
            "display_name": "Dependent",
            "entry_point": "test/main.py",
            "depends_on": ["base"],
        })
        # base is not enabled
        resp = client.post("/api/v1/plugins/dependent/enable")
        assert resp.status_code == 422
        assert "base" in resp.json()["detail"]
        assert "not enabled" in resp.json()["detail"]

    def test_enable_with_enabled_dep_succeeds(self, client):
        client.post("/api/v1/plugins/register", json={
            "name": "base",
            "version": "1.0.0",
            "display_name": "Base",
            "entry_point": "test/base.py",
        })
        client.post("/api/v1/plugins/register", json={
            "name": "dependent",
            "version": "1.0.0",
            "display_name": "Dependent",
            "entry_point": "test/main.py",
            "depends_on": ["base"],
        })
        client.post("/api/v1/plugins/base/enable")
        resp = client.post("/api/v1/plugins/dependent/enable")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is True
