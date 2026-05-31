"""Tests for the BasePlugin class and refactored timer plugin."""

import json
import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# Need to patch out webview before any plugin imports try to use it
@pytest.fixture(autouse=True)
def _no_webview(monkeypatch):
    monkeypatch.setattr("sys.modules", {**sys.modules, "webview": MagicMock()})

# Patch out parse_args so it doesn't try to parse pytest's CLI arguments
@pytest.fixture(autouse=True)
def _no_parse_args(monkeypatch):
    import sys
    # Save original argv
    original_argv = sys.argv
    monkeypatch.setattr(sys, "argv", [""])
    
    # Also patch the function in base_plugin after clearing any cached import
    class FakeArgs:
        gui_hidden = False
    
    # Remove cached module so next import gets fresh (patched) version
    import sys
    sys.modules.pop("core.base_plugin", None)
    sys.modules.pop("plugins.timer.main", None)
    
    # Pre-import and patch before test runs
    import core.base_plugin as _bp
    monkeypatch.setattr(_bp, "parse_args", lambda: FakeArgs())


class TestBasePluginLifecycle:
    """Tests for BasePlugin initialization and lifecycle."""

    def test_subclass_must_set_plugin_name(self):
        from core.base_plugin import BasePlugin

        class BrokenPlugin(BasePlugin):
            pass

        with pytest.raises(RuntimeError, match="PLUGIN_NAME must be set"):
            BrokenPlugin()

    def test_loads_config(self, tmp_path, monkeypatch):
        from core.base_plugin import BasePlugin

        class FakePlugin(BasePlugin):
            PLUGIN_NAME = "fake"
            DEFAULT_PORT = 12345

            def get_overlay_html(self):
                return "<html></html>"

        monkeypatch.setattr(
            "core.base_plugin.load_plugin_config",
            lambda d: {"port": 12345, "start_time": 5},
        )
        monkeypatch.setattr("core.base_plugin.get_base_dir", lambda: tmp_path)
        p = FakePlugin()
        assert p.config.get("port") == 12345

    def test_window_state_load_defaults(self, tmp_path, monkeypatch):
        from core.base_plugin import BasePlugin

        class FakePlugin(BasePlugin):
            PLUGIN_NAME = "fake"

            def get_overlay_html(self):
                return "<html></html>"

        monkeypatch.setattr("core.base_plugin.get_base_dir", lambda: tmp_path)
        p = FakePlugin()
        assert p._window_state["width"] == 600
        assert p._window_state["height"] == 300

    def test_window_state_load_existing(self, tmp_path, monkeypatch):
        from core.base_plugin import BasePlugin

        data_dir = tmp_path.parent / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        state_file = data_dir / "window_state_fake.json"
        state_file.write_text('{"width": 800, "height": 600}')

        class FakePlugin(BasePlugin):
            PLUGIN_NAME = "fake"

            def get_overlay_html(self):
                return "<html></html>"

        monkeypatch.setattr("core.base_plugin.get_base_dir", lambda: tmp_path)
        p = FakePlugin()
        assert p._window_state["width"] == 800
        assert p._window_state["height"] == 600


class TestBasePluginAPIHelpers:
    """Tests for api_post, api_get, push_state, send_command."""

    def test_api_post_returns_true_on_success(self, tmp_path, monkeypatch):
        from core.base_plugin import BasePlugin

        class FakePlugin(BasePlugin):
            PLUGIN_NAME = "fake"

            def get_overlay_html(self):
                return "<html></html>"

        monkeypatch.setattr("core.base_plugin.get_base_dir", lambda: tmp_path)
        p = FakePlugin()

        def mock_urlopen(req, timeout=None):
            m = MagicMock()
            m.__enter__ = MagicMock(return_value=m)
            m.__exit__ = MagicMock(return_value=None)
            return m

        monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)
        assert p.api_post("/test", {"key": "val"}) is True

    def test_api_post_returns_false_on_error(self, tmp_path, monkeypatch):
        from core.base_plugin import BasePlugin

        class FakePlugin(BasePlugin):
            PLUGIN_NAME = "fake"

            def get_overlay_html(self):
                return "<html></html>"

        monkeypatch.setattr("core.base_plugin.get_base_dir", lambda: tmp_path)
        p = FakePlugin()

        def mock_urlopen(req, timeout=None):
            raise ConnectionError("fail")

        monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)
        assert p.api_post("/test", {}) is False

    def test_api_get_returns_data_on_success(self, tmp_path, monkeypatch):
        from core.base_plugin import BasePlugin

        class FakePlugin(BasePlugin):
            PLUGIN_NAME = "fake"

            def get_overlay_html(self):
                return "<html></html>"

        monkeypatch.setattr("core.base_plugin.get_base_dir", lambda: tmp_path)
        p = FakePlugin()

        def mock_urlopen(req, timeout=None):
            m = MagicMock()
            m.read.return_value = json.dumps({"ok": True}).encode()
            m.__enter__ = MagicMock(return_value=m)
            m.__exit__ = MagicMock(return_value=None)
            return m

        monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)
        result = p.api_get("/test")
        assert result == {"ok": True}

    def test_push_state_posts_state(self, tmp_path, monkeypatch):
        from core.base_plugin import BasePlugin

        class FakePlugin(BasePlugin):
            PLUGIN_NAME = "fake"

            def get_overlay_html(self):
                return "<html></html>"

        monkeypatch.setattr("core.base_plugin.get_base_dir", lambda: tmp_path)
        p = FakePlugin()
        p.state = {"x": 1}

        posted = {}
        def capture_post(path, data):
            posted["path"] = path
            posted["data"] = data
            return True

        monkeypatch.setattr(p, "api_post", capture_post)
        p.push_state()
        assert posted["data"]["state"]["x"] == 1


