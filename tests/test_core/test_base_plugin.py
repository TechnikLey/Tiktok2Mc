"""Tests for BasePlugin and refactored timer plugin.

Memory-efficient: no dynamic module reloading, no full-suite imports.
"""

import json
import sys
from unittest.mock import MagicMock

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

    def test_handler_registration_replaces_existing(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)
        calls = []
        p.register_handler("cmd", lambda args: calls.append(1))
        p.register_handler("cmd", lambda args: calls.append(2))
        dispatch = {"commands": [{"command": "cmd", "args": {}}]}
        call_count = [0]

        def mock_get(path, timeout=None):
            call_count[0] += 1
            if call_count[0] == 1:
                return dispatch
            p._running = False
            return {"commands": []}

        monkeypatch.setattr(p, "api_get", mock_get)
        p._running = True
        p._command_polling_loop()
        assert calls == [2]

    def test_save_window_state(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)
        p._state_file.parent.mkdir(parents=True, exist_ok=True)
        p.save_window_state(1024, 768)
        assert p._state_file.exists()
        import json

        data = json.loads(p._state_file.read_text(encoding="utf-8"))
        assert data["width"] == 1024
        assert data["height"] == 768

    def test_polling_stops_when_not_running(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)
        p._running = False
        p._command_polling_loop()
        # Should return immediately without calling api_get


