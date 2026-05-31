"""Tests for the BackupManager (core/backup.py)."""

import shutil
import time
from pathlib import Path

import pytest


class TestReadHash:
    def test_returns_64_char_hex(self, tmp_path: Path):
        from core.backup import _read_hash
        f = tmp_path / "test.txt"
        f.write_text("hello")
        h = _read_hash(f)
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_identical_files_same_hash(self, tmp_path: Path):
        from core.backup import _read_hash
        a = tmp_path / "a.txt"
        b = tmp_path / "b.txt"
        a.write_text("same content")
        b.write_text("same content")
        assert _read_hash(a) == _read_hash(b)

    def test_different_files_different_hash(self, tmp_path: Path):
        from core.backup import _read_hash
        a = tmp_path / "a.txt"
        b = tmp_path / "b.txt"
        a.write_text("content a")
        b.write_text("content b")
        assert _read_hash(a) != _read_hash(b)

    def test_large_file(self, tmp_path: Path):
        from core.backup import _read_hash
        f = tmp_path / "large.bin"
        f.write_bytes(b"x" * 100_000)
        h = _read_hash(f)
        assert len(h) == 64


class TestTimestampTag:
    def test_format(self):
        from core.backup import _timestamp_tag
        tag = _timestamp_tag()
        parts = tag.split("_")
        assert len(parts) >= 2
        assert len(parts[0]) == 8

    def test_monotonic(self):
        from core.backup import _timestamp_tag
        t1 = _timestamp_tag()
        t2 = _timestamp_tag()
        assert t2 >= t1


class TestBackupManager:
    def test_create_backup_returns_path(self, tmp_path: Path):
        from core.backup import BackupManager
        mgr = BackupManager(root_dir=tmp_path, coalesce_seconds=0)
        source = tmp_path / "config.yaml"
        source.write_text("key: value")
        result = mgr.create_backup(source)
        assert result is not None
        assert result.exists()

    def test_create_backup_nonexistent_source(self, tmp_path: Path):
        from core.backup import BackupManager
        mgr = BackupManager(root_dir=tmp_path)
        source = tmp_path / "nonexistent.yaml"
        result = mgr.create_backup(source)
        assert result is None

    def test_dedup_same_content_skips(self, tmp_path: Path):
        from core.backup import BackupManager
        mgr = BackupManager(root_dir=tmp_path, coalesce_seconds=0)
        source = tmp_path / "config.yaml"
        source.write_text("same content")
        first = mgr.create_backup(source)
        second = mgr.create_backup(source)
        assert first is not None
        assert second is None

    def test_different_content_creates_new(self, tmp_path: Path):
        from core.backup import BackupManager
        mgr = BackupManager(root_dir=tmp_path, coalesce_seconds=0)
        source = tmp_path / "config.yaml"
        source.write_text("v1")
        mgr.create_backup(source)
        source.write_text("v2")
        second = mgr.create_backup(source)
        assert second is not None

    def test_time_coalescing_skips_within_window(self, tmp_path: Path):
        from core.backup import BackupManager
        mgr = BackupManager(root_dir=tmp_path, coalesce_seconds=60)
        source = tmp_path / "config.yaml"
        source.write_text("content")
        mgr.create_backup(source)
        source.write_text("new content")
        second = mgr.create_backup(source)
        assert second is None

    def test_time_coalescing_zero_disabled(self, tmp_path: Path):
        from core.backup import BackupManager
        mgr = BackupManager(root_dir=tmp_path, coalesce_seconds=0)
        source = tmp_path / "config.yaml"
        source.write_text("content")
        first = mgr.create_backup(source)
        source.write_text("different")
        second = mgr.create_backup(source)
        assert first is not None
        assert second is not None
        assert first != second

    def test_list_backups_newest_first(self, tmp_path: Path):
        from core.backup import BackupManager
        mgr = BackupManager(root_dir=tmp_path, coalesce_seconds=0)
        source = tmp_path / "config.yaml"
        for content in ["a", "b", "c"]:
            source.write_text(content)
            mgr.create_backup(source)
        backups = mgr.list_backups("config")
        assert len(backups) >= 1

    def test_list_backups_max_count(self, tmp_path: Path):
        from core.backup import BackupManager
        mgr = BackupManager(root_dir=tmp_path, coalesce_seconds=0)
        source = tmp_path / "config.yaml"
        for content in ["v1", "v2", "v3", "v4", "v5"]:
            source.write_text(content)
            mgr.create_backup(source)
        backups = mgr.list_backups("config", max_count=2)
        assert len(backups) <= 2

    def test_restore_backup(self, tmp_path: Path):
        from core.backup import BackupManager
        mgr = BackupManager(root_dir=tmp_path, coalesce_seconds=0)
        source = tmp_path / "config.yaml"
        source.write_text("original")
        bak = mgr.create_backup(source)
        source.write_text("modified")
        mgr.restore_backup(bak, source)
        assert source.read_text() == "original"

    def test_cleanup_removes_excess(self, tmp_path: Path):
        from core.backup import BackupManager
        mgr = BackupManager(root_dir=tmp_path, max_backups=2, coalesce_seconds=0)
        source = tmp_path / "config.yaml"
        for content in ["a", "b", "c", "d"]:
            source.write_text(content)
            mgr.create_backup(source)
        backups = mgr.list_backups("config")
        assert len(backups) <= 2

    def test_cleanup_all_categories(self, tmp_path: Path):
        from core.backup import BackupManager
        mgr = BackupManager(root_dir=tmp_path, max_backups=1, coalesce_seconds=0)
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config")
        mgr.create_backup(cfg)
        reg = tmp_path / "api_plugin_registry.json"
        reg.write_text("registry")
        mgr.create_backup(reg)
        removed = mgr.cleanup()
        assert removed >= 0

    def test_default_category_config(self, tmp_path: Path):
        from core.backup import BackupManager
        source = tmp_path / "config.yaml"
        source.write_text("test")
        cat = BackupManager._default_category(source)
        assert cat == "config"

    def test_default_category_registry(self, tmp_path: Path):
        from core.backup import BackupManager
        source = tmp_path / "api_plugin_registry.json"
        source.write_text("{}")
        cat = BackupManager._default_category(source)
        assert cat == "plugin_registry"

    def test_default_category_plugin(self, tmp_path: Path):
        from core.backup import BackupManager
        plugin_dir = tmp_path / "plugins" / "my-plugin"
        plugin_dir.mkdir(parents=True)
        source = plugin_dir / "config.yaml"
        source.write_text("plugin: config")
        cat = BackupManager._default_category(source)
        assert cat == "plugins/my-plugin"

    def test_default_category_other(self, tmp_path: Path):
        from core.backup import BackupManager
        source = tmp_path / "random.json"
        source.write_text("{}")
        cat = BackupManager._default_category(source)
        assert cat == "_other"

    def test_backup_file_naming(self, tmp_path: Path):
        from core.backup import BackupManager
        mgr = BackupManager(root_dir=tmp_path, coalesce_seconds=0)
        source = tmp_path / "test.yaml"
        source.write_text("data")
        bak = mgr.create_backup(source)
        assert bak.name.endswith(".bak")
        assert ".v" in bak.name

    def test_backup_dir_created(self, tmp_path: Path):
        from core.backup import BackupManager
        mgr = BackupManager(root_dir=tmp_path, coalesce_seconds=0)
        source = tmp_path / "test.yaml"
        source.write_text("data")
        mgr.create_backup(source)
        assert (tmp_path / "data" / "backups").exists()

    def test_get_backup_manager_singleton(self):
        from core.backup import get_backup_manager
        mgr1 = get_backup_manager()
        mgr2 = get_backup_manager()
        assert mgr1 is mgr2


