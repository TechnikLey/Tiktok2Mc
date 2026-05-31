"""Tests for BasePlugin and refactored timer plugin.

Memory-efficient: no dynamic module reloading, no full-suite imports.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _patch_argv(monkeypatch):
    """Prevent parse_args from seeing pytest CLI arguments."""
    monkeypatch.setattr(sys, "argv", [""])


class FakeArgs:
    gui_hidden = False


class TestBasePluginLifecycle:
    """BasePlugin init, config, window state."""

    def test_subclass_must_set_plugin_name(self):
        from core.base_plugin import BasePlugin

        class Broken(BasePlugin):
            pass

        with pytest.raises(RuntimeError, match="PLUGIN_NAME must be set"):
            Broken()

    def test_loads_config(self, tmp_path, monkeypatch):
        from core.base_plugin import BasePlugin

        monkeypatch.setattr("core.base_plugin.parse_args", lambda: FakeArgs())
        monkeypatch.setattr(
            "core.base_plugin.load_plugin_config",
            lambda d: {"port": 12345},
        )
        monkeypatch.setattr("core.base_plugin.get_base_dir", lambda: tmp_path)

        class P(BasePlugin):
            PLUGIN_NAME = "fake"

            def get_overlay_html(self):
                return ""

        p = P()
        assert p.config.get("port") == 12345

    def test_window_state_defaults(self, tmp_path, monkeypatch):
        from core.base_plugin import BasePlugin

        monkeypatch.setattr("core.base_plugin.parse_args", lambda: FakeArgs())
        monkeypatch.setattr("core.base_plugin.load_plugin_config", lambda d: {})
        monkeypatch.setattr("core.base_plugin.get_base_dir", lambda: tmp_path)

        class P(BasePlugin):
            PLUGIN_NAME = "fake"

            def get_overlay_html(self):
                return ""

        p = P()
        assert p._window_state["width"] == 600
        assert p._window_state["height"] == 300

    def test_window_state_load_existing(self, tmp_path, monkeypatch):
        from core.base_plugin import BasePlugin

        data_dir = tmp_path.parent / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "window_state_fake.json").write_text(
            '{"width": 800, "height": 600}'
        )

        monkeypatch.setattr("core.base_plugin.parse_args", lambda: FakeArgs())
        monkeypatch.setattr("core.base_plugin.load_plugin_config", lambda d: {})
        monkeypatch.setattr("core.base_plugin.get_base_dir", lambda: tmp_path)

        class P(BasePlugin):
            PLUGIN_NAME = "fake"

            def get_overlay_html(self):
                return ""

        p = P()
        assert p._window_state["width"] == 800
        assert p._window_state["height"] == 600


class TestBasePluginAPIHelpers:
    """api_post, api_get, push_state, send_command."""

    def _make_plugin(self, tmp_path, monkeypatch):
        from core.base_plugin import BasePlugin

        monkeypatch.setattr("core.base_plugin.parse_args", lambda: FakeArgs())
        monkeypatch.setattr("core.base_plugin.load_plugin_config", lambda d: {})
        monkeypatch.setattr("core.base_plugin.get_base_dir", lambda: tmp_path)

        class P(BasePlugin):
            PLUGIN_NAME = "fake"

            def get_overlay_html(self):
                return ""

        return P()

    def test_api_post_success(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)

        def mock_urlopen(req, timeout=None):
            m = MagicMock()
            m.__enter__ = MagicMock(return_value=m)
            m.__exit__ = MagicMock(return_value=None)
            return m

        monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)
        assert p.api_post("/test", {"key": "val"}) is True

    def test_api_post_failure(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)

        def mock_urlopen(req, timeout=None):
            raise ConnectionError("fail")

        monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)
        assert p.api_post("/test", {}) is False

    def test_api_get_success(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)

        def mock_urlopen(req, timeout=None):
            m = MagicMock()
            m.read.return_value = json.dumps({"ok": True}).encode()
            m.__enter__ = MagicMock(return_value=m)
            m.__exit__ = MagicMock(return_value=None)
            return m

        monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)
        result = p.api_get("/test")
        assert result == {"ok": True}

    def test_push_state(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)
        p.state = {"x": 1}

        posted = {}

        def capture(path, data):
            posted["path"] = path
            posted["data"] = data
            return True

        monkeypatch.setattr(p, "api_post", capture)
        p.push_state()
        assert posted["data"]["state"]["x"] == 1


class TestBasePluginCommandPolling:
    """Command dispatch without actual HTTP calls."""

    def _make_plugin(self, tmp_path, monkeypatch):
        from core.base_plugin import BasePlugin

        monkeypatch.setattr("core.base_plugin.parse_args", lambda: FakeArgs())
        monkeypatch.setattr("core.base_plugin.load_plugin_config", lambda d: {})
        monkeypatch.setattr("core.base_plugin.get_base_dir", lambda: tmp_path)

        class P(BasePlugin):
            PLUGIN_NAME = "fake"

            def get_overlay_html(self):
                return ""

        return P()

    def test_handler_dispatch(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)
        calls = []
        p.register_handler("test_cmd", lambda args: calls.append(args))

        call_count = [0]
        def mock_get(path, timeout=None):
            call_count[0] += 1
            if call_count[0] == 1:
                return {"commands": [{"command": "test_cmd", "args": {"n": 1}}]}
            p._running = False
            return {"commands": []}

        monkeypatch.setattr(p, "api_get", mock_get)
        p._running = True
        p._command_polling_loop()
        assert len(calls) == 1
        assert calls[0]["n"] == 1

    def test_unhandled_calls_on_command(self, tmp_path, monkeypatch):
        from core.base_plugin import BasePlugin

        monkeypatch.setattr("core.base_plugin.parse_args", lambda: FakeArgs())
        monkeypatch.setattr("core.base_plugin.load_plugin_config", lambda d: {})
        monkeypatch.setattr("core.base_plugin.get_base_dir", lambda: tmp_path)

        class P(BasePlugin):
            PLUGIN_NAME = "fake"

            def __init__(self):
                super().__init__()
                self.seen = []

            def get_overlay_html(self):
                return ""

            def on_command(self, command, args):
                self.seen.append((command, args))

        p = P()
        call_count = [0]
        def mock_get(path, timeout=None):
            call_count[0] += 1
            if call_count[0] == 1:
                return {"commands": [{"command": "unknown", "args": {}}]}
            p._running = False
            return {"commands": []}

        monkeypatch.setattr(p, "api_get", mock_get)
        p._running = True
        p._command_polling_loop()
        assert ("unknown", {}) in p.seen


class TestTimerPlugin:
    """TimerPlugin logic (no HTTP, no window)."""

    def _make_timer(self, tmp_path, monkeypatch, **cfg_override):
        from plugins.timer.main import TimerPlugin

        monkeypatch.setattr("core.base_plugin.parse_args", lambda: FakeArgs())
        monkeypatch.setattr(
            "core.base_plugin.load_plugin_config",
            lambda d: {"start_time": 5, **cfg_override},
        )
        monkeypatch.setattr("core.base_plugin.get_base_dir", lambda: tmp_path)
        return TimerPlugin()

    def test_initial_state(self, tmp_path, monkeypatch):
        t = self._make_timer(tmp_path, monkeypatch)
        assert t._initial_seconds == 300
        assert t._time_left == 300
        assert not t._is_paused

    def test_start(self, tmp_path, monkeypatch):
        t = self._make_timer(tmp_path, monkeypatch)
        t._is_paused = True
        t._start()
        assert not t._is_paused

    def test_pause(self, tmp_path, monkeypatch):
        t = self._make_timer(tmp_path, monkeypatch)
        t._pause()
        assert t._is_paused

    def test_reset(self, tmp_path, monkeypatch):
        t = self._make_timer(tmp_path, monkeypatch)
        t._time_left = 100
        t._reset()
        assert t._time_left == 300

    def test_tick_decrements(self, tmp_path, monkeypatch):
        t = self._make_timer(tmp_path, monkeypatch)
        t._time_left = 10
        t.on_tick()
        assert t._time_left == 9

    def test_tick_at_zero_with_auto_win(self, tmp_path, monkeypatch):
        t = self._make_timer(tmp_path, monkeypatch, auto_win=True)
        t._time_left = 1

        sent = {}

        def capture(target, cmd, args):
            sent["target"] = target
            sent["cmd"] = cmd
            return True

        monkeypatch.setattr(t, "send_command", capture)
        monkeypatch.setattr(t, "push_state", lambda: None)
        t.on_tick()
        assert t._time_left == 300
        assert sent["target"] == "win-counter"
        assert sent["cmd"] == "add_win"

    def test_death_with_pause_on_death(self, tmp_path, monkeypatch):
        t = self._make_timer(tmp_path, monkeypatch, pause_on_death=True)
        t._is_paused = False
        t._time_left = 100
        t._on_death()
        assert t._is_paused
        assert t._time_left == 300

    def test_save_dims(self, tmp_path, monkeypatch):
        t = self._make_timer(tmp_path, monkeypatch)
        saved = {}
        monkeypatch.setattr(t, "save_window_state", lambda w, h: saved.update({"w": w, "h": h}))
        t._save_dims({"width": 800, "height": 600})
        assert saved["w"] == 800
        assert saved["h"] == 600
