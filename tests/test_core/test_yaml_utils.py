import pytest
from pathlib import Path

from core.yaml_utils import create_yaml_rt, load_yaml, save_yaml, deep_update_rt


class TestLoadYaml:
    def test_load_valid_mapping(self, tmp_path):
        p = tmp_path / "test.yaml"
        p.write_text("key: value\nnested:\n  a: 1\n", encoding="utf-8")
        data = load_yaml(p)
        assert data["key"] == "value"
        assert data["nested"]["a"] == 1

    def test_load_empty_file(self, tmp_path):
        p = tmp_path / "empty.yaml"
        p.write_text("", encoding="utf-8")
        data = load_yaml(p)
        assert data == {}

    def test_load_missing_file_raises(self, tmp_path):
        p = tmp_path / "missing.yaml"
        with pytest.raises(FileNotFoundError):
            load_yaml(p)

    def test_load_malformed_yaml_raises(self, tmp_path):
        p = tmp_path / "bad.yaml"
        p.write_text(": broken yaml [", encoding="utf-8")
        with pytest.raises(ValueError):
            load_yaml(p)

    def test_load_preserves_comments(self, tmp_path):
        p = tmp_path / "with_comments.yaml"
        p.write_text(
            "# Section header\nkey: value  # inline\n", encoding="utf-8"
        )
        data = load_yaml(p)
        assert data["key"] == "value"
        # ruamel.yaml stores comments internally; verify round-trip below

    def test_load_preserves_quotes(self, tmp_path):
        p = tmp_path / "quotes.yaml"
        p.write_text('host: "127.0.0.1"\n', encoding="utf-8")
        data = load_yaml(p)
        assert data["host"] == "127.0.0.1"


class TestSaveYaml:
    def test_save_creates_file(self, tmp_path):
        p = tmp_path / "out.yaml"
        yaml = create_yaml_rt()
        data = yaml.load("key: value\n")
        save_yaml(p, data, backup=False)
        assert p.exists()
        assert "key: value" in p.read_text(encoding="utf-8")

    def test_save_backup(self, tmp_path, monkeypatch):
        from core.backup import BackupManager
        bm = BackupManager(root_dir=tmp_path)
        monkeypatch.setattr("core.yaml_utils.get_backup_manager", lambda: bm)
        p = tmp_path / "out.yaml"
        p.write_text("old: data\n", encoding="utf-8")
        yaml = create_yaml_rt()
        data = yaml.load("new: data\n")
        save_yaml(p, data, backup=True)
        backups = list((tmp_path / "data" / "backups" / "_other").glob("*"))
        assert len(backups) == 1
        assert "old: data" in backups[0].read_text(encoding="utf-8")

    def test_save_atomic(self, tmp_path):
        p = tmp_path / "atomic.yaml"
        yaml = create_yaml_rt()
        data = yaml.load("safe: true\n")
        save_yaml(p, data, backup=False)
        assert p.exists()
        assert ".tmp" not in [f.name for f in tmp_path.iterdir()]


class TestRoundTripPreservation:
    def test_section_comments_preserved(self, tmp_path):
        p = tmp_path / "rt.yaml"
        original = (
            "# Server settings\n"
            "server_host: \"127.0.0.1\"  # local only\n"
            "\n"
            "# Java settings\n"
            "java:\n"
            "  xms: 4G  # initial RAM\n"
            "  xmx: 4G  # maximum RAM\n"
            "\n"
            "# Random comment\n"
            "random_triggers:\n"
            "  mode: deny-all\n"
        )
        p.write_text(original, encoding="utf-8")

        data = load_yaml(p)
        data["server_host"] = "0.0.0.0"
        deep_update_rt(data, {"java": {"xms": "2G"}})
        save_yaml(p, data, backup=False)

        content = p.read_text(encoding="utf-8")
        assert "# Server settings" in content
        assert "# local only" in content
        assert "# initial RAM" in content
        assert "# Random comment" in content
        assert "server_host: \"0.0.0.0\"" in content
        assert "xms: 2G" in content

    def test_unknown_keys_and_comments_preserved(self, tmp_path):
        p = tmp_path / "rt.yaml"
        original = (
            "known: 1\n"
            "# user comment\n"
            "unknown: value\n"
        )
        p.write_text(original, encoding="utf-8")

        data = load_yaml(p)
        data["known"] = 2
        deep_update_rt(data, {"new_key": "new_val"})
        save_yaml(p, data, backup=False)

        content = p.read_text(encoding="utf-8")
        assert "unknown: value" in content
        assert "# user comment" in content
        assert "new_key: new_val" in content
        assert "known: 2" in content

    def test_nested_dict_comments_preserved(self, tmp_path):
        p = tmp_path / "nested.yaml"
        original = (
            "theme:\n"
            "  # Background color\n"
            "  background: \"#000000\"\n"
            "  text: \"#ffffff\"\n"
        )
        p.write_text(original, encoding="utf-8")

        data = load_yaml(p)
        deep_update_rt(data, {"theme": {"background": "#111111"}})
        save_yaml(p, data, backup=False)

        content = p.read_text(encoding="utf-8")
        assert "# Background color" in content
        assert "background: \"#111111\"" in content
        assert "text: \"#ffffff\"" in content

    def test_array_comments_partially_preserved(self, tmp_path):
        p = tmp_path / "arr.yaml"
        original = (
            "items:\n"
            "  - a: 1\n"
            "  - a: 2\n"
        )
        p.write_text(original, encoding="utf-8")

        data = load_yaml(p)
        # Update first item, keep second
        deep_update_rt(data, {"items": [{"a": 10}]})
        save_yaml(p, data, backup=False)

        content = p.read_text(encoding="utf-8")
        assert "a: 10" in content


class TestDeepUpdateRt:
    def test_updates_existing_keys(self):
        yaml = create_yaml_rt()
        base = yaml.load("key: 1\n")
        deep_update_rt(base, {"key": 2})
        assert base["key"] == 2

    def test_adds_new_keys(self):
        yaml = create_yaml_rt()
        base = yaml.load("old: 1\n")
        deep_update_rt(base, {"new": 2})
        assert base["old"] == 1
        assert base["new"] == 2

    def test_nested_merge(self):
        yaml = create_yaml_rt()
        base = yaml.load("a:\n  b: 1\n  c: 2\n")
        deep_update_rt(base, {"a": {"b": 10}})
        assert base["a"]["b"] == 10
        assert base["a"]["c"] == 2

    def test_does_not_delete_untouched_keys(self):
        yaml = create_yaml_rt()
        base = yaml.load("a: 1\nb: 2\n")
        deep_update_rt(base, {"a": 10})
        assert base["a"] == 10
        assert base["b"] == 2
