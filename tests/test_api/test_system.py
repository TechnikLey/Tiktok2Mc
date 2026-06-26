"""Tests for restart/shutdown/cancel system endpoints.

Note: ``/shutdown``, ``/shutdown/cancel``, and ``/shutdown/status``
routes were intentionally removed — shutdown coordination is handled
by the supervisor directly.  Only ``/shutdown/now`` (hard exit) remains.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
import pytest

from core.lifecycle import SupervisorState


@pytest.fixture(autouse=True)
def _no_shutdown_timer(monkeypatch):
    """Prevent /shutdown/now from spawning a sys.exit timer that would
    fire asynchronously during later tests and raise a warning."""
    monkeypatch.setattr("threading.Timer", lambda *a, **kw: MagicMock())


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

    import core.lifecycle
    import core.api.routes.system as system_routes

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
    def test_shutdown_now_returns_requested(self, client):
        """POST /shutdown/now triggers a hard exit via sys.exit timer."""
        resp = client.post("/api/v1/shutdown/now")
        assert resp.status_code == 200
        assert resp.json() == {"status": "shutdown_requested"}


class TestServerRestart:
    def test_restart_server_not_registered(self, client, project_dir):
        """New direct-supervisor restart returns 404 when server is not registered."""
        resp = client.post("/api/v1/server/restart")
        assert resp.status_code == 404
        assert "not registered" in resp.json()["detail"].lower()
