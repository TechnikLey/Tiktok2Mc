import json
import pytest
from pathlib import Path

from core.api.plugin_watcher import PluginWatcher, _get_plugin_dirs
from core.api.registry import get_registry


class TestPluginDirs:
    def test_get_plugin_dirs_empty(self, tmp_path: Path):
        assert _get_plugin_dirs(tmp_path) == {}

    def test_get_plugin_dirs_with_manifest(self, tmp_path: Path):
        plugin_dir = tmp_path / "my-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(
            json.dumps({"name": "my-plugin", "version": "1.0.0"}),
            encoding="utf-8",
        )
        result = _get_plugin_dirs(tmp_path)
        assert result == {"my-plugin": plugin_dir}

    def test_get_plugin_dirs_skips_invalid_manifests(self, tmp_path: Path):
        plugin_dir = tmp_path / "bad"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text("not json", encoding="utf-8")
        assert _get_plugin_dirs(tmp_path) == {}

    def test_get_plugin_dirs_skips_missing_name(self, tmp_path: Path):
        plugin_dir = tmp_path / "no-name"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(
            json.dumps({"version": "1.0.0"}), encoding="utf-8",
        )
        assert _get_plugin_dirs(tmp_path) == {}


class TestPluginWatcherSync:
    @pytest.fixture(autouse=True)
    def _clear_registry(self):
        reg = get_registry()
        for p in reg.list():
            reg.unregister(p.name)

    def test_sync_registers_new_plugin(self, tmp_path: Path):
        reg = get_registry()
        watcher = PluginWatcher(plugins_dir=tmp_path)

        # Create a plugin directory and manifest
        plugin_dir = tmp_path / "new-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(
            json.dumps({
                "name": "new-plugin",
                "version": "1.0.0",
                "entry_point": "main.py",
            }),
            encoding="utf-8",
        )

        watcher._sync()
        assert reg.get("new-plugin") is not None
        assert reg.get("new-plugin").name == "new-plugin"

    def test_sync_unregisters_removed_plugin(self, tmp_path: Path):
        reg = get_registry()
        plugin_dir = tmp_path / "gone-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(
            json.dumps({"name": "gone-plugin", "version": "1.0.0"}),
            encoding="utf-8",
        )

        watcher = PluginWatcher(plugins_dir=tmp_path)
        watcher._known = {"gone-plugin"}
        watcher._sync()
        assert reg.get("gone-plugin") is None

    def test_sync_idempotent_on_no_changes(self, tmp_path: Path):
        reg = get_registry()
        plugin_dir = tmp_path / "stable"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(
            json.dumps({"name": "stable", "version": "1.0.0"}),
            encoding="utf-8",
        )

        watcher = PluginWatcher(plugins_dir=tmp_path)
        watcher._sync()
        before = len(reg.list())
        watcher._sync()
        after = len(reg.list())
        assert before == after == 1
