import json
import pytest
from unittest.mock import Mock
from pathlib import Path
from urllib.error import URLError


def _make_json_response(data: dict, status: int = 200):
    """Return a mock ``urlopen`` response object."""
    m = Mock()
    m.status = status

    def read():
        return json.dumps(data).encode("utf-8")

    m.read = read
    m.__enter__ = lambda _: m
    m.__exit__ = lambda *a: None
    return m


class TestPluginAPIClient:
    @pytest.fixture
    def client(self):
        from core.api.client import PluginAPIClient

        return PluginAPIClient("http://test:9999/api/v1")

    def test_register_success(self, client, monkeypatch):
        plugin = {"name": "p1", "path": "/p.exe", "enabled": True}

        def mock_urlopen(req, **_kw):
            assert "plugins/register" in str(req.selector)
            return _make_json_response({"plugin": plugin})

        monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)
        result = client.register(plugin)
        assert result == plugin

    def test_register_failure(self, client, monkeypatch):
        def mock_urlopen(*_a, **_kw):
            raise URLError("fail")

        monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)
        result = client.register({"name": "p1"})
        assert result is None

    def test_unregister_success(self, client, monkeypatch):
        def mock_urlopen(req, **_kw):
            assert "/plugins/p1" in str(req.selector)
            assert req.method == "DELETE"
            return _make_json_response({"status": "unregistered"})

        monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)
        assert client.unregister("p1") is True

    def test_unregister_failure(self, client, monkeypatch):
        def mock_urlopen(*_a, **_kw):
            raise URLError("fail")

        monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)
        assert client.unregister("p1") is False

    def test_get_success(self, client, monkeypatch):
        plugin = {"name": "p1", "version": "1.0"}

        def mock_urlopen(req, **_kw):
            assert "/plugins/p1" in str(req.selector)
            assert req.method == "GET"
            return _make_json_response(plugin)

        monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)
        result = client.get("p1")
        assert result == plugin

    def test_get_failure(self, client, monkeypatch):
        def mock_urlopen(*_a, **_kw):
            raise URLError("fail")

        monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)
        assert client.get("p1") is None

    def test_update_success(self, client, monkeypatch):
        plugin = {"name": "p1", "enabled": False}

        def mock_urlopen(req, **_kw):
            assert "/plugins/p1" in str(req.selector)
            assert req.method == "PUT"
            return _make_json_response(plugin)

        monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)
        result = client.update("p1", {"enabled": False})
        assert result == plugin

    def test_update_failure(self, client, monkeypatch):
        def mock_urlopen(*_a, **_kw):
            raise URLError("fail")

        monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)
        assert client.update("p1", {}) is None

    def test_list_success(self, client, monkeypatch):
        plugins = [{"name": "p1"}, {"name": "p2"}]

        def mock_urlopen(req, **_kw):
            assert "plugins" in str(req.selector)
            assert req.method == "GET"
            return _make_json_response({"plugins": plugins})

        monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)
        result = client.list()
        assert result == plugins

    def test_list_failure(self, client, monkeypatch):
        def mock_urlopen(*_a, **_kw):
            raise URLError("fail")

        monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)
        assert client.list() == []

    def test_list_empty(self, client, monkeypatch):
        def mock_urlopen(*_a, **_kw):
            return _make_json_response({"plugins": []})

        monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)
        assert client.list() == []


class TestRegisterPluginFunction:
    def test_register_plugin_with_appconfig(self, monkeypatch):
        from core.api.client import register_plugin
        from core.models import AppConfig
        from pathlib import Path

        config = AppConfig(
            name="test",
            path=Path("/t.exe"),
            enable=True,
            level=2,
            ics=False,
        )
        returned = {"name": "test", "path": "/t.exe", "enabled": True}

        def mock_urlopen(req, **_kw):
            body = json.loads(req.data)
            assert body["name"] == "test"
            assert body["enabled"] is True
            return _make_json_response({"plugin": returned})

        monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)

        result = register_plugin(config)
        assert result.name == "test"
        assert result.enable is True

    def test_raises_connection_error_on_failure(self, monkeypatch):
        from core.api.client import register_plugin
        from core.models import AppConfig
        from pathlib import Path

        config = AppConfig(name="fail", path=Path("/f.exe"), enable=False, level=2, ics=False)

        def mock_urlopen(*_a, **_kw):
            raise URLError("fail")

        monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)

        with pytest.raises(ConnectionError):
            register_plugin(config)

    def test_map_to_api_body_converts_enable_to_enabled(self):
        from core.api.client import _map_to_api_body

        result = _map_to_api_body({"name": "x", "enable": True})
        assert result["enabled"] is True
        assert "enable" not in result
