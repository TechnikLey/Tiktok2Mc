"""Tests for the plugin update checker."""

import json
from pathlib import Path

import pytest


class TestExtractVersion:
    def test_semver_tag(self):
        from core.api.updater import _extract_version

        assert _extract_version("v1.2.3") == "1.2.3"

    def test_semver_tag_no_v(self):
        from core.api.updater import _extract_version

        assert _extract_version("1.2.3") == "1.2.3"

    def test_major_minor(self):
        from core.api.updater import _extract_version

        assert _extract_version("v2.0") == "2.0"

    def test_with_prefix(self):
        from core.api.updater import _extract_version

        assert _extract_version("release-1.0.0-beta") == "1.0.0-beta"

    def test_empty_string(self):
        from core.api.updater import _extract_version

        assert _extract_version("") == ""

    def test_no_version(self):
        from core.api.updater import _extract_version

        assert _extract_version("no numbers here") == ""


class TestParseRemoteVersion:
    def test_github_release(self, monkeypatch):
        import urllib.request

        from core.api.updater import _parse_remote_version

        def fake_urlopen(req, **_kw):
            data = json.dumps({"tag_name": "v1.2.3"}).encode("utf-8")
            return _FakeResponse(data)

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        assert (
            _parse_remote_version(
                "https://api.github.com/repos/user/repo/releases/latest"
            )
            == "1.2.3"
        )

    def test_github_release_no_v(self, monkeypatch):
        import urllib.request

        from core.api.updater import _parse_remote_version

        def fake_urlopen(req, **_kw):
            data = json.dumps({"tag_name": "2.0.0"}).encode("utf-8")
            return _FakeResponse(data)

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        assert (
            _parse_remote_version(
                "https://api.github.com/repos/user/repo/releases/latest"
            )
            == "2.0.0"
        )

    def test_direct_json_with_version(self, monkeypatch):
        import urllib.request

        from core.api.updater import _parse_remote_version

        def fake_urlopen(req, **_kw):
            data = json.dumps({"version": "3.0.1"}).encode("utf-8")
            return _FakeResponse(data)

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        assert _parse_remote_version("https://example.com/version.json") == "3.0.1"

    def test_plain_text_version(self, monkeypatch):
        import urllib.request

        from core.api.updater import _parse_remote_version

        def fake_urlopen(req, **_kw):
            return _FakeResponse(b"1.2.3\n")

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        assert _parse_remote_version("https://example.com/version.txt") == "1.2.3"

    def test_unreachable_returns_none(self, monkeypatch):
        import urllib.request

        from core.api.updater import _parse_remote_version

        def fake_urlopen(req, **_kw):
            raise urllib.error.URLError("timeout")

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        assert _parse_remote_version("https://example.com/version.json") is None


class TestPluginUpdateChecker:
    def test_check_updates_skips_plugins_without_update_url(self):
        from core.api.updater import PluginUpdateChecker

        checker = PluginUpdateChecker()
        plugins = [
            {
                "name": "no-update",
                "version": "1.0.0",
                "update_url": "",
                "display_name": "No Update",
            },
        ]
        results = checker.check_updates(plugins)
        assert results == []

    def test_check_updates_reports_available(self, monkeypatch):
        import urllib.request

        from core.api.updater import PluginUpdateChecker

        def fake_urlopen(req, **_kw):
            return _FakeResponse(json.dumps({"tag_name": "v2.0.0"}).encode("utf-8"))

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

        checker = PluginUpdateChecker()
        plugins = [
            {
                "name": "outdated",
                "version": "1.0.0",
                "update_url": "https://api.github.com/repos/user/repo/releases/latest",
                "display_name": "Outdated Plugin",
            },
        ]
        results = checker.check_updates(plugins)
        assert len(results) == 1
        assert results[0]["update_available"] is True
        assert results[0]["latest_version"] == "2.0.0"
        assert results[0]["current_version"] == "1.0.0"

    def test_check_updates_reports_current(self, monkeypatch):
        import urllib.request

        from core.api.updater import PluginUpdateChecker

        def fake_urlopen(req, **_kw):
            return _FakeResponse(json.dumps({"tag_name": "v1.0.0"}).encode("utf-8"))

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

        checker = PluginUpdateChecker()
        plugins = [
            {
                "name": "current",
                "version": "1.0.0",
                "update_url": "https://api.github.com/repos/user/repo/releases/latest",
                "display_name": "Current",
            },
        ]
        results = checker.check_updates(plugins)
        assert len(results) == 1
        assert results[0]["update_available"] is False

    def test_check_updates_handles_fetch_error(self, monkeypatch):
        import urllib.request

        from core.api.updater import PluginUpdateChecker

        def fake_urlopen(req, **_kw):
            raise urllib.error.URLError("timeout")

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

        checker = PluginUpdateChecker()
        plugins = [
            {
                "name": "failing",
                "version": "1.0.0",
                "update_url": "https://api.github.com/repos/user/repo/releases/latest",
                "display_name": "Failing",
            },
        ]
        results = checker.check_updates(plugins)
        assert len(results) == 1
        assert results[0]["error"] is not None
        assert results[0]["update_available"] is False

    def test_cached_status(self):
        from core.api.updater import PluginUpdateChecker

        checker = PluginUpdateChecker()
        assert checker.get_cached_status("nonexistent") is None

    def test_cached_status_after_check(self, monkeypatch):
        import urllib.request

        from core.api.updater import PluginUpdateChecker

        def fake_urlopen(req, **_kw):
            return _FakeResponse(json.dumps({"tag_name": "v1.0.0"}).encode("utf-8"))

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

        checker = PluginUpdateChecker()
        checker.check_updates(
            [
                {
                    "name": "cached",
                    "version": "1.0.0",
                    "update_url": "https://api.github.com/repos/user/repo/releases/latest",
                    "display_name": "Cached",
                },
            ]
        )
        cached = checker.get_cached_status("cached")
        assert cached is not None
        assert cached["name"] == "cached"

    def test_returns_without_update_url_skipped(self):
        from core.api.updater import PluginUpdateChecker

        checker = PluginUpdateChecker()
        plugins = [
            {"name": "a", "version": "1.0.0", "update_url": "", "display_name": "A"},
            {
                "name": "b",
                "version": "1.0.0",
                "update_url": "https://example.com/ver.json",
                "display_name": "B",
            },
        ]
        # Only b has update_url, but it will fail fetch -> returns with error
        results = checker.check_updates(plugins)
        # Only b appears (a has no update_url)
        names = [r["name"] for r in results if r["error"] is None or r["error"]]
        assert "a" not in names