class TestTimerPlugin:
    """TimerPlugin logic (no HTTP, no window)."""

    def _make_timer(self, tmp_path, monkeypatch, **cfg_override):
        from plugins.timer.main import TimerPlugin

        monkeypatch.setattr("core.base_plugin.parse_args", lambda: FakeArgs())
        monkeypatch.setattr(
            "core.base_plugin.load_plugin_config",
            lambda d: {"start_time": 300, "direction": "down", **cfg_override},
        )
        monkeypatch.setattr("core.base_plugin.get_base_dir", lambda: tmp_path)
        return TimerPlugin()

    # -- init -----------------------------------------------------------

    def test_initial_state_down(self, tmp_path, monkeypatch):
        t = self._make_timer(tmp_path, monkeypatch)
        assert t._start_time == 300
        assert t._current == 300
        assert t._is_paused is True  # auto_start defaults to False

    def test_initial_state_up(self, tmp_path, monkeypatch):
        t = self._make_timer(tmp_path, monkeypatch, direction="up")
        assert t._current == 0
        assert t._is_paused is True

    # -- commands --------------------------------------------------------

    def _mock_http(self, t, monkeypatch):
        monkeypatch.setattr(t, "push_state", lambda: None)
        monkeypatch.setattr(t, "api_post", lambda path, data: True)

    def test_start(self, tmp_path, monkeypatch):
        t = self._make_timer(tmp_path, monkeypatch)
        self._mock_http(t, monkeypatch)
        t._is_paused = True
        t._start()
        assert not t._is_paused
        assert not t._is_waiting

    def test_pause(self, tmp_path, monkeypatch):
        t = self._make_timer(tmp_path, monkeypatch)
        self._mock_http(t, monkeypatch)
        t._start()
        t._pause()
        assert t._is_paused

    def test_resume(self, tmp_path, monkeypatch):
        t = self._make_timer(tmp_path, monkeypatch)
        self._mock_http(t, monkeypatch)
        t._start()
        t._pause()
        t._resume()
        assert not t._is_paused
        assert not t._is_waiting

    def test_reset(self, tmp_path, monkeypatch):
        t = self._make_timer(tmp_path, monkeypatch)
        self._mock_http(t, monkeypatch)
        t._current = 100
        t._reset()
        assert t._current == 300
        assert not t._is_waiting

    def test_set_time(self, tmp_path, monkeypatch):
        t = self._make_timer(tmp_path, monkeypatch)
        self._mock_http(t, monkeypatch)
        t._on_set_time({"seconds": 120})
        assert t._current == 120

    def test_add_time(self, tmp_path, monkeypatch):
        t = self._make_timer(tmp_path, monkeypatch)
        self._mock_http(t, monkeypatch)
        t._current = 100
        t._on_add_time({"seconds": 50})
        assert t._current == 150

    def test_save_dims(self, tmp_path, monkeypatch):
        t = self._make_timer(tmp_path, monkeypatch)
        saved = {}
        monkeypatch.setattr(
            t, "save_window_state", lambda w, h: saved.update({"w": w, "h": h})
        )
        t._on_save_dims({"width": 800, "height": 600})
        assert saved["w"] == 800
        assert saved["h"] == 600

    # -- tick: count down ------------------------------------------------

    def test_tick_decrements(self, tmp_path, monkeypatch):
        t = self._make_timer(tmp_path, monkeypatch)
        t._is_paused = False
        t._current = 10
        t.on_tick()
        assert t._current == 9

    def test_tick_at_zero_no_loop(self, tmp_path, monkeypatch):
        t = self._make_timer(tmp_path, monkeypatch)
        t._is_paused = False
        t._current = 1
        monkeypatch.setattr(t, "push_state", lambda: None)
        t.on_tick()
        assert t._current == 0
        assert t._is_waiting
        assert t._is_paused  # auto-pause when zero reached without loop

    def test_tick_at_zero_with_loop(self, tmp_path, monkeypatch):
        t = self._make_timer(tmp_path, monkeypatch, loop=True)
        t._is_paused = False
        t._current = 1
        monkeypatch.setattr(t, "push_state", lambda: None)
        t.on_tick()
        assert t._current == 300  # reset to start_time
        assert not t._is_waiting

    # -- tick: count up --------------------------------------------------

    def test_tick_increments(self, tmp_path, monkeypatch):
        t = self._make_timer(tmp_path, monkeypatch, direction="up")
        t._is_paused = False
        t._current = 5
        t.on_tick()
        assert t._current == 6

    # -- signals (EventBus, no coupling) ----------------------------------

    def test_zero_publishes_event(self, tmp_path, monkeypatch):
        t = self._make_timer(tmp_path, monkeypatch, signal_on=["zero"])
        t._is_paused = False
        t._current = 1
        events = []

        def capture(path, data):
            events.append((path, data))
            return True

        monkeypatch.setattr(t, "api_post", capture)
        monkeypatch.setattr(t, "push_state", lambda: None)
        t.on_tick()
        assert len(events) >= 1
        assert any(
            e[0] == "/events" and e[1].get("type") == "timer.zero" for e in events
        )

    def test_milestone_publishes_event(self, tmp_path, monkeypatch):
        t = self._make_timer(
            tmp_path, monkeypatch, signal_on=["milestone"], milestones=[5, 10]
        )
        t._is_paused = False
        t._milestones_sent.clear()  # reset tracking so we can observe the hit
        t._current = 10
        events = []

        def capture(path, data):
            events.append((path, data))
            return True

        monkeypatch.setattr(t, "api_post", capture)
        monkeypatch.setattr(t, "push_state", lambda: None)
        t.on_tick()  # 10 -> 9, should trigger milestone 10 for down direction
        assert any(
            e[0] == "/events" and e[1].get("type") == "timer.milestone" for e in events
        )

    # -- formatting -------------------------------------------------------

    def test_format_mm_ss(self, tmp_path, monkeypatch):
        t = self._make_timer(tmp_path, monkeypatch)
        t._current = 125
        assert t._format_display() == "02:05"

    def test_format_hh_mm_ss(self, tmp_path, monkeypatch):
        t = self._make_timer(tmp_path, monkeypatch, format="hh:mm:ss")
        t._current = 3665
        assert t._format_display() == "01:01:05"

    def test_format_seconds(self, tmp_path, monkeypatch):
        t = self._make_timer(tmp_path, monkeypatch, format="seconds")
        t._current = 99
        assert t._format_display() == "99"

    # -- config helpers ---------------------------------------------------

    def test_should_reset(self, tmp_path, monkeypatch):
        t = self._make_timer(tmp_path, monkeypatch, reset_on=["zero", "manual"])
        assert t._should_reset("zero")
        assert t._should_reset("manual")
        assert not t._should_reset("command")

    def test_should_signal(self, tmp_path, monkeypatch):
        t = self._make_timer(tmp_path, monkeypatch, signal_on=["tick", "zero"])
        assert t._should_signal("tick")
        assert t._should_signal("zero")
        assert not t._should_signal("started")
