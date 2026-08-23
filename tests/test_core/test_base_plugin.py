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

    # -- api_request (HookAPI.request parity) --------------------------------

    def test_api_request_get_returns_parsed_body(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)
        seen = {}

        def mock_urlopen(req, timeout=None):
            seen["method"] = req.method
            seen["url"] = req.full_url
            m = MagicMock()
            m.read.return_value = json.dumps({"sent": ["log"]}).encode()
            m.__enter__ = MagicMock(return_value=m)
            m.__exit__ = MagicMock(return_value=None)
            return m

        monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)
        result = p.api_request("/notifications/channels")
        assert result == {"sent": ["log"]}
        assert seen["method"] == "GET"
        assert "/api/v1/notifications/channels" in seen["url"]

    def test_api_request_post_sends_json_payload(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)
        seen = {}

        def mock_urlopen(req, timeout=None):
            seen["method"] = req.method
            seen["data"] = req.data
            seen["content_type"] = req.headers.get("Content-type")
            m = MagicMock()
            m.read.return_value = json.dumps(
                {"sent": ["discord"], "failed": [], "skipped": []}
            ).encode()
            m.__enter__ = MagicMock(return_value=m)
            m.__exit__ = MagicMock(return_value=None)
            return m

        monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)
        payload = {
            "title": "Clip archived",
            "channels": {"discord": {"webhook_url": "https://x/y"}},
        }
        result = p.api_request("notifications", payload=payload)
        assert result == {"sent": ["discord"], "failed": [], "skipped": []}
        assert seen["method"] == "POST"
        assert json.loads(seen["data"]) == payload
        assert seen["content_type"] == "application/json"

    def test_api_request_method_override(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)

        def mock_urlopen(req, timeout=None):
            m = MagicMock()
            m.read.return_value = b'{"ok": true}'
            m.__enter__ = MagicMock(return_value=m)
            m.__exit__ = MagicMock(return_value=None)
            return m

        monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)
        assert p.api_request(
            "plugins/fake/data/counter",
            payload={"value": 42},
            method="PUT",
        ) == {"ok": True}

    def test_api_request_empty_body_returns_none(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)

        def mock_urlopen(req, timeout=None):
            m = MagicMock()
            m.read.return_value = b""
            m.__enter__ = MagicMock(return_value=m)
            m.__exit__ = MagicMock(return_value=None)
            return m

        monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)
        assert p.api_request("/no-content") is None

    def test_api_request_failure_returns_none(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)

        def mock_urlopen(req, timeout=None):
            raise ConnectionError("fail")

        monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)
        assert p.api_request("/test") is None

    def test_api_request_http_error_returns_none(self, tmp_path, monkeypatch):
        import email.message
        import io
        import urllib.error

        p = self._make_plugin(tmp_path, monkeypatch)

        def mock_urlopen(req, timeout=None):
            raise urllib.error.HTTPError(
                req.full_url,
                404,
                "Not Found",
                email.message.Message(),
                io.BytesIO(b""),
            )

        monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)
        assert p.api_request("/missing") is None

    def test_api_request_unserializable_payload_returns_none(
        self, tmp_path, monkeypatch
    ):
        p = self._make_plugin(tmp_path, monkeypatch)

        def fail_urlopen(req, timeout=None):
            raise AssertionError("must not be called")

        monkeypatch.setattr("urllib.request.urlopen", fail_urlopen)
        assert p.api_request("/test", payload={"bad": object()}) is None

    def test_push_state(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)
        p.state = {"x": 1}

        posted = {}

        def capture(method, path, data):
            posted["path"] = path
            posted["data"] = data
            return True

        # push_state uses the ungated raw helper internally
        monkeypatch.setattr(p, "_api_request", capture)
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

        monkeypatch.setattr(p, "_http_get", mock_get)
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

        monkeypatch.setattr(p, "_http_get", mock_get)
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

        monkeypatch.setattr(p, "_http_get", mock_get)
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
        assert t._should_signal("zero")
        assert t._should_signal("tick")
        assert not t._should_signal("started")


