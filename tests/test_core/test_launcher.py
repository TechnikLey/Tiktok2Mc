import json
import pytest
from pathlib import Path
from unittest.mock import Mock
from urllib.error import URLError


def _mock_urlopen_factory(client):
    """Return a mock urlopen that proxies plugin data from the test client."""

    def _mock_urlopen(req_or_url, **_kw):
        if isinstance(req_or_url, str):
            method = "GET"
            path = req_or_url
        else:
            method = req_or_url.method or "GET"
            path = req_or_url.selector if hasattr(req_or_url, "selector") else "/api/v1/plugins"

        if "/api/v1/plugins" in path and method == "GET":
            resp = client.get("/api/v1/plugins")
            mock = Mock()
            mock.status = resp.status_code

            def read():
                return json.dumps(resp.json()).encode("utf-8")

            mock.read = read
            mock.__enter__ = lambda _: mock
            mock.__exit__ = lambda *a: None
            return mock

        raise URLError(f"Unmocked path: {path}")

    return _mock_urlopen


class TestPluginLauncher:
    @pytest.fixture(autouse=True)
    def _clear_registry(self):
        from core.api.registry import get_registry

        reg = get_registry()
        for p in reg.list():
            reg.unregister(p.name)

    @pytest.fixture
    def empty_plugins_dir(self, tmp_path):
        d = tmp_path / "plugins"
        d.mkdir()
        return d

    def test_using_api_true_when_api_responds(self, client, monkeypatch, empty_plugins_dir):
        client.post(
            "/api/v1/plugins/register",
            json={"name": "launcher-test", "path": "/fake.exe", "enabled": True},
        )
        monkeypatch.setattr(
            "urllib.request.urlopen", _mock_urlopen_factory(client)
        )
        launcher = self._make_launcher(plugins_dir=empty_plugins_dir)
        plugins = launcher.get_plugins()
        assert launcher.using_api is True
        assert launcher.source == "api"
        names = [p.name for p in plugins]
        assert "launcher-test" in names

    def test_returns_empty_when_api_unreachable(self, empty_plugins_dir):
        launcher = self._make_launcher("http://127.0.0.1:1/api/v1", plugins_dir=empty_plugins_dir)
        plugins = launcher.get_plugins()
        assert plugins == []
        assert launcher.using_api is False
        assert launcher.source == "empty"

    def test_plugin_count(self, client, monkeypatch, empty_plugins_dir):
        for i in range(2):
            client.post(
                "/api/v1/plugins/register",
                json={"name": f"cnt-{i}", "path": f"/p{i}.exe"},
            )
        monkeypatch.setattr(
            "urllib.request.urlopen", _mock_urlopen_factory(client)
        )
        launcher = self._make_launcher(plugins_dir=empty_plugins_dir)
        launcher.get_plugins()
        assert launcher.plugin_count == 2

    def test_maps_api_fields_to_app_config(self, client, monkeypatch, empty_plugins_dir):
        client.post(
            "/api/v1/plugins/register",
            json={
                "name": "mapper",
                "path": "/m.exe",
                "enabled": True,
                "level": 3,
                "ics": True,
            },
        )
        monkeypatch.setattr(
            "urllib.request.urlopen", _mock_urlopen_factory(client)
        )
        launcher = self._make_launcher(plugins_dir=empty_plugins_dir)
        plugins = launcher.get_plugins()
        p = [x for x in plugins if x.name == "mapper"][0]
        assert p.path == Path("/m.exe")
        assert p.enable is True
        assert p.level == 3
        assert p.ics is True

    def test_env_var_overrides_base_url(self, monkeypatch, empty_plugins_dir):
        import os
        monkeypatch.setitem(os.environ, "API_BASE_URL", "http://127.0.0.1:1/api/v1")
        import importlib
        import core.api.launcher as launcher_mod
        importlib.reload(launcher_mod)
        from core.api.launcher import PluginLauncher

        launcher = PluginLauncher(plugins_dir=empty_plugins_dir)
        plugins = launcher.get_plugins()
        assert plugins == []

    # ------------------------------------------------------------------

    @staticmethod
    def _make_launcher(base_url: str | None = None, plugins_dir: Path | None = None):
        from core.api.launcher import PluginLauncher

        if base_url is None:
            base_url = "http://127.0.0.1:29185/api/v1"
        return PluginLauncher(base_url, plugins_dir=plugins_dir)