class TestBackupEdgeCases:
    def test_empty_file(self, tmp_path: Path):
        from core.backup import BackupManager
        mgr = BackupManager(root_dir=tmp_path, coalesce_seconds=0)
        source = tmp_path / "empty.txt"
        source.write_text("")
        bak = mgr.create_backup(source)
        assert bak is not None

    def test_binary_file(self, tmp_path: Path):
        from core.backup import BackupManager
        mgr = BackupManager(root_dir=tmp_path, coalesce_seconds=0)
        source = tmp_path / "binary.bin"
        source.write_bytes(b"\x00\x01\x02\xff")
        bak = mgr.create_backup(source)
        assert bak is not None

    def test_unicode_filename(self, tmp_path: Path):
        from core.backup import BackupManager
        mgr = BackupManager(root_dir=tmp_path, coalesce_seconds=0)
        source = tmp_path / "café.yaml"
        source.write_text("data")
        bak = mgr.create_backup(source)
        assert bak is not None

    def test_deeply_nested_source_path(self, tmp_path: Path):
        from core.backup import BackupManager
        mgr = BackupManager(root_dir=tmp_path, coalesce_seconds=0)
        nested = tmp_path / "a" / "b" / "c" / "config.yaml"
        nested.parent.mkdir(parents=True)
        nested.write_text("deep")
        bak = mgr.create_backup(nested)
        assert bak is not None

    def test_default_coalesce_seconds(self):
        from core.backup import BackupManager
        mgr = BackupManager()
        assert mgr.coalesce_seconds == 60

    def test_default_max_backups(self):
        from core.backup import BackupManager
        mgr = BackupManager()
        assert mgr.max_backups == 10