class TestBasePluginPermissions:
    """Opt-in permission model: manifest 'permissions' gates the public
    api_*/store_*/send_command/query_plugin/publish_event helpers while
    BasePlugin's own machinery (polling, heartbeat, overlay registration)
    stays ungated."""

    def _plugin_class(self):
        from core.base_plugin import BasePlugin

        class P(BasePlugin):
            PLUGIN_NAME = "fake"

            def get_overlay_html(self):
                return ""

        return P

    def _make_plugin(self, tmp_path, monkeypatch):
        monkeypatch.setattr("core.base_plugin.parse_args", lambda: FakeArgs())
        monkeypatch.setattr("core.base_plugin.load_plugin_config", lambda d: {})
        monkeypatch.setattr("core.base_plugin.get_base_dir", lambda: tmp_path)
        return self._plugin_class()()

    @staticmethod
    def _mock_urlopen(monkeypatch, calls=None, response=None):
        def mock_urlopen(req, timeout=None):
            if calls is not None:
                calls.append(req)
            m = MagicMock()
            m.__enter__ = MagicMock(return_value=m)
            m.__exit__ = MagicMock(return_value=None)
            if response is not None:
                m.read.return_value = json.dumps(response).encode()
            return m

        monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)

    def test_unrestricted_by_default(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)
        assert p._permissions is None
        calls = []
        self._mock_urlopen(monkeypatch, calls)
        assert p.api_post("/anything", {}) is True
        assert len(calls) == 1

    def test_network_gate_blocks_generic_helpers(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)
        p._permissions = {"store"}
        calls = []
        self._mock_urlopen(monkeypatch, calls)
        assert p.api_post("/anything", {}) is False
        assert p.api_put("/anything", {}) is False
        assert p.api_delete("/anything") is False
        assert p.api_get("/anything") is None
        assert p.api_request("/anything", payload={}) is None
        assert calls == []  # no HTTP traffic at all

    def test_store_gate(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)
        p._permissions = {"network"}
        self._mock_urlopen(monkeypatch)
        assert (
            p.store_get("k") == "default_x"
            or p.store_get("k", "default_x") == "default_x"
        )
        assert p.store_set("k", 1) is False
        assert p.store_delete("k") is False
        assert p.store_all() == {}
        # network still works
        assert p.api_post("/anything", {}) is True

    def test_plugins_gate_blocks_cross_plugin_calls(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)
        p._permissions = {"store"}
        calls = []
        self._mock_urlopen(monkeypatch, calls)
        assert p.send_command("other", "cmd") is False
        assert p.query_plugin("other", "q") is None
        assert calls == []

    def test_send_command_allowed_with_permission(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)
        p._permissions = {"plugins"}
        calls = []
        self._mock_urlopen(monkeypatch, calls)
        assert p.send_command("other", "cmd", {"n": 1}) is True
        assert len(calls) == 1
        assert "/plugins/other/command" in calls[0].full_url

    def test_events_publish_event_namespaced(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)
        p._permissions = {"events"}
        calls = []
        self._mock_urlopen(monkeypatch, calls)
        assert p.publish_event("fake.thing", {"n": 1}) is True
        body = json.loads(calls[0].data.decode())
        assert body == {"type": "fake.thing", "data": {"n": 1}}

    def test_events_publish_warns_on_foreign_namespace_but_sends(
        self, tmp_path, monkeypatch, caplog
    ):
        import logging as _logging

        p = self._make_plugin(tmp_path, monkeypatch)
        p._permissions = {"events"}
        calls = []
        self._mock_urlopen(monkeypatch, calls)
        with caplog.at_level(_logging.WARNING):
            assert p.publish_event("tiktok.gift", {}) is True
        assert any("namespace" in r.message for r in caplog.records)

    def test_publish_event_invalid_type(self, tmp_path, monkeypatch):
        from typing import Any as _Any

        p = self._make_plugin(tmp_path, monkeypatch)
        p._permissions = {"events"}
        calls = []
        self._mock_urlopen(monkeypatch, calls)
        assert p.publish_event("", {}) is False
        bad: _Any = None  # deliberately invalid input
        assert p.publish_event(bad, {}) is False
        assert calls == []

    def test_load_permissions_missing_manifest(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)
        p._plugin_dir = tmp_path / "nope"
        assert p._load_permissions() is None

    def test_load_permissions_reads_manifest(self, tmp_path, monkeypatch):
        plugin_dir = tmp_path / "plug"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(
            json.dumps({"name": "plug", "permissions": ["store", "bogus"]}),
            encoding="utf-8",
        )
        p = self._make_plugin(tmp_path, monkeypatch)
        p._plugin_dir = plugin_dir
        perms = p._load_permissions()
        assert perms == {"store"}  # unknown names are ignored (with warning)

    def test_load_permissions_empty_list_is_unrestricted(self, tmp_path, monkeypatch):
        plugin_dir = tmp_path / "plug"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(
            json.dumps({"name": "plug", "permissions": []}), encoding="utf-8"
        )
        p = self._make_plugin(tmp_path, monkeypatch)
        p._plugin_dir = plugin_dir
        assert p._load_permissions() is None


