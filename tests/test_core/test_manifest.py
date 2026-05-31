"""Tests for the plugin manifest discovery system."""

import json
import pytest
from pathlib import Path


class TestPluginManifestModel:
    def test_valid_manifest(self):
        from core.api.models import PluginManifest

        m = PluginManifest(
            name="test-plugin",
            version="1.0.0",
            entry_point="src/plugins/test/main.py",
            display_name="Test Plugin",
            description="A test plugin",
        )
        assert m.name == "test-plugin"

    def test_invalid_name_rejected(self):
        from core.api.models import PluginManifest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            PluginManifest(
                name="Has Spaces",
                version="1.0.0",
                entry_point="p.py",
                display_name="Bad",
            )

    def test_empty_name_rejected(self):
        from core.api.models import PluginManifest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            PluginManifest(
                name="",
                version="1.0.0",
                entry_point="p.py",
                display_name="Empty",
            )

    def test_missing_entry_point_rejected(self):
        from core.api.models import PluginManifest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            PluginManifest(
                name="missing-entry",
                version="1.0.0",
                display_name="No Entry",  # entry_point is required
            )

    def test_capabilities_defaults_to_empty(self):
        from core.api.models import PluginManifest

        m = PluginManifest(
            name="no-caps",
            version="1.0.0",
            entry_point="p.py",
            display_name="No Caps",
        )
        assert m.capabilities == []


class TestPluginRegistrationFromManifest:
    def test_from_manifest_basic(self):
        from core.api.models import PluginManifest, PluginRegistration

        manifest = PluginManifest(
            name="timer",
            version="1.0.0",
            entry_point="src/plugins/timer/main.py",
            display_name="Timer",
            description="Countdown timer",
            capabilities=["timer:schedule", "timer:pause"],
        )
        reg = PluginRegistration.from_manifest(manifest)
        assert reg.name == "timer"
        assert reg.display_name == "Timer"
        assert reg.capabilities == ["timer:schedule", "timer:pause"]
        assert reg.description == "Countdown timer"
        assert reg.path == "src/plugins/timer/main.py"

    def test_from_manifest_overrides(self):
        from core.api.models import PluginManifest, PluginRegistration

        manifest = PluginManifest(
            name="timer",
            version="1.0.0",
            entry_point="src/plugins/timer/main.py",
            display_name="Timer",
        )
        reg = PluginRegistration.from_manifest(
            manifest, enabled=True, level=3
        )
        assert reg.enabled is True
        assert reg.level == 3

    def test_from_manifest_preserves_auto_enable(self):
        from core.api.models import PluginManifest, PluginRegistration

        manifest = PluginManifest(
            name="auto-on",
            version="1.0.0",
            entry_point="p.py",
            display_name="Auto On",
            auto_enable=True,
        )
        reg = PluginRegistration.from_manifest(manifest)
        assert reg.auto_enable is True


