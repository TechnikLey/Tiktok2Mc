"""Tests for the external networking helpers on BasePlugin.

``http_request``: retries with backoff, per-URL circuit breaker,
JSON parsing, 4xx no-retry semantics.
``ws_connect`` / ``ws_close``: managed background WebSocket client
threads with auto-reconnect and shutdown cleanup.
"""

import threading
import time
from unittest.mock import MagicMock

import pytest

from core.base_plugin import BasePlugin, _CircuitBreaker


class FakeArgs:
    plugin = "fake"
    gui_hidden = True


def _make_plugin(tmp_path, monkeypatch):
    monkeypatch.setattr("core.base_plugin.parse_args", lambda: FakeArgs())
    monkeypatch.setattr("core.base_plugin.load_plugin_config", lambda d: {})
    monkeypatch.setattr("core.base_plugin.get_base_dir", lambda: tmp_path)

    class P(BasePlugin):
        PLUGIN_NAME = "fake"

        def get_overlay_html(self):
            return ""

    return P()


class TestCircuitBreaker:
    def test_opens_after_max_fails(self):
        b = _CircuitBreaker(max_fails=3, cooldown=60.0)
        assert b.allow()
        for _ in range(2):
            b.mark_failure()
        assert b.allow()  # below threshold
        b.mark_failure()
        assert not b.allow()  # open now

    def test_success_resets_failures(self):
        b = _CircuitBreaker(max_fails=3, cooldown=60.0)
        b.mark_failure()
        b.mark_failure()
        b.mark_success()
        b.mark_failure()
        b.mark_failure()
        assert b.allow()

    def test_closes_after_cooldown(self):
        b = _CircuitBreaker(max_fails=1, cooldown=0.2)
        b.mark_failure()
        assert not b.allow()
        time.sleep(0.3)
        assert b.allow()


class TestHttpRequest:
    def _resp(self, status=200, body=b"{}", content_type="application/json"):
        m = MagicMock()
        m.__enter__ = MagicMock(return_value=m)
        m.__exit__ = MagicMock(return_value=None)
        m.status = status
        m.read.return_value = body
        m.headers = {"Content-Type": content_type}
        return m

    def test_success_parses_json(self, tmp_path, monkeypatch):
        p = _make_plugin(tmp_path, monkeypatch)
        monkeypatch.setattr(
            "urllib.request.urlopen",
            lambda req, timeout=None: self._resp(200, b'{"ok": true}'),
        )
        result = p.http_request("https://example.test/api")
        assert result == {"status": 200, "json": {"ok": True}, "text": '{"ok": true}'}

    def test_retries_on_5xx_then_succeeds(self, tmp_path, monkeypatch):
        p = _make_plugin(tmp_path, monkeypatch)
        calls = []

        def handler(req, timeout=None):
            calls.append(1)
            if len(calls) < 3:
                raise __import__("urllib.error", fromlist=["HTTPError"]).HTTPError(
                    req.full_url, 503, "unavailable", {}, None
                )
            return self._resp(200, b"{}")

        monkeypatch.setattr("urllib.request.urlopen", handler)
        monkeypatch.setattr(time, "sleep", lambda s: None)
        result = p.http_request("https://example.test/x", retries=3)
        assert result is not None and result["status"] == 200
        assert len(calls) == 3

    def test_4xx_no_retry(self, tmp_path, monkeypatch):
        p = _make_plugin(tmp_path, monkeypatch)
        calls = []

        def handler(req, timeout=None):
            calls.append(1)
            raise __import__("urllib.error", fromlist=["HTTPError"]).HTTPError(
                req.full_url, 404, "nope", {}, None
            )

        monkeypatch.setattr("urllib.request.urlopen", handler)
        result = p.http_request("https://example.test/x", retries=5)
        assert len(calls) == 1  # caller error -> immediate return
        assert result == {"status": 404, "json": None, "text": ""}

    def test_breaker_fails_fast_after_repeated_network_errors(
        self, tmp_path, monkeypatch
    ):
        p = _make_plugin(tmp_path, monkeypatch)
        monkeypatch.setattr(time, "sleep", lambda s: None)

        def handler(req, timeout=None):
            raise ConnectionError("down")

        monkeypatch.setattr("urllib.request.urlopen", handler)
        # Default max_fails=5: exhaust the breaker in one call each round.
        for _ in range(5):
            assert p.http_request("https://dead.test/", retries=1) is None
        calls = []

        def counting(req, timeout=None):
            calls.append(1)
            raise ConnectionError("down")

        monkeypatch.setattr("urllib.request.urlopen", counting)
        assert p.http_request("https://dead.test/") is None
        assert calls == []  # dropped locally, endpoint untouched

    def test_json_body_and_data_are_exclusive(self, tmp_path, monkeypatch):
        p = _make_plugin(tmp_path, monkeypatch)
        with pytest.raises(ValueError):
            p.http_request("https://x.test/", json_body={"a": 1}, data=b"x")


class TestWsConnect:
    def test_returns_false_without_websocket_package(self, tmp_path, monkeypatch):
        import builtins

        p = _make_plugin(tmp_path, monkeypatch)
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "websocket":
                raise ImportError("nope")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        assert p.ws_connect("wss://x.test/", lambda msg: None) is False

    def test_rejects_non_callable_handler(self, tmp_path, monkeypatch):
        import sys as _sys
        import types as _types

        if "websocket" not in _sys.modules:
            fake = _types.ModuleType("websocket")
            fake.create_connection = lambda *a, **k: None
            _sys.modules["websocket"] = fake
        try:
            p = _make_plugin(tmp_path, monkeypatch)
            assert p.ws_connect("wss://x.test/", "not-callable") is False
        finally:
            if isinstance(
                _sys.modules.get("websocket"), _types.ModuleType
            ) and not hasattr(_sys.modules["websocket"], "__version__"):
                del _sys.modules["websocket"]

    def test_duplicate_client_name_rejected_and_close_works(
        self, tmp_path, monkeypatch
    ):
        import sys as _sys
        import types as _types

        created = []
        closed = []

        class FakeWS:
            def recv(self):
                stop.wait(5)
                raise ConnectionError("stop")

            def close(self):
                closed.append(1)

        stop = threading.Event()

        def create_connection(url, header=None, timeout=None):
            created.append(url)
            return FakeWS()

        fake = _types.ModuleType("websocket")
        fake.create_connection = create_connection
        monkeypatch.setitem(_sys.modules, "websocket", fake)

        p = _make_plugin(tmp_path, monkeypatch)
        got = []
        started = threading.Event()

        def on_message(data):
            got.append(data)
            started.set()

        assert (
            p.ws_connect(
                "wss://game.test/", on_message, name="game", reconnect_delay=0.05
            )
            is True
        )
        assert (
            p.ws_connect(
                "wss://other.test/", on_message, name="game", reconnect_delay=0.05
            )
            is False
        )  # duplicate name
        deadline = time.time() + 3
        while not created and time.time() < deadline:
            time.sleep(0.01)
        p.ws_close("game")
        time.sleep(0.1)
        assert closed  # socket was closed via ws_close