class TestBasePluginRpc:
    """Generic custom endpoint: reserved __rpc__ command -> on_rpc()."""

    def _make(self, tmp_path, monkeypatch):
        monkeypatch.setattr("core.base_plugin.parse_args", lambda: FakeArgs())
        monkeypatch.setattr("core.base_plugin.load_plugin_config", lambda d: {})
        monkeypatch.setattr("core.base_plugin.get_base_dir", lambda: tmp_path)
        from core.base_plugin import BasePlugin

        class P(BasePlugin):
            PLUGIN_NAME = "fake"

            def get_overlay_html(self):
                return ""

        return P()

    def _posted(self, p, monkeypatch):
        posted = []

        def capture(method, path, data):
            posted.append((path, data))
            return True

        monkeypatch.setattr(p, "_api_request", capture)
        return posted

    def test_on_rpc_success_posts_result(self, tmp_path, monkeypatch):
        from typing import Any as _Any

        p = self._make(tmp_path, monkeypatch)
        seen: list[tuple] = []

        def handler(method: str, path: str, body: _Any):
            seen.append((method, path, body))
            return {"echo": path}

        p.on_rpc = handler  # type: ignore[method-assign]
        posted = self._posted(p, monkeypatch)
        p._handle_rpc(
            {
                "_rpc_id": "id-1",
                "_rpc_method": "POST",
                "_rpc_path": "/things/42",
                "name": "x",
            }
        )
        assert seen == [("POST", "/things/42", {"name": "x"})]
        path, data = posted[0]
        assert path == "/plugins/fake/query-response"
        assert data == {"id": "id-1", "ok": True, "result": {"echo": "/things/42"}}

    def test_on_rpc_error_posts_failure(self, tmp_path, monkeypatch):
        p = self._make(tmp_path, monkeypatch)

        def broken(method, path, body):
            raise RuntimeError("boom")

        p.on_rpc = broken  # type: ignore[method-assign]
        posted = self._posted(p, monkeypatch)
        p._handle_rpc({"_rpc_id": "id-2", "_rpc_method": "GET", "_rpc_path": "/x"})
        _, data = posted[0]
        assert data["ok"] is False
        assert "boom" in data["error"]

    def test_polling_loop_intercepts_rpc(self, tmp_path, monkeypatch):
        p = self._make(tmp_path, monkeypatch)
        commands_seen = []
        monkeypatch.setattr(
            p,
            "on_command",
            lambda cmd, args: commands_seen.append(cmd),
        )
        calls = []

        def mock_get(path, timeout=None):
            if not calls:
                calls.append(1)
                return {
                    "commands": [
                        {
                            "command": "__rpc__",
                            "args": {
                                "_rpc_id": "id-3",
                                "_rpc_method": "GET",
                                "_rpc_path": "/y",
                            },
                        }
                    ]
                }
            p._running = False
            return {"commands": []}

        monkeypatch.setattr(p, "_http_get", mock_get)
        monkeypatch.setattr(p, "_handle_rpc", lambda args: None)  # skip HTTP
        p._running = True
        p._command_polling_loop()
        assert commands_seen == []  # reserved command never reaches handlers


