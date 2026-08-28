"""Tests for restart/shutdown/cancel system endpoints.

Note: ``/shutdown``, ``/shutdown/cancel``, and ``/shutdown/status``
routes were intentionally removed — shutdown coordination is handled
by the supervisor directly.  Only ``/shutdown/now`` (hard exit) remains,
and it requires an HMAC-signed request (``X-Shutdown-*`` headers).
"""

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.api.shutdown_signature import (
    HDR_SIGNATURE,
    HDR_TIMESTAMP,
    ensure_secret,
    make_headers,
)
from core.lifecycle import SupervisorState


@pytest.fixture(autouse=True)
def _no_shutdown_timer(monkeypatch):
    """Prevent /shutdown/now from spawning a sys.exit timer that would
    fire asynchronously during later tests and raise a warning."""
    monkeypatch.setattr("threading.Timer", lambda *a, **kw: MagicMock())


@pytest.fixture(autouse=True)
def _reset_shutdown_controller():
    """Reset the global ShutdownController between tests so an accepted
    request from one test does not leak into the next."""
    from core.shutdown import reset_shutdown_controller

    reset_shutdown_controller()
    yield
    reset_shutdown_controller()


def _signed_headers(identity: str = "gui.py:stop_system") -> dict[str, str]:
    """Build valid signature headers for the current fixture runner."""
    ensure_secret()
    return make_headers(identity)


@pytest.fixture
def mock_supervisor(monkeypatch):
    """Provide a mocked supervisor and return it."""
    supervisor = MagicMock()
    supervisor.state = SupervisorState.RUNNING
    supervisor.shutdown_delay = 30.0
    supervisor.restart = AsyncMock()
    supervisor.shutdown = AsyncMock()
    supervisor.shutdown_countdown = AsyncMock()

    def _get_supervisor():
        return supervisor

    import core.api.routes.system as system_routes
    import core.lifecycle

    monkeypatch.setattr(core.lifecycle, "get_supervisor", _get_supervisor)
    monkeypatch.setattr(system_routes, "get_supervisor", _get_supervisor)
    return supervisor


class TestRestart:
    def test_restart_requests_supervisor_restart(self, client, mock_supervisor):
        resp = client.post("/api/v1/restart")
        assert resp.status_code == 200
        assert resp.json() == {"status": "restart_requested"}
        mock_supervisor.restart.assert_called_once()

    def test_restart_rejects_when_not_runnable(self, client, mock_supervisor):
        mock_supervisor.state = SupervisorState.SHUTTING_DOWN
        resp = client.post("/api/v1/restart")
        assert resp.status_code == 409
        mock_supervisor.restart.assert_not_awaited()


class TestShutdown:
    def test_shutdown_now_requires_signature(self, client):
        """POST /shutdown/now without a signature is rejected with 403."""
        resp = client.post("/api/v1/shutdown/now")
        assert resp.status_code == 403
        assert "rejected" in resp.json()["detail"].lower()

    def test_shutdown_now_rejects_bad_signature(self, client):
        """A signature that does not match the shared secret is rejected."""
        headers = _signed_headers()
        headers[HDR_SIGNATURE] = "0" * 64
        resp = client.post("/api/v1/shutdown/now", headers=headers)
        assert resp.status_code == 403
        assert "signature mismatch" in resp.json()["detail"]

    def test_shutdown_now_rejects_expired_timestamp(self, client):
        """A signature with an expired timestamp is rejected."""
        headers = _signed_headers()
        headers[HDR_TIMESTAMP] = str(int(time.time()) - 3600)
        resp = client.post("/api/v1/shutdown/now", headers=headers)
        assert resp.status_code == 403
        assert "timestamp out of window" in resp.json()["detail"]

    def test_shutdown_now_rejects_replayed_nonce(self, client):
        """Replaying a valid request (same nonce) is rejected."""
        ensure_secret()
        headers = make_headers("gui.py:stop_system")
        first = client.post("/api/v1/shutdown/now", headers=headers)
        assert first.status_code == 200
        second = client.post("/api/v1/shutdown/now", headers=headers)
        assert second.status_code == 403
        assert "nonce replay" in second.json()["detail"]

    def test_shutdown_now_returns_requested(self, client):
        """A correctly signed POST /shutdown/now requests a graceful shutdown."""
        resp = client.post("/api/v1/shutdown/now", headers=_signed_headers())
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "shutdown_requested"
        assert "shutdown_id" in body

    def test_shutdown_now_audit_log_file_written(self, client, project_dir):
        """A rejected attempt records an entry in the shutdown audit log."""
        resp = client.post("/api/v1/shutdown/now")
        assert resp.status_code == 403
        audit = project_dir / "data" / "diagnostics" / "shutdown_audit.jsonl"
        assert audit.exists()
        content = audit.read_text(encoding="utf-8").strip()
        assert content
        assert '"verdict": "rejected:missing timestamp"' in content


class TestServerRestart:
    def test_restart_server_not_registered(self, client, project_dir):
        """New direct-supervisor restart returns 404 when server is not registered."""
        resp = client.post("/api/v1/server/restart")
        assert resp.status_code == 404
        assert "not registered" in resp.json()["detail"].lower()
