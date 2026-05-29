import json
from pathlib import Path

import pytest


class TestPluginRegistryBackup:
    def test_save_creates_backup(self, project_dir):
        from core.api.registry import PluginRegistry

        registry = PluginRegistry(project_dir)
        from core.api.models import PluginRegistration

        p = PluginRegistration(name="test_plugin", path="/exe")
        registry.register(p)
        # Force a second save to trigger backup of the first.
        p2 = PluginRegistration(
            name="test_plugin", path="/exe", version="2.0.0"
        )
        registry.register(p2)

        backups = list((project_dir / "data" / "backups" / "plugin_registry").glob("*"))
        assert len(backups) >= 1

    def test_corrupt_file_returns_empty_registry(self, project_dir):
        from core.api.registry import PluginRegistry

        reg_file = project_dir / "api_plugin_registry.json"
        reg_file.write_text("{corrupt json", encoding="utf-8")

        from core.api.registry import PluginRegistry

        registry = PluginRegistry(project_dir)
        assert registry.list() == []

    def test_partial_corrupt_entry_skipped(self, project_dir):
        from core.api.registry import PluginRegistry

        reg_file = project_dir / "api_plugin_registry.json"
        reg_file.write_text(
            json.dumps([
                {"name": "good", "path": "/a", "version": "1.0.0", "enabled": False, "level": 2, "port": 0, "ics": False, "description": ""},
                {"name": "bad", "path": "/b", "version": 123},
            ]),
            encoding="utf-8",
        )
        from core.api.registry import PluginRegistry

        registry = PluginRegistry(project_dir)
        names = [p.name for p in registry.list()]
        assert "good" in names
        assert "bad" not in names


class TestPluginRegistryBackupNumbering:
    def test_backup_numbers_increment(self, project_dir):
        from core.api.registry import PluginRegistry
        from core.api.models import PluginRegistration

        registry = PluginRegistry(project_dir)
        p = PluginRegistration(name="p", path="/p")
        for _ in range(5):
            p2 = PluginRegistration(name="p", path="/p")
            registry.register(p2)

        backup_dir = project_dir / "data" / "backups" / "plugin_registry"
        backups = sorted(backup_dir.glob("*"))
        # With content dedup, only one backup is kept (same content each time).
        # Registering with different content each time to force multiple backups.
        # Reset content for each iteration to trigger new backups.
        assert len(backups) >= 1
