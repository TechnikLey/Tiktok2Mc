"""Tests for ``core.config_migration`` (P3a: config migration moved out of the
updater binary into a reusable core module — the launcher first-start hook
calls it, see ``src/python/start.py``)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from ruamel.yaml import YAML

from core.config_migration import (
    _inject_values_strictly,
    load_yaml_with_debug,
    migrate_config,
)

# =========================================================================
# _inject_values_strictly — pure config injection logic
# =========================================================================


class TestInjectValuesStrictly:
    def test_preserves_user_values(self):
        template = {"server_host": "0.0.0.0", "config_version": "1.0"}
        user = {"server_host": "127.0.0.1", "config_version": "1.0"}
        _inject_values_strictly(template, user)
        assert template["server_host"] == "127.0.0.1"
        assert template["config_version"] == "1.0"

    def test_keeps_default_when_user_missing_key(self):
        template = {"server_host": "0.0.0.0", "java": {"xms": "512M"}}
        user = {"server_host": "127.0.0.1"}
        _inject_values_strictly(template, user)
        assert template["server_host"] == "127.0.0.1"
        assert template["java"]["xms"] == "512M"

    def test_recursive_nested_dicts(self):
        template = {"java": {"xms": "512M", "xmx": "1G"}, "rcon": {"port": 25575}}
        user = {"java": {"xms": "1G"}, "rcon": {}}
        _inject_values_strictly(template, user)
        assert template["java"]["xms"] == "1G"
        assert template["java"]["xmx"] == "1G"
        assert template["rcon"]["port"] == 25575

    def test_skips_user_keys_not_in_template(self):
        template = {"server_host": "0.0.0.0"}
        user = {"server_host": "127.0.0.1", "unknown_key": "should_be_dropped"}
        _inject_values_strictly(template, user)
        assert template["server_host"] == "127.0.0.1"
        assert "unknown_key" not in template

    def test_preserves_booleans_and_numbers(self):
        template = {"auto_update_config": False, "control_method": "DCS"}
        user = {"auto_update_config": True, "control_method": "RCON"}
        _inject_values_strictly(template, user)
        assert template["auto_update_config"] is True
        assert template["control_method"] == "RCON"

    def test_handles_none_user_value(self):
        template = {"server_host": "0.0.0.0", "shutdown": {}}
        user = {"server_host": None, "shutdown": None}
        _inject_values_strictly(template, user)
        assert template["server_host"] == "0.0.0.0"
        assert template["shutdown"] == {}

    def test_handles_none_user_source_root(self):
        template = {"config_version": "1.0"}
        _inject_values_strictly(template, None)
        assert template["config_version"] == "1.0"

    def test_handles_empty_user_source(self):
        template = {"server_host": "0.0.0.0"}
        _inject_values_strictly(template, {})
        assert template["server_host"] == "0.0.0.0"

    def test_overwrites_template_list_with_user_list(self):
        template = {"shutdown": {"countdown_times": [5, 10, 30]}}
        user = {"shutdown": {"countdown_times": [10, 20, 60]}}
        _inject_values_strictly(template, user)
        assert template["shutdown"]["countdown_times"] == [10, 20, 60]


# =========================================================================
# load_yaml_with_debug
# =========================================================================


class TestLoadYamlWithDebug:
    def test_valid_yaml(self, tmp_path: Path):
        yaml_obj = YAML(typ="rt")
        f = tmp_path / "valid.yaml"
        f.write_text("key: value\n", encoding="utf-8")
        assert load_yaml_with_debug(f, yaml_obj, "T") == {"key": "value"}

    def test_empty_yaml_returns_empty_map(self, tmp_path: Path):
        yaml_obj = YAML(typ="rt")
        f = tmp_path / "empty.yaml"
        f.write_text("", encoding="utf-8")
        assert load_yaml_with_debug(f, yaml_obj, "T") == {}

    def test_invalid_yaml_returns_none(self, tmp_path: Path):
        yaml_obj = YAML(typ="rt")
        f = tmp_path / "bad.yaml"
        f.write_text("key: [unclosed\n  broken: :\n", encoding="utf-8")
        assert load_yaml_with_debug(f, yaml_obj, "T") is None

    def test_missing_file_returns_none(self, tmp_path: Path):
        yaml_obj = YAML(typ="rt")
        assert load_yaml_with_debug(tmp_path / "nope.yaml", yaml_obj, "T") is None


# =========================================================================
# migrate_config
# =========================================================================


class TestMigrateConfig:
    def _patch_backup(self, tmp_path: Path):
        from core.backup import BackupManager

        bm = BackupManager(root_dir=tmp_path)
        return (
            patch("core.config_migration.get_backup_manager", return_value=bm),
            patch("core.backup.get_backup_manager", return_value=bm),
        )

    def test_creates_config_when_missing(self, tmp_path: Path):
        default_config = tmp_path / "config.default.yaml"
        user_config = tmp_path / "config.yaml"
        default_config.write_text(
            "server_host: 127.0.0.1\nconfig_version: '1.0'\n", encoding="utf-8"
        )
        with (
            patch("core.config_migration.get_backup_manager", return_value=None),
        ):
            assert migrate_config(user_config, default_config, yaml_obj=_yaml()) is True
        assert user_config.exists()

    def test_skips_when_up_to_date(self, tmp_path: Path):
        default_config = tmp_path / "config.default.yaml"
        user_config = tmp_path / "config.yaml"
        default_config.write_text("config_version: '1.0'\n", encoding="utf-8")
        user_config.write_text("config_version: '1.0'\n", encoding="utf-8")
        with (
            patch("core.config_migration.get_backup_manager", return_value=None),
        ):
            assert (
                migrate_config(user_config, default_config, yaml_obj=_yaml()) is False
            )

    def test_migrates_legacy_version(self, tmp_path: Path):
        default_config = tmp_path / "config.default.yaml"
        user_config = tmp_path / "config.yaml"
        default_config.write_text(
            "config_version: '1.0'\nserver_host: 0.0.0.0\n", encoding="utf-8"
        )
        user_config.write_text(
            "config_version: '0.7'\nserver_host: 127.0.0.1\n", encoding="utf-8"
        )
        with self._patch_backup(tmp_path)[0]:
            assert migrate_config(user_config, default_config, yaml_obj=_yaml()) is True

        content = user_config.read_text(encoding="utf-8")
        assert "config_version: '1.0'" in content
        assert "server_host: 127.0.0.1" in content

    def test_migrates_legacy_int_version(self, tmp_path: Path):
        default_config = tmp_path / "config.default.yaml"
        user_config = tmp_path / "config.yaml"
        default_config.write_text(
            "config_version: '1.0'\nserver_host: 0.0.0.0\n", encoding="utf-8"
        )
        user_config.write_text(
            "config_version: 7\nserver_host: 192.168.1.1\n", encoding="utf-8"
        )
        with self._patch_backup(tmp_path)[0]:
            assert migrate_config(user_config, default_config, yaml_obj=_yaml()) is True

        content = user_config.read_text(encoding="utf-8")
        assert "server_host: 192.168.1.1" in content

    def test_returns_false_when_default_missing(self, tmp_path: Path):
        user_config = tmp_path / "config.yaml"
        assert (
            migrate_config(user_config, tmp_path / "missing.yaml", yaml_obj=_yaml())
            is False
        )


def _yaml() -> YAML:
    yaml_obj = YAML(typ="rt")
    yaml_obj.preserve_quotes = True
    yaml_obj.indent(mapping=2, sequence=4, offset=2)
    yaml_obj.width = 120
    return yaml_obj