class TestUpdateEndpoint:
    @pytest.fixture(autouse=True)
    def _clear_registry(self):
        from core.api.registry import get_registry

        reg = get_registry()
        for p in reg.list():
            reg.unregister(p.name)

    def test_updates_endpoint_returns_200(self, client):
        resp = client.get("/api/v1/plugins/updates")
        assert resp.status_code == 200
        data = resp.json()
        assert "plugins" in data
        assert "total" in data
        assert "updates_available" in data

    def test_updates_endpoint_empty_when_no_plugins(self, client):
        resp = client.get("/api/v1/plugins/updates")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0

    def test_updates_endpoint_with_plugin(self, client):
        client.post(
            "/api/v1/plugins/register",
            json={
                "name": "test-plugin",
                "version": "1.0.0",
                "display_name": "Test",
                "entry_point": "test/main.py",
                "update_url": "",
            },
        )
        resp = client.get("/api/v1/plugins/updates")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0  # no update_url -> no entry

    def test_updates_endpoint_with_update_url(self, client):
        client.post(
            "/api/v1/plugins/register",
            json={
                "name": "updatable",
                "version": "1.0.0",
                "display_name": "Updatable",
                "entry_point": "test/main.py",
                "update_url": "https://api.github.com/repos/user/repo/releases/latest",
            },
        )
        resp = client.get("/api/v1/plugins/updates")
        assert resp.status_code == 200
        data = resp.json()
        # Should have 1 result (with error since URL is fake)
        assert data["total"] == 1
        assert data["plugins"][0]["error"] is not None


class TestSignalEndpoint:
    def test_get_signal_returns_none_by_default(self, client):
        resp = client.get("/api/v1/updater/signal")
        assert resp.status_code == 200
        assert resp.json() == {"signal": None}

    def test_put_signal_sets_value(self, client):
        resp = client.put("/api/v1/updater/signal", json={"signal": "kill"})
        assert resp.status_code == 200
        assert resp.json() == {"signal": "kill"}

    def test_get_after_put_returns_set_value(self, client):
        client.put("/api/v1/updater/signal", json={"signal": "kill"})
        resp = client.get("/api/v1/updater/signal")
        assert resp.status_code == 200
        assert resp.json() == {"signal": "kill"}

    def test_delete_clears_signal(self, client):
        client.put("/api/v1/updater/signal", json={"signal": "kill"})
        resp = client.delete("/api/v1/updater/signal")
        assert resp.status_code == 200
        assert resp.json() == {"signal": None}

    def test_get_after_delete_returns_none(self, client):
        client.put("/api/v1/updater/signal", json={"signal": "kill"})
        client.delete("/api/v1/updater/signal")
        resp = client.get("/api/v1/updater/signal")
        assert resp.status_code == 200
        assert resp.json() == {"signal": None}


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


class TestSafeExtractZip:
    def test_extracts_normal_archive(self, tmp_path: Path):
        import zipfile

        from core.api.updater import _safe_extract_zip

        archive = tmp_path / "p.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("main.py", "# plugin")
            zf.writestr("sub/config.yaml", "key: value")

        dest = tmp_path / "dest"
        dest.mkdir()
        _safe_extract_zip(archive, dest)

        assert (dest / "main.py").read_text() == "# plugin"
        assert (dest / "sub" / "config.yaml").is_file()

    def test_rejects_zip_slip_member(self, tmp_path: Path):
        import zipfile

        from core.api.updater import _safe_extract_zip

        archive = tmp_path / "evil.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("../escaped.py", "# evil")

        dest = tmp_path / "dest"
        dest.mkdir()

        with pytest.raises(ValueError, match="Zip slip"):
            _safe_extract_zip(archive, dest)

        assert not (tmp_path / "escaped.py").exists()