class TestManifestDiscovery:
    def test_discover_single_manifest(self, tmp_path):
        from core.api.launcher import PluginLauncher

        plugins_dir = tmp_path / "src" / "plugins"
        plugins_dir.mkdir(parents=True)
        timer_dir = plugins_dir / "timer"
        timer_dir.mkdir()
        manifest = {
            "name": "timer",
            "version": "1.0.0",
            "entry_point": "src/plugins/timer/main.py",
            "display_name": "Timer",
        }
        (timer_dir / "plugin.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )

        launcher = PluginLauncher(plugins_dir=plugins_dir)
        manifests = launcher._discover_from_manifests()
        assert len(manifests) == 1
        assert manifests[0].name == "timer"

    def test_discover_multiple_plugins(self, tmp_path):
        from core.api.launcher import PluginLauncher

        plugins_dir = tmp_path / "src" / "plugins"
        plugins_dir.mkdir(parents=True)
        for name in ("timer", "death-counter", "win-counter"):
            d = plugins_dir / name
            d.mkdir()
            (d / "plugin.json").write_text(
                json.dumps({
                    "name": name,
                    "version": "1.0.0",
                    "entry_point": f"src/plugins/{name}/main.py",
                    "display_name": name.title(),
                }),
                encoding="utf-8",
            )

        launcher = PluginLauncher(plugins_dir=plugins_dir)
        manifests = launcher._discover_from_manifests()
        names = [m.name for m in manifests]
        assert names == ["death-counter", "timer", "win-counter"]

    def test_skips_directory_without_manifest(self, tmp_path):
        from core.api.launcher import PluginLauncher

        plugins_dir = tmp_path / "src" / "plugins"
        plugins_dir.mkdir(parents=True)
        (plugins_dir / "has-manifest").mkdir()
        (plugins_dir / "has-manifest" / "plugin.json").write_text(
            json.dumps({
                "name": "has-manifest",
                "version": "1.0.0",
                "entry_point": "p.py",
                "display_name": "Has Manifest",
            }),
            encoding="utf-8",
        )
        (plugins_dir / "no-manifest").mkdir()

        launcher = PluginLauncher(plugins_dir=plugins_dir)
        manifests = launcher._discover_from_manifests()
        assert len(manifests) == 1
        assert manifests[0].name == "has-manifest"

    def test_skips_directory_with_bad_json(self, tmp_path):
        from core.api.launcher import PluginLauncher

        plugins_dir = tmp_path / "src" / "plugins"
        plugins_dir.mkdir(parents=True)
        d = plugins_dir / "bad-json"
        d.mkdir()
        (d / "plugin.json").write_text(
            "this is not json", encoding="utf-8"
        )

        launcher = PluginLauncher(plugins_dir=plugins_dir)
        manifests = launcher._discover_from_manifests()
        assert len(manifests) == 0

    def test_skips_duplicate_names(self, tmp_path):
        from core.api.launcher import PluginLauncher

        plugins_dir = tmp_path / "src" / "plugins"
        plugins_dir.mkdir(parents=True)
        for sub in ("a", "b"):
            d = plugins_dir / sub
            d.mkdir()
            (d / "plugin.json").write_text(
                json.dumps({
                    "name": "dup",
                    "version": "1.0.0",
                    "entry_point": "p.py",
                    "display_name": "Dup",
                }),
                encoding="utf-8",
            )

        launcher = PluginLauncher(plugins_dir=plugins_dir)
        manifests = launcher._discover_from_manifests()
        assert len(manifests) == 1

    def test_skips_invalid_manifest_schema(self, tmp_path):
        from core.api.launcher import PluginLauncher

        plugins_dir = tmp_path / "src" / "plugins"
        plugins_dir.mkdir(parents=True)
        d = plugins_dir / "bad-schema"
        d.mkdir()
        (d / "plugin.json").write_text(
            json.dumps({
                "name": "bad",    # missing entry_point, display_name
                "version": "1.0.0",
            }),
            encoding="utf-8",
        )

        launcher = PluginLauncher(plugins_dir=plugins_dir)
        manifests = launcher._discover_from_manifests()
        assert len(manifests) == 0

    def test_returns_empty_when_no_plugins_dir(self):
        from core.api.launcher import PluginLauncher

        launcher = PluginLauncher(plugins_dir=Path("/nonexistent/dir"))
        manifests = launcher._discover_from_manifests()
        assert manifests == []

    def test_plugins_directory_default(self, monkeypatch):
        from core.api.launcher import PluginLauncher
        from pathlib import Path

        launcher = PluginLauncher()
        pd = launcher._plugins_directory()
        assert pd is not None
        assert pd.name == "plugins"


class _FakeResponse:
    """Context-manager-compatible fake HTTP response."""

    def __init__(self, data: bytes, status: int = 200):
        self._data = data
        self.status = status

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class TestManifestRegistrationViaAPI:
    """Verify that the launcher registers discovered manifests
    with the API and that they appear in the plugin list."""

    def test_manifest_plugins_appear_in_list(self, tmp_path, client, monkeypatch):
        from core.api.launcher import PluginLauncher
        import urllib.request

        plugins_dir = tmp_path / "src" / "plugins"
        plugins_dir.mkdir(parents=True)
        (plugins_dir / "timer").mkdir()
        (plugins_dir / "timer" / "plugin.json").write_text(
            json.dumps({
                "name": "timer",
                "version": "1.0.0",
                "entry_point": "src/plugins/timer/main.py",
                "display_name": "Timer",
                "ports": {"declared": [29189]},
                "capabilities": ["timer:schedule"],
            }),
            encoding="utf-8",
        )

        def tracking_urlopen(req_or_url, **_kw):
            if isinstance(req_or_url, str):
                url = req_or_url
                method = "GET"
                data = None
            else:
                url = req_or_url.full_url
                method = req_or_url.method or "GET"
                data = req_or_url.data

            if "/api/v1/plugins/register" in url and method == "POST":
                body = json.loads(data.decode("utf-8"))
                resp = client.post("/api/v1/plugins/register", json=body)
                return _FakeResponse(
                    json.dumps(resp.json()).encode("utf-8"), resp.status_code
                )

            if "/api/v1/plugins" in url and method == "GET":
                resp = client.get("/api/v1/plugins")
                return _FakeResponse(
                    json.dumps(resp.json()).encode("utf-8"), resp.status_code
                )

            raise urllib.error.URLError(f"Unmocked: {url}")

        monkeypatch.setattr(urllib.request, "urlopen", tracking_urlopen)

        launcher = PluginLauncher(
            plugins_dir=plugins_dir,
            api_base_url="http://127.0.0.1:29185/api/v1",
        )
        plugins = launcher.get_plugins()
        names = [p.name for p in plugins]
        assert "timer" in names
        assert launcher.source == "manifest"
