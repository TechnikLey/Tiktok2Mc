"""Integration tests for GET /api/v1/plugins/discover.

Verifies that the discovery endpoint scans filesystem manifests
and merges registry state without side effects.
"""

import json
from pathlib import Path

import pytest


def _create_manifest(root: Path, name: str, version: str = "1.0.0",
                      entry_point: str = "main.py") -> None:
    """Create a temporary plugin manifest on disk."""
    plugin_dir = root / "src" / "plugins" / name
    plugin_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "name": name,
        "version": version,
        "entry_point": entry_point,
        "display_name": name.replace("-", " ").title(),
    }
    (plugin_dir / "plugin.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )


def _clean_plugins(root: Path) -> None:
    """Remove the entire src/plugins directory tree."""
    plugins_dir = root / "src" / "plugins"
    if plugins_dir.exists():
        import shutil
        shutil.rmtree(plugins_dir)


class TestPluginDiscoveryEndpoint:
    """Tests for GET /api/v1/plugins/discover."""

    @pytest.fixture(autouse=True)
    def _clear_registry(self):
        """Each test starts with a clean registry."""
        from core.api.registry import get_registry

        reg = get_registry()
        for p in reg.list():
            reg.unregister(p.name)

    def test_discovery_returns_all_valid_plugins(self, client, project_dir):
        _create_manifest(project_dir, "alpha", "2.0.0", "alpha.py")
        _create_manifest(project_dir, "bravo", "1.5.0", "bravo.py")
        _create_manifest(project_dir, "charlie", "3.0.0", "charlie.py")

        resp = client.get("/api/v1/plugins/discover")
        assert resp.status_code == 200
        plugins = resp.json()["plugins"]
        names = [p["name"] for p in plugins]
        assert names == ["alpha", "bravo", "charlie"]
        # Check metadata
        by_name = {p["name"]: p for p in plugins}
        assert by_name["alpha"]["version"] == "2.0.0"
        assert by_name["bravo"]["entry_point"] == "bravo.py"

        _clean_plugins(project_dir)

    def test_disabled_plugins_are_included(self, client, project_dir):
        _create_manifest(project_dir, "offline")

        resp = client.get("/api/v1/plugins/discover")
        assert resp.status_code == 200
        plugins = resp.json()["plugins"]
        assert len(plugins) == 1
        # Not registered → should show as disabled
        assert plugins[0]["enabled"] is False

        _clean_plugins(project_dir)

    def test_enabled_state_matches_registry(self, client, project_dir):
        _create_manifest(project_dir, "toggler")

        # Register the plugin as enabled
        client.post("/api/v1/plugins/register", json={
            "name": "toggler",
            "enabled": True,
        })

        resp = client.get("/api/v1/plugins/discover")
        assert resp.status_code == 200
        plugins = resp.json()["plugins"]
        toggler = next(p for p in plugins if p["name"] == "toggler")
        assert toggler["enabled"] is True

        # Disable via API
        client.post("/api/v1/plugins/toggler/disable")
        resp = client.get("/api/v1/plugins/discover")
        toggler = next(
            p for p in resp.json()["plugins"] if p["name"] == "toggler"
        )
        assert toggler["enabled"] is False

        _clean_plugins(project_dir)

    def test_empty_plugin_directory_returns_empty_list(self, client):
        resp = client.get("/api/v1/plugins/discover")
        assert resp.status_code == 200
        assert resp.json()["plugins"] == []

    def test_output_is_deterministic(self, client, project_dir):
        # Create plugins in reverse alphabetical order
        for name in reversed(["zulu", "yankee", "xray"]):
            _create_manifest(project_dir, name)

        resp1 = client.get("/api/v1/plugins/discover")
        resp2 = client.get("/api/v1/plugins/discover")
        assert resp1.json() == resp2.json()
        names = [p["name"] for p in resp1.json()["plugins"]]
        assert names == ["xray", "yankee", "zulu"]

        _clean_plugins(project_dir)

    def test_no_registry_mutation_from_discovery(self, client, project_dir):
        """Verify that discovery does not register or unregister plugins."""
        _create_manifest(project_dir, "mutant")

        # Before discovery — registry is empty
        before = client.get("/api/v1/plugins")
        assert before.json()["total"] == 0

        # Run discovery
        client.get("/api/v1/plugins/discover")

        # After discovery — registry must still be empty
        after = client.get("/api/v1/plugins")
        assert after.json()["total"] == 0

        _clean_plugins(project_dir)