class TestBasePluginGracefulShutdown:
    """on_stop() contract: reserved __shutdown__ command and atexit fallback."""

    class _ProcessExited(Exception):
        pass

    def _plugin_class(self):
        from core.base_plugin import BasePlugin

        class P(BasePlugin):
            PLUGIN_NAME = "fake"

            def get_overlay_html(self):
                return ""

        return P

    def _make_plugin(self, tmp_path, monkeypatch, plugin_cls=None):
        monkeypatch.setattr("core.base_plugin.parse_args", lambda: FakeArgs())
        monkeypatch.setattr("core.base_plugin.load_plugin_config", lambda d: {})
        monkeypatch.setattr("core.base_plugin.get_base_dir", lambda: tmp_path)
        if plugin_cls is None:
            plugin_cls = self._plugin_class()
        return plugin_cls()

    def test_shutdown_command_calls_on_stop_and_exits(self, tmp_path, monkeypatch):
        from core.base_plugin import SHUTDOWN_COMMAND

        calls = []

        class P(self._plugin_class()):
            def on_stop(self):
                calls.append("stopped")

        p = self._make_plugin(tmp_path, monkeypatch, plugin_cls=P)
        monkeypatch.setattr(
            "core.base_plugin.os._exit",
            lambda code: (_ for _ in ()).throw(self._ProcessExited(code)),
        )
        with pytest.raises(self._ProcessExited):
            p._handle_shutdown_command()
        assert calls == ["stopped"]
        assert p._shutdown_started is True
        assert p._running is False
        assert SHUTDOWN_COMMAND == "__shutdown__"

    def test_shutdown_runs_exactly_once(self, tmp_path, monkeypatch):
        calls = []

        class P(self._plugin_class()):
            def on_stop(self):
                calls.append(1)

        p = self._make_plugin(tmp_path, monkeypatch, plugin_cls=P)
        monkeypatch.setattr(
            "core.base_plugin.os._exit",
            lambda code: None,
        )
        p._handle_shutdown_command()
        p._handle_shutdown_command()  # second call is a no-op
        assert len(calls) == 1

    def test_broken_on_stop_does_not_prevent_exit(self, tmp_path, monkeypatch):
        class P(self._plugin_class()):
            def on_stop(self):
                raise RuntimeError("boom")

        p = self._make_plugin(tmp_path, monkeypatch, plugin_cls=P)
        exited = []
        monkeypatch.setattr(
            "core.base_plugin.os._exit", lambda code: exited.append(code)
        )
        p._handle_shutdown_command()
        assert exited == [0]

    def test_polling_loop_intercepts_shutdown_command(self, tmp_path, monkeypatch):
        calls = []

        class P(self._plugin_class()):
            def on_stop(self):
                calls.append("stop")

        p = self._make_plugin(tmp_path, monkeypatch, plugin_cls=P)
        monkeypatch.setattr(
            "core.base_plugin.os._exit",
            lambda code: (_ for _ in ()).throw(self._ProcessExited(code)),
        )

        def mock_get(path, timeout=None):
            return {"commands": [{"command": "__shutdown__", "args": {}}]}

        monkeypatch.setattr(p, "_http_get", mock_get)
        p._running = True
        with pytest.raises(self._ProcessExited):
            p._command_polling_loop()
        assert calls == ["stop"]

    def test_atexit_fallback_calls_on_stop_once(self, tmp_path, monkeypatch):
        calls = []

        class P(self._plugin_class()):
            def on_stop(self):
                calls.append(1)

        p = self._make_plugin(tmp_path, monkeypatch, plugin_cls=P)
        p._atexit_stop()
        p._atexit_stop()
        assert len(calls) == 1
