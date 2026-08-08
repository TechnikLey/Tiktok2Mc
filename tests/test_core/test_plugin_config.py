import json

from core.plugin_config import (
    _deep_update,
    _generate_defaults_from_fields,
    _get_nested,
    _set_nested,
    get_plugin_config_path,
    load_all_plugin_configs,
    load_plugin_config,
    load_plugin_manifest,
    save_plugin_config,
    validate_plugin_config,
)
from core.yaml_utils import save_yaml


class TestNestedHelpers:
    def test_get_nested_simple(self):
        assert _get_nested({"a": 1}, "a") == 1

    def test_get_nested_dotted(self):
        assert _get_nested({"a": {"b": 2}}, "a.b") == 2

    def test_get_nested_missing(self):
        assert _get_nested({}, "a.b", "fallback") == "fallback"

    def test_set_nested_simple(self):
        d = {}
        _set_nested(d, "key", "val")
        assert d == {"key": "val"}

    def test_set_nested_dotted(self):
        d = {}
        _set_nested(d, "a.b.c", 42)
        assert d == {"a": {"b": {"c": 42}}}

    def test_deep_update(self):
        base = {"a": 1, "b": {"x": 10}}
        _deep_update(base, {"b": {"y": 20}, "c": 3})
        assert base == {"a": 1, "b": {"x": 10, "y": 20}, "c": 3}


class TestGenerateDefaults:
    def test_simple_fields(self):
        fields = [
            {"key": "enabled", "type": "boolean", "default": True},
            {"key": "port", "type": "integer", "default": 8080},
        ]
        defaults = _generate_defaults_from_fields(fields)
        assert defaults == {"enabled": True, "port": 8080}

    def test_dotted_keys(self):
        fields = [
            {"key": "theme.background", "type": "color", "default": "#000000"},
        ]
        defaults = _generate_defaults_from_fields(fields)
        assert defaults == {"theme": {"background": "#000000"}}

    def test_array_with_item_schema(self):
        fields = [
            {
                "key": "triggers",
                "type": "array",
                "item_schema": {
                    "type": "object",
                    "fields": [
                        {"key": "id", "type": "string", "default": "default_id"},
                        {"key": "every", "type": "integer", "default": 100},
                    ],
                },
            }
        ]
        defaults = _generate_defaults_from_fields(fields)
        assert defaults == {"triggers": [{"id": "default_id", "every": 100}]}

    def test_no_default_skipped(self):
        fields = [{"key": "secret", "type": "string"}]
        defaults = _generate_defaults_from_fields(fields)
        assert "secret" not in defaults


class TestLoadPluginManifest:
    def test_valid_manifest(self, tmp_path):
        manifest = {"name": "test-plugin", "version": "1.0.0"}
        p = tmp_path / "plugin.json"
        p.write_text(json.dumps(manifest), encoding="utf-8")
        result = load_plugin_manifest(tmp_path)
        assert result["name"] == "test-plugin"

    def test_missing_manifest(self, tmp_path):
        result = load_plugin_manifest(tmp_path)
        assert result is None

    def test_invalid_json(self, tmp_path):
        p = tmp_path / "plugin.json"
        p.write_text("not json", encoding="utf-8")
        result = load_plugin_manifest(tmp_path)
        assert result is None


