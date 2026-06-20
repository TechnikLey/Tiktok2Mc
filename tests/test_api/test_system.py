"""Tests for restart/shutdown/cancel system endpoints."""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
import pytest

from core.lifecycle import SupervisorState


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
    monkeypatch.setattr(core.lifecycle, "shutdown_cancel_event", asyncio.Event())
    # Ensure the route module sees the patched lifecycle functions.
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
    def test_shutdown_requests_supervisor_countdown(self, client, mock_supervisor):
        resp = client.post("/api/v1/shutdown")
        assert resp.status_code == 200
        assert resp.json() == {"status": "shutdown_requested"}
        mock_supervisor.shutdown_countdown.assert_called_once_with()

    def test_shutdown_already_shutting_down(self, client, mock_supervisor):
        mock_supervisor.state = SupervisorState.SHUTTING_DOWN
        resp = client.post("/api/v1/shutdown")
        assert resp.status_code == 200
        assert resp.json() == {"status": "shutdown_already_requested"}
        mock_supervisor.shutdown_countdown.assert_not_awaited()

    def test_shutdown_now_requests_supervisor_shutdown(self, client, mock_supervisor):
        resp = client.post("/api/v1/shutdown/now")
        assert resp.status_code == 200
        assert resp.json() == {"status": "shutdown_now"}
        mock_supervisor.shutdown.assert_called_once()

    def test_shutdown_cancel_sets_cancel_event(self, client, mock_supervisor, monkeypatch):
        import core.lifecycle
        import core.api.routes.system as system_routes

        event = asyncio.Event()
        monkeypatch.setattr(core.lifecycle, "shutdown_cancel_event", event)
        monkeypatch.setattr(system_routes, "shutdown_cancel_event", event)

        resp = client.post("/api/v1/shutdown/cancel")
        assert resp.status_code == 200
        assert resp.json() == {"status": "cancel_requested"}
        assert event.is_set()


class TestShutdownStatus:
    def test_shutdown_status_idle_when_no_file(self, client):
        resp = client.get("/api/v1/shutdown/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body == {
            "shutdown_pending": False,
            "remaining_seconds": None,
            "state": "idle",
        }

    def test_shutdown_status_returns_file_content(self, client, project_dir):
        runtime_dir = project_dir / "core" / "runtime"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        status_file = runtime_dir / "shutdown_status"
        status_file.write_text(
            json.dumps({"remaining": 10, "state": "counting_down"}),
            encoding="utf-8",
        )
        try:
            resp = client.get("/api/v1/shutdown/status")
            assert resp.status_code == 200
            assert resp.json() == {
                "shutdown_pending": True,
                "remaining_seconds": 10,
                "state": "counting_down",
            }
        finally:
            status_file.unlink(missing_ok=True)

    def test_shutdown_status_handles_corrupt_json_gracefully(
        self, client, project_dir
    ):
        runtime_dir = project_dir / "core" / "runtime"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        status_file = runtime_dir / "shutdown_status"
        status_file.write_text("not valid json", encoding="utf-8")
        try:
            resp = client.get("/api/v1/shutdown/status")
            assert resp.status_code == 200
            assert resp.json() == {
                "shutdown_pending": False,
                "remaining_seconds": None,
                "state": "idle",
            }
        finally:
            status_file.unlink(missing_ok=True)

    def test_shutdown_status_handles_read_error_gracefully(
        self, client, project_dir, monkeypatch
    ):
        runtime_dir = project_dir / "core" / "runtime"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        status_file = runtime_dir / "shutdown_status"
        status_file.write_text("{}", encoding="utf-8")

        def _broken_read(*args, **kwargs):
            raise PermissionError("access denied")

        monkeypatch.setattr(Path, "read_text", _broken_read)
        try:
            resp = client.get("/api/v1/shutdown/status")
            assert resp.status_code == 200
            assert resp.json() == {
                "shutdown_pending": False,
                "remaining_seconds": None,
                "state": "idle",
            }
        finally:
            status_file.unlink(missing_ok=True)
