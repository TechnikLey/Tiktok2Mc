import json


class TestDiscoverPluginsFromManifests:
    def test_directory_not_found_returns_empty(self):
        from core.api.services.plugin_discovery import discover_plugins_from_manifests

        result = discover_plugins_from_manifests("/nonexistent/path")
        assert result == []

    def test_empty_plugins_dir(self, tmp_path):
        from core.api.services.plugin_discovery import discover_plugins_from_manifests

        d = tmp_path / "plugins"
        d.mkdir()
        result = discover_plugins_from_manifests(str(d))
        assert result == []

    def test_valid_plugin(self, tmp_path):
        from core.api.services.plugin_discovery import discover_plugins_from_manifests

        plugin_dir = tmp_path / "plugins" / "my_plugin"
        plugin_dir.mkdir(parents=True)
        manifest = {"name": "my_plugin", "version": "1.2.3", "entry_point": "main.py"}
        (plugin_dir / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
        result = discover_plugins_from_manifests(str(tmp_path / "plugins"))
        assert len(result) == 1
        assert result[0]["name"] == "my_plugin"
        assert result[0]["version"] == "1.2.3"
        assert result[0]["entry_point"] == "main.py"
        assert result[0]["enabled_by_registry"] is False

    def test_plugin_with_defaults(self, tmp_path):
        from core.api.services.plugin_discovery import discover_plugins_from_manifests

        plugin_dir = tmp_path / "plugins" / "minimal"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin.json").write_text(json.dumps({"name": "minimal"}), encoding="utf-8")
        result = discover_plugins_from_manifests(str(tmp_path / "plugins"))
        assert len(result) == 1
        assert result[0]["version"] == "0.0.0"
        assert result[0]["entry_point"] == ""

    def test_broken_json(self, tmp_path):
        from core.api.services.plugin_discovery import discover_plugins_from_manifests

        plugin_dir = tmp_path / "plugins" / "broken"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin.json").write_text("not valid json", encoding="utf-8")
        result = discover_plugins_from_manifests(str(tmp_path / "plugins"))
        assert len(result) == 1
        assert result[0]["version"] == "0.0.0"
        assert result[0]["error"]

    def test_plugin_missing_name(self, tmp_path):
        from core.api.services.plugin_discovery import discover_plugins_from_manifests

        plugin_dir = tmp_path / "plugins" / "noname"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin.json").write_text(json.dumps({"version": "1.0"}), encoding="utf-8")
        result = discover_plugins_from_manifests(str(tmp_path / "plugins"))
        assert result == []

    def test_plugin_name_not_string(self, tmp_path):
        from core.api.services.plugin_discovery import discover_plugins_from_manifests

        plugin_dir = tmp_path / "plugins" / "badname"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin.json").write_text(json.dumps({"name": 123}), encoding="utf-8")
        result = discover_plugins_from_manifests(str(tmp_path / "plugins"))
        assert result == []

    def test_duplicate_names(self, tmp_path):
        from core.api.services.plugin_discovery import discover_plugins_from_manifests

        for name in ("p1", "p2", "p1"):
            d = tmp_path / "plugins" / name
            d.mkdir(parents=True, exist_ok=True)
            (d / "plugin.json").write_text(json.dumps({"name": name}), encoding="utf-8")
        result = discover_plugins_from_manifests(str(tmp_path / "plugins"))
        assert len(result) == 2

    def test_only_dirs_are_scanned(self, tmp_path):
        from core.api.services.plugin_discovery import discover_plugins_from_manifests

        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        (plugins_dir / "file.json").write_text("{}", encoding="utf-8")
        result = discover_plugins_from_manifests(str(plugins_dir))
        assert result == []

    def test_skip_non_plugin_dirs(self, tmp_path):
        from core.api.services.plugin_discovery import discover_plugins_from_manifests

        empty_dir = tmp_path / "plugins" / "empty"
        empty_dir.mkdir(parents=True)
        result = discover_plugins_from_manifests(str(tmp_path / "plugins"))
        assert result == []

    def test_result_sorted_by_name(self, tmp_path):
        from core.api.services.plugin_discovery import discover_plugins_from_manifests

        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        for name in ("z_plugin", "a_plugin", "m_plugin"):
            d = plugins_dir / name
            d.mkdir()
            (d / "plugin.json").write_text(json.dumps({"name": name}), encoding="utf-8")
        result = discover_plugins_from_manifests(str(plugins_dir))
        names = [p["name"] for p in result]
        assert names == sorted(names)

    def test_os_error_on_manifest_read(self, tmp_path, monkeypatch):
        from core.api.services.plugin_discovery import discover_plugins_from_manifests

        plugin_dir = tmp_path / "plugins" / "locked"
        plugin_dir.mkdir(parents=True)
        manifest_file = plugin_dir / "plugin.json"
        manifest_file.write_text("garbage", encoding="utf-8")
        result = discover_plugins_from_manifests(str(tmp_path / "plugins"))
        assert len(result) >= 1