class TestLoadPluginConfig:
    def test_load_existing_config(self, tmp_path):
        plugin_dir = tmp_path / "myplugin"
        plugin_dir.mkdir()
        manifest = {"name": "myplugin", "config_schema": {"version": 1, "fields": []}}
        (plugin_dir / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
        save_yaml(
            plugin_dir / "config.yaml", {"enabled": True, "port": 1234}, backup=False
        )

        cfg = load_plugin_config(plugin_dir, apply_defaults=False)
        assert cfg["enabled"] is True
        assert cfg["port"] == 1234

    def test_generates_defaults_when_missing(self, tmp_path):
        plugin_dir = tmp_path / "myplugin"
        plugin_dir.mkdir()
        manifest = {
            "name": "myplugin",
            "config_schema": {
                "version": 1,
                "fields": [
                    {"key": "port", "type": "integer", "default": 8080},
                ],
            },
        }
        (plugin_dir / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")

        cfg = load_plugin_config(plugin_dir)
        assert cfg["enabled"] is True  # framework default
        assert cfg["port"] == 8080

    def test_merge_existing_with_defaults(self, tmp_path):
        plugin_dir = tmp_path / "myplugin"
        plugin_dir.mkdir()
        manifest = {
            "name": "myplugin",
            "config_schema": {
                "version": 1,
                "fields": [
                    {"key": "port", "type": "integer", "default": 8080},
                    {"key": "host", "type": "string", "default": "localhost"},
                ],
            },
        }
        (plugin_dir / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
        save_yaml(plugin_dir / "config.yaml", {"port": 9090}, backup=False)

        cfg = load_plugin_config(plugin_dir)
        assert cfg["enabled"] is True  # framework default
        assert cfg["port"] == 9090  # existing
        assert cfg["host"] == "localhost"  # default

    def test_corrupt_config_fallback(self, tmp_path):
        plugin_dir = tmp_path / "myplugin"
        plugin_dir.mkdir()
        manifest = {
            "name": "myplugin",
            "config_schema": {
                "version": 1,
                "fields": [],
            },
        }
        (plugin_dir / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
        (plugin_dir / "config.yaml").write_text(": broken", encoding="utf-8")

        cfg = load_plugin_config(plugin_dir)
        assert cfg["enabled"] is True  # framework default

    def test_no_schema_no_file(self, tmp_path):
        plugin_dir = tmp_path / "myplugin"
        plugin_dir.mkdir()
        manifest = {"name": "myplugin"}
        (plugin_dir / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")

        cfg = load_plugin_config(plugin_dir)
        assert cfg == {"enabled": True}  # framework default


class TestSavePluginConfig:
    def test_atomic_write(self, tmp_path):
        plugin_dir = tmp_path / "myplugin"
        plugin_dir.mkdir()
        manifest = {"name": "myplugin"}
        (plugin_dir / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")

        save_plugin_config(plugin_dir, {"enabled": True, "port": 1234})
        p = get_plugin_config_path(plugin_dir)
        assert p.exists()
        saved = load_plugin_config(plugin_dir, apply_defaults=False)
        assert saved["enabled"] is True
        assert saved["port"] == 1234

    def test_preserves_existing_comments(self, tmp_path):
        plugin_dir = tmp_path / "myplugin"
        plugin_dir.mkdir()
        manifest = {"name": "myplugin"}
        (plugin_dir / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")

        config_path = plugin_dir / "config.yaml"
        config_path.write_text(
            "# Keep this comment\nenabled: false\n", encoding="utf-8"
        )

        save_plugin_config(plugin_dir, {"port": 9999})
        content = config_path.read_text(encoding="utf-8")
        assert "# Keep this comment" in content
        assert "enabled: false" in content
        assert "port: 9999" in content

    def test_overwrites_existing_values(self, tmp_path):
        plugin_dir = tmp_path / "myplugin"
        plugin_dir.mkdir()
        manifest = {"name": "myplugin"}
        (plugin_dir / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")

        save_plugin_config(plugin_dir, {"enabled": True})
        save_plugin_config(plugin_dir, {"enabled": False})
        saved = load_plugin_config(plugin_dir, apply_defaults=False)
        assert saved["enabled"] is False


class TestValidatePluginConfig:
    def test_valid_config(self):
        schema = {
            "fields": [
                {"key": "enabled", "type": "boolean"},
                {"key": "port", "type": "integer", "min": 1024, "max": 65535},
            ]
        }
        data = {"enabled": True, "port": 8080}
        errors = validate_plugin_config(data, schema)
        assert errors == []

    def test_invalid_type(self):
        schema = {"fields": [{"key": "enabled", "type": "boolean"}]}
        errors = validate_plugin_config({"enabled": "yes"}, schema)
        assert any("must be a boolean" in e for e in errors)

    def test_integer_out_of_range(self):
        schema = {
            "fields": [{"key": "port", "type": "integer", "min": 1024, "max": 65535}]
        }
        errors = validate_plugin_config({"port": 100}, schema)
        assert any("must be >= 1024" in e for e in errors)

        errors = validate_plugin_config({"port": 100000}, schema)
        assert any("must be <= 65535" in e for e in errors)

    def test_required_field(self):
        schema = {"fields": [{"key": "name", "type": "string", "required": True}]}
        errors = validate_plugin_config({}, schema)
        assert any("is required" in e for e in errors)

    def test_invalid_color(self):
        schema = {"fields": [{"key": "bg", "type": "color"}]}
        errors = validate_plugin_config({"bg": "red"}, schema)
        assert any("hex color" in e for e in errors)

        errors = validate_plugin_config({"bg": "#FF0000"}, schema)
        assert errors == []

    def test_select_validation(self):
        schema = {"fields": [{"key": "mode", "type": "select", "options": ["a", "b"]}]}
        errors = validate_plugin_config({"mode": "c"}, schema)
        assert any("must be one of" in e for e in errors)

    def test_array_item_validation(self):
        schema = {
            "fields": [
                {
                    "key": "items",
                    "type": "array",
                    "item_schema": {
                        "type": "object",
                        "fields": [{"key": "id", "type": "string", "required": True}],
                    },
                }
            ]
        }
        errors = validate_plugin_config({"items": [{"id": ""}]}, schema)
        assert any("is required" in e for e in errors)

    def test_no_schema_returns_empty(self):
        errors = validate_plugin_config({"anything": 1}, None)
        assert errors == []

    def test_dotted_key_validation(self):
        schema = {"fields": [{"key": "theme.background", "type": "color"}]}
        errors = validate_plugin_config({"theme": {"background": "#000000"}}, schema)
        assert errors == []


class TestLoadAllPluginConfigs:
    def test_discovers_and_loads(self, tmp_path, monkeypatch):
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()

        # Plugin A
        a_dir = plugins_dir / "plugin-a"
        a_dir.mkdir()
        (a_dir / "plugin.json").write_text(
            json.dumps({"name": "plugin-a"}), encoding="utf-8"
        )
        save_yaml(a_dir / "config.yaml", {"enabled": True}, backup=False)

        # Plugin B
        b_dir = plugins_dir / "plugin-b"
        b_dir.mkdir()
        (b_dir / "plugin.json").write_text(
            json.dumps({"name": "plugin-b"}), encoding="utf-8"
        )
        save_yaml(b_dir / "config.yaml", {"enabled": False}, backup=False)

        monkeypatch.setattr(
            "core.plugin_config.discover_plugins_dir", lambda: plugins_dir
        )

        result = load_all_plugin_configs()
        assert result["plugin-a"]["enabled"] is True
        assert result["plugin-b"]["enabled"] is False

    def test_skips_broken_plugins(self, tmp_path, monkeypatch):
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()

        good_dir = plugins_dir / "good"
        good_dir.mkdir()
        (good_dir / "plugin.json").write_text(
            json.dumps({"name": "good"}), encoding="utf-8"
        )
        save_yaml(good_dir / "config.yaml", {"ok": True}, backup=False)

        bad_dir = plugins_dir / "bad"
        bad_dir.mkdir()
        (bad_dir / "plugin.json").write_text("not json", encoding="utf-8")

        monkeypatch.setattr(
            "core.plugin_config.discover_plugins_dir", lambda: plugins_dir
        )

        result = load_all_plugin_configs()
        assert "good" in result


class TestConfigValidationOnLoad:
    def test_valid_config_preserved(self, tmp_path):
        plugin_dir = tmp_path / "test-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(
            json.dumps(
                {
                    "name": "test-plugin",
                    "config_schema": {
                        "fields": [
                            {"key": "port", "type": "integer", "default": 8080},
                        ],
                    },
                }
            ),
            encoding="utf-8",
        )
        save_yaml(
            plugin_dir / "config.yaml", {"enabled": False, "port": 9090}, backup=False
        )
        cfg = load_plugin_config(plugin_dir)
        assert cfg["enabled"] is False  # preserved from config
        assert cfg["port"] == 9090

    def test_invalid_value_healed_on_load(self, tmp_path):
        plugin_dir = tmp_path / "test-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(
            json.dumps(
                {
                    "name": "test-plugin",
                    "config_schema": {
                        "fields": [],
                    },
                }
            ),
            encoding="utf-8",
        )
        # enabled is "yes" (string) instead of boolean — should be corrected
        save_yaml(plugin_dir / "config.yaml", {"enabled": "yes"}, backup=False)
        cfg = load_plugin_config(plugin_dir)
        assert cfg["enabled"] is True  # corrected by framework

    def test_invalid_value_without_default_logs_warning(self, tmp_path, caplog):
        plugin_dir = tmp_path / "test-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(
            json.dumps(
                {
                    "name": "test-plugin",
                    "config_schema": {
                        "fields": [
                            {"key": "color", "type": "color"},
                        ],
                    },
                }
            ),
            encoding="utf-8",
        )
        save_yaml(plugin_dir / "config.yaml", {"color": "not-a-color"}, backup=False)
        cfg = load_plugin_config(plugin_dir)
        # value is kept as-is but a warning is logged (no default to heal to)
        assert cfg["color"] == "not-a-color"
        assert any("validation warning" in r.message for r in caplog.records)

    def test_healing_logs_warning(self, tmp_path, caplog):
        plugin_dir = tmp_path / "test-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(
            json.dumps(
                {
                    "name": "test-plugin",
                    "config_schema": {
                        "fields": [
                            {"key": "port", "type": "integer", "default": 8080},
                        ],
                    },
                }
            ),
            encoding="utf-8",
        )
        # enabled is a framework field; invalid value is corrected by
        # framework injection (not schema healing)
        save_yaml(plugin_dir / "config.yaml", {"enabled": "bad-value"}, backup=False)
        cfg = load_plugin_config(plugin_dir)
        assert cfg["enabled"] is True  # corrected by framework
        # port is invalid — healing should kick in for non-framework fields
        save_yaml(plugin_dir / "config.yaml", {"port": "not-a-number"}, backup=False)
        cfg = load_plugin_config(plugin_dir)
        assert cfg["port"] == 8080
        assert any("Healing" in r.message for r in caplog.records)