class TestBasePluginCommandPolling:
    """Tests for command polling and dispatch."""

    def test_command_dispatches_to_handler(self, tmp_path, monkeypatch):
        from core.base_plugin import BasePlugin

        class FakePlugin(BasePlugin):
            PLUGIN_NAME = "fake"

            def get_overlay_html(self):
                return "<html></html>"

        monkeypatch.setattr("core.base_plugin.get_base_dir", lambda: tmp_path)
        p = FakePlugin()

        calls = []
        p.register_handler("test_cmd", lambda args: calls.append(args))

        def mock_get(path, timeout=None):
            return {"commands": [{"command": "test_cmd", "args": {"n": 1}}]}

        monkeypatch.setattr(p, "api_get", mock_get)
        p._running = True

        # Run one iteration manually
        p._command_polling_loop()
        assert len(calls) == 1
        assert calls[0]["n"] == 1

    def test_unhandled_command_calls_on_command(self, tmp_path, monkeypatch):
        from core.base_plugin import BasePlugin

        class FakePlugin(BasePlugin):
            PLUGIN_NAME = "fake"
            commands_seen = []

            def get_overlay_html(self):
                return "<html></html>"

            def on_command(self, command, args):
                self.commands_seen.append((command, args))

        monkeypatch.setattr("core.base_plugin.get_base_dir", lambda: tmp_path)
        p = FakePlugin()

        def mock_get(path, timeout=None):
            return {"commands": [{"command": "unknown", "args": {}}]}

        monkeypatch.setattr(p, "api_get", mock_get)
        p._running = True
        p._command_polling_loop()
        assert ("unknown", {}) in p.commands_seen


class TestTimerPlugin:
    """Tests for the refactored TimerPlugin."""

    def test_timer_initial_state(self, tmp_path, monkeypatch):
        from plugins.timer.main import TimerPlugin

        monkeypatch.setattr("core.base_plugin.get_base_dir", lambda: tmp_path)
        monkeypatch.setattr("core.plugin_config.load_plugin_config", lambda d: {"start_time": 5})

        p = TimerPlugin()
        assert p._initial_seconds == 300
        assert p._time_left == 300
        assert not p._is_paused

    def test_start_unpauses(self, tmp_path, monkeypatch):
        from plugins.timer.main import TimerPlugin

        monkeypatch.setattr("core.base_plugin.get_base_dir", lambda: tmp_path)
        monkeypatch.setattr("core.plugin_config.load_plugin_config", lambda d: {"start_time": 5})

        p = TimerPlugin()
        p._is_paused = True
        p._start()
        assert not p._is_paused

    def test_pause(self, tmp_path, monkeypatch):
        from plugins.timer.main import TimerPlugin

        monkeypatch.setattr("core.base_plugin.get_base_dir", lambda: tmp_path)
        monkeypatch.setattr("core.plugin_config.load_plugin_config", lambda d: {"start_time": 5})

        p = TimerPlugin()
        p._pause()
        assert p._is_paused

    def test_reset(self, tmp_path, monkeypatch):
        from plugins.timer.main import TimerPlugin

        monkeypatch.setattr("core.base_plugin.get_base_dir", lambda: tmp_path)
        monkeypatch.setattr("core.plugin_config.load_plugin_config", lambda d: {"start_time": 5})

        p = TimerPlugin()
        p._time_left = 100
        p._reset()
        assert p._time_left == 300

    def test_tick_decrements(self, tmp_path, monkeypatch):
        from plugins.timer.main import TimerPlugin

        monkeypatch.setattr("core.base_plugin.get_base_dir", lambda: tmp_path)
        monkeypatch.setattr("core.plugin_config.load_plugin_config", lambda d: {"start_time": 5})

        p = TimerPlugin()
        p._time_left = 10
        p.on_tick()
        assert p._time_left == 9

    def test_tick_at_zero_with_auto_win(self, tmp_path, monkeypatch):
        from plugins.timer.main import TimerPlugin

        monkeypatch.setattr("core.base_plugin.get_base_dir", lambda: tmp_path)
        monkeypatch.setattr("core.plugin_config.load_plugin_config", lambda d: {"start_time": 5, "auto_win": True})

        p = TimerPlugin()
        p._time_left = 1

        sent = {}
        def capture_send(target, cmd, args):
            sent["target"] = target
            sent["cmd"] = cmd
            return True

        monkeypatch.setattr(p, "send_command", capture_send)
        monkeypatch.setattr(p, "push_state", lambda: None)
        p.on_tick()
        assert p._time_left == 300  # reset
        assert sent["target"] == "win-counter"
        assert sent["cmd"] == "add_win"

    def test_death_handler_with_pause_on_death(self, tmp_path, monkeypatch):
        from plugins.timer.main import TimerPlugin

        monkeypatch.setattr("core.base_plugin.get_base_dir", lambda: tmp_path)
        monkeypatch.setattr("core.plugin_config.load_plugin_config", lambda d: {"start_time": 5, "pause_on_death": True})

        p = TimerPlugin()
        p._is_paused = False
        p._time_left = 100
        p._on_death()
        assert p._is_paused
        assert p._time_left == 300  # reset to initial

    def test_save_dims(self, tmp_path, monkeypatch):
        from plugins.timer.main import TimerPlugin

        monkeypatch.setattr("core.base_plugin.get_base_dir", lambda: tmp_path)
        monkeypatch.setattr("core.plugin_config.load_plugin_config", lambda d: {"start_time": 5})

        p = TimerPlugin()
        saved = {}
        monkeypatch.setattr(p, "save_window_state", lambda w, h: saved.update({"w": w, "h": h}))
        p._save_dims({"width": 800, "height": 600})
        assert saved["w"] == 800
        assert saved["h"] == 600
