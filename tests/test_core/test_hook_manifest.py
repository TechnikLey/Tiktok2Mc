import json


class TestHookManifest:
    def test_default_values(self):
        from core.hook_manifest import HookManifest

        m = HookManifest({})
        assert m.name == ""
        assert m.version == "1.0.0"
        assert m.display_name == ""
        assert m.description == ""
        assert m.author == ""
        assert m.capabilities == []
        assert m.config_schema is None
        assert m.depends_on == []

    def test_construction_from_data(self):
        from core.hook_manifest import HookManifest

        data = {
            "name": "test_hook",
            "version": "2.0.0",
            "display_name": "Test Hook",
            "description": "A test hook",
            "author": "dev",
            "capabilities": ["chat", "events"],
            "config_schema": {"type": "object"},
            "depends_on": ["other_hook"],
            "update_url": "https://example.com",
        }
        m = HookManifest(data)
        assert m.name == "test_hook"
        assert m.version == "2.0.0"
        assert m.display_name == "Test Hook"
        assert len(m.capabilities) == 2
        assert m.config_schema == {"type": "object"}
        assert m.update_url == "https://example.com"

    def test_valid_property_true_with_name(self):
        from core.hook_manifest import HookManifest

        assert HookManifest({"name": "ok"}).valid is True

    def test_valid_property_false_without_name(self):
        from core.hook_manifest import HookManifest

        assert HookManifest({}).valid is False


class TestLoadHookManifest:
    def test_load_valid_manifest(self, tmp_path):
        from core.hook_manifest import load_hook_manifest

        hook_dir = tmp_path / "my_hook"
        hook_dir.mkdir()
        (hook_dir / "hook.json").write_text(
            json.dumps({"name": "my_hook", "version": "1.0.0"}), encoding="utf-8"
        )
        manifest = load_hook_manifest(hook_dir)
        assert manifest is not None
        assert manifest.name == "my_hook"

    def test_missing_file_returns_none(self, tmp_path):
        from core.hook_manifest import load_hook_manifest

        hook_dir = tmp_path / "empty_hook"
        hook_dir.mkdir()
        manifest = load_hook_manifest(hook_dir)
        assert manifest is None

    def test_invalid_json_returns_none(self, tmp_path):
        from core.hook_manifest import load_hook_manifest

        hook_dir = tmp_path / "bad_hook"
        hook_dir.mkdir()
        (hook_dir / "hook.json").write_text("not json", encoding="utf-8")
        manifest = load_hook_manifest(hook_dir)
        assert manifest is None

    def test_missing_name_returns_none(self, tmp_path):
        from core.hook_manifest import load_hook_manifest

        hook_dir = tmp_path / "noname"
        hook_dir.mkdir()
        (hook_dir / "hook.json").write_text(json.dumps({"version": "1.0"}), encoding="utf-8")
        manifest = load_hook_manifest(hook_dir)
        assert manifest is None


class TestDiscoverHooksDirs:
    def test_discover_returns_list(self):
        from core.hook_manifest import discover_hooks_dirs

        dirs = discover_hooks_dirs()
        assert isinstance(dirs, list)


class TestReadHookVersion:
    def test_read_version_from_manifest(self, tmp_path):
        from core.hook_manifest import read_hook_version

        hook_dir = tmp_path / "v_hook"
        hook_dir.mkdir()
        (hook_dir / "hook.json").write_text(
            json.dumps({"name": "v_hook", "version": "3.2.1"}), encoding="utf-8"
        )
        version = read_hook_version(hook_dir)
        assert version == "3.2.1"

    def test_read_version_missing_manifest(self, tmp_path):
        from core.hook_manifest import read_hook_version

        hook_dir = tmp_path / "no_manifest"
        hook_dir.mkdir()
        version = read_hook_version(hook_dir)
        assert version == "0.0.0"
