import json
import urllib.request


class _FakeResponse:
    """Context-manager-compatible fake for urllib.response."""

    def __init__(self, data: bytes, status: int = 200):
        self._data = data
        self._status = status

    def getcode(self):
        return self._status

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class TestPluginLauncherBadResponse:
    def test_malformed_json_returns_empty(self, monkeypatch):
        from core.api.launcher import PluginLauncher

        def fake_urlopen(*args, **kwargs):
            return _FakeResponse(b"not valid json")

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        launcher = PluginLauncher("http://127.0.0.1:1/api/v1")
        plugins = launcher.get_plugins()
        assert plugins == []
        assert launcher.using_api is False

    def test_non_list_plugins_field_returns_empty(self, monkeypatch):
        from core.api.launcher import PluginLauncher

        def fake_urlopen(*args, **kwargs):
            return _FakeResponse(
                json.dumps(
                    {"total": 0, "enabled": 0, "plugins": None}
                ).encode()
            )

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        launcher = PluginLauncher("http://127.0.0.1:1/api/v1")
        plugins = launcher.get_plugins()
        assert plugins == []

    def test_entry_with_wrong_types_skipped(self, monkeypatch):
        from core.api.launcher import PluginLauncher

        def fake_urlopen(*args, **kwargs):
            return _FakeResponse(
                json.dumps(
                    {
                        "total": 2,
                        "enabled": 1,
                        "plugins": [
                            {
                                "name": "good",
                                "path": "/good",
                                "version": "1.0",
                                "enabled": True,
                                "level": 2,
                                "ics": False,
                                "description": "",
                            },
                            {
                                "name": "bad",
                                "path": "/bad",
                                "version": 123,
                                "enabled": "nope",
                                "level": "abc",
                                "ics": 99,
                            },
                        ],
                    }
                ).encode()
            )

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        launcher = PluginLauncher("http://127.0.0.1:1/api/v1")
        plugins = launcher.get_plugins()
        names = [p.name for p in plugins]
        assert "good" in names
        assert "bad" not in names
