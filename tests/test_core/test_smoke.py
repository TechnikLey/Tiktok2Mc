"""Plugin smoke tests — validate real plugin.json files and their structure."""

import json
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PLUGINS_DIR = PROJECT_ROOT / "src" / "plugins"


# ── Known plugin manifest data ───────────────────────────────────────
# Keys are the kebab-case manifest names; "dir" maps to on-disk directory.

EXPECTED_PLUGINS: dict[str, dict[str, object]] = {
    "death-counter": {
        "dir": "deathcounter",
        "display_name": "Death Counter",
    },
    "example-plugin": {
        "dir": "example_plugin",
        "display_name": "Example Plugin",
    },
    "spotify-control": {
        "dir": "spotify",
        "display_name": "Spotify Control",
    },
    "test": {
        "dir": "test",
        "display_name": "Test Plugin",
    },
    "timer": {
        "dir": "timer",
        "display_name": "Timer",
    },
    "win-counter": {
        "dir": "wincounter",
        "display_name": "Win Counter",
    },
}


# ── Helpers ──────────────────────────────────────────────────────────


def _expected_names() -> list[str]:
    return sorted(EXPECTED_PLUGINS)


def _read_manifest(name: str) -> dict:
    info = EXPECTED_PLUGINS[name]
    path = PLUGINS_DIR / info["dir"] / "plugin.json"
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


# ── File structure tests ─────────────────────────────────────────────


class TestPluginManifestFilesExist:
    """Every expected plugin directory contains a plugin.json."""

    def test_all_expected_plugins_have_manifests(self):
        for name in _expected_names():
            info = EXPECTED_PLUGINS[name]
            assert (PLUGINS_DIR / info["dir"] / "plugin.json").is_file(), (
                f"Missing plugin.json for {name}"
            )

    def test_no_unknown_plugin_directories(self):
        found = {d.name for d in PLUGINS_DIR.iterdir() if d.is_dir()}
        expected = {v["dir"] for v in EXPECTED_PLUGINS.values()}
        assert found == expected, f"Unexpected dirs: {found - expected}"


# ── Manifest content tests ────────────────────────────────────────────


class TestPluginManifestContent:
    """Validate the content of each real plugin.json against expectations."""

    @pytest.mark.parametrize("name", _expected_names())
    def test_required_fields_present(self, name):
        manifest = _read_manifest(name)
        for field in ("name", "version", "entry_point", "display_name"):
            assert field in manifest, f"{name}: missing '{field}'"
            assert manifest[field], f"{name}: '{field}' is empty"

    @pytest.mark.parametrize("name", _expected_names())
    def test_entry_point_exists(self, name):
        manifest = _read_manifest(name)
        entry = PROJECT_ROOT / manifest["entry_point"]
        assert entry.is_file(), f"{name}: entry_point {entry} not found"

    @pytest.mark.parametrize("name", _expected_names())
    def test_name_is_kebab_case(self, name):
        manifest = _read_manifest(name)
        assert manifest["name"] == name, (
            f"manifest name '{manifest['name']}' != expected '{name}'"
        )

    @pytest.mark.parametrize("name", _expected_names())
    def test_display_name_matches(self, name):
        manifest = _read_manifest(name)
        expected = EXPECTED_PLUGINS[name]["display_name"]
        assert manifest["display_name"] == expected, (
            f"{name}: display_name '{manifest['display_name']}' != '{expected}'"
        )

    @pytest.mark.parametrize("name", _expected_names())
    def test_version_is_semver(self, name):
        manifest = _read_manifest(name)
        ver = manifest.get("version", "")
        parts = ver.split(".")
        assert len(parts) == 3, f"{name}: version '{ver}' is not semver"
        assert all(p.isdigit() for p in parts), (
            f"{name}: version '{ver}' has non-numeric parts"
        )

    def test_all_plugin_names_are_unique(self):
        names = [_read_manifest(n)["name"] for n in _expected_names()]
        assert len(names) == len(set(names)), "Duplicate plugin names found"

    @pytest.mark.parametrize("name", _expected_names())
    def test_update_url_is_url_or_empty(self, name):
        manifest = _read_manifest(name)
        url = manifest.get("update_url", "")
        if url:
            assert url.startswith("http"), f"{name}: update_url not a URL"


# ── Discovery integration test ────────────────────────────────────────


class TestPluginDiscoveryIntegration:
    """Use PluginLauncher to discover real manifests from the project."""

    def test_discover_all_plugins(self):
        from core.api.launcher import PluginLauncher

        launcher = PluginLauncher(plugins_dir=PLUGINS_DIR)
        manifests = launcher._discover_from_manifests()
        names = {m.name for m in manifests}
        assert names == set(EXPECTED_PLUGINS), (
            f"Missing: {set(EXPECTED_PLUGINS) - names}, "
            f"unexpected: {names - set(EXPECTED_PLUGINS)}"
        )

    def test_discovered_manifests_have_valid_models(self):
        from core.api.launcher import PluginLauncher
        from core.api.models import PluginManifest

        launcher = PluginLauncher(plugins_dir=PLUGINS_DIR)
        for manifest in launcher._discover_from_manifests():
            assert isinstance(manifest, PluginManifest)
            assert manifest.name in EXPECTED_PLUGINS
            assert manifest.entry_point
            assert manifest.display_name