class TestInstallUpdateIntegrity:
    def _make_checker(self):
        from core.api.updater import PluginUpdateChecker

        return PluginUpdateChecker()

    def test_aborts_when_no_checksum_available(self, tmp_path: Path, monkeypatch):
        from core.api import updater

        checker = self._make_checker()
        plugin = {
            "name": "demo",
            "update_url": "https://example.com/demo.zip",
            "entry_point": "main.py",
        }

        monkeypatch.setattr(updater, "_download_update", lambda *a, **k: True)
        monkeypatch.setattr(updater, "fetch_checksum", lambda url: None)

        verified = {"called": False}

        def _fail_verify(*_a, **_k):
            verified["called"] = True
            return True

        monkeypatch.setattr(updater, "verify_checksum", _fail_verify)

        assert checker.install_update(plugin, tmp_path) is False
        assert verified["called"] is False


def _build_update_zip(target: Path, manifest_name: str, *, ship_config: bool) -> bytes:
    """Create an update archive at *target* and return its bytes."""
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            f"pkg/{manifest_name}",
            json.dumps({"name": "demo", "version": "0.0.0", "entry_point": "main.py"}),
        )
        zf.writestr("pkg/main.py", "print('new version')\n")
        if ship_config:
            zf.writestr("pkg/config.yaml", "enabled: true\nfrom_archive: true\n")
    data = buf.getvalue()
    target.write_bytes(data)
    return data


class TestInstallUpdateReplacesPackage:
    def _make_checker(self):
        from core.api.updater import PackageUpdateChecker

        return PackageUpdateChecker()

    def _setup(self, tmp_path: Path, monkeypatch, manifest_name: str):
        import hashlib

        from core.api import updater

        pkg_dir = tmp_path / "demo"
        pkg_dir.mkdir()
        (pkg_dir / manifest_name).write_text(
            json.dumps({"name": "demo", "version": "1.0.0"}), encoding="utf-8"
        )
        (pkg_dir / "config.yaml").write_text(
            "enabled: true\nuser_setting: keep_me\n", encoding="utf-8"
        )

        zip_bytes = {}

        def fake_download(_url, target):
            zip_bytes["data"] = _build_update_zip(
                target, manifest_name, ship_config=True
            )
            return True

        monkeypatch.setattr(updater, "_download_update", fake_download)
        monkeypatch.setattr(
            updater,
            "fetch_checksum",
            lambda url: hashlib.sha256(zip_bytes["data"]).hexdigest(),
        )
        return pkg_dir

    def test_preserves_user_config_over_archive_config(
        self, tmp_path: Path, monkeypatch
    ):
        pkg_dir = self._setup(tmp_path, monkeypatch, "plugin.json")
        checker = self._make_checker()

        ok = checker.install_update(
            {
                "name": "demo",
                "update_url": "https://example.com/demo.zip",
                "latest_version": "2.0.0",
            },
            tmp_path,
        )

        assert ok is True
        config = (pkg_dir / "config.yaml").read_text(encoding="utf-8")
        # The user's file survives — the archive's config.yaml is discarded.
        assert "user_setting: keep_me" in config
        assert "from_archive" not in config

    def test_bumps_plugin_json_version(self, tmp_path: Path, monkeypatch):
        pkg_dir = self._setup(tmp_path, monkeypatch, "plugin.json")
        self._make_checker().install_update(
            {
                "name": "demo",
                "update_url": "https://example.com/x.zip",
                "latest_version": "2.0.0",
            },
            tmp_path,
        )
        manifest = json.loads((pkg_dir / "plugin.json").read_text(encoding="utf-8"))
        assert manifest["version"] == "2.0.0"
        assert (pkg_dir / "main.py").read_text(encoding="utf-8").startswith("print")

    def test_bumps_hook_json_version(self, tmp_path: Path, monkeypatch):
        pkg_dir = self._setup(tmp_path, monkeypatch, "hook.json")
        self._make_checker().install_update(
            {
                "name": "demo",
                "update_url": "https://example.com/x.zip",
                "latest_version": "2.0.0",
            },
            tmp_path,
        )
        manifest = json.loads((pkg_dir / "hook.json").read_text(encoding="utf-8"))
        assert manifest["version"] == "2.0.0"

    def test_leaves_no_backup_dir_behind(self, tmp_path: Path, monkeypatch):
        self._setup(tmp_path, monkeypatch, "plugin.json")
        self._make_checker().install_update(
            {"name": "demo", "update_url": "https://example.com/x.zip"},
            tmp_path,
        )
        assert not (tmp_path / ".bak_demo").exists()
