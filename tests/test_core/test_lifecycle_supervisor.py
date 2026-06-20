"""Tests for the lifecycle supervisor."""

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.lifecycle import (
    ManagedProcess,
    ProcessState,
    ProcessSupervisor,
    SupervisorState,
    shutdown_cancel_event,
)


@pytest.fixture
async def supervisor(tmp_path, monkeypatch):
    """Return a supervisor configured to use a temp runtime dir."""
    import core.paths

    monkeypatch.setattr(core.paths, "get_root_dir", lambda: tmp_path)
    sup = ProcessSupervisor()
    sup._loop = asyncio.get_running_loop()
    return sup


class TestStateMachine:
    def test_initial_state(self, supervisor):
        assert supervisor.state == SupervisorState.IDLE

    def test_state_transition(self, supervisor):
        supervisor.state = SupervisorState.RUNNING
        assert supervisor.state == SupervisorState.RUNNING

    def test_state_listener(self, supervisor):
        called_with = []
        supervisor.add_state_listener(lambda s: called_with.append(s))
        supervisor.state = SupervisorState.STARTING
        supervisor.state = SupervisorState.RUNNING
        assert called_with == [SupervisorState.STARTING, SupervisorState.RUNNING]


class TestProcessRegistration:
    def test_register_and_get(self, supervisor):
        supervisor.register("test", [sys.executable, "-c", "print('ok')"])
        proc = supervisor.get("test")
        assert proc is not None
        assert proc.name == "test"
        assert proc.state == ProcessState.STOPPED

    def test_register_shell_process(self, supervisor):
        supervisor.register("gui", [sys.executable, "-c", "print('gui')"], shell=True)
        proc = supervisor.get("gui")
        assert proc.shell is True

    def test_register_disabled_process(self, supervisor):
        supervisor.register("disabled", [sys.executable, "-c", "print('ok')"], enabled=False)
        proc = supervisor.get("disabled")
        assert proc.enabled is False

    def test_unregister(self, supervisor):
        supervisor.register("test", [sys.executable, "-c", "print('ok')"])
        supervisor.unregister("test")
        assert supervisor.get("test") is None


class TestProcessStartStop:
    @pytest.mark.asyncio
    async def test_start_and_stop_process(self, supervisor, tmp_path):
        script = tmp_path / "sleep.py"
        script.write_text("import time; time.sleep(30)", encoding="utf-8")
        supervisor.register("sleeper", [sys.executable, str(script)])

        await supervisor.start("sleeper")
        proc = supervisor.get("sleeper")
        assert proc.state == ProcessState.RUNNING
        assert proc.proc is not None
        assert proc.proc.poll() is None

        await supervisor.stop("sleeper")
        assert proc.state in {ProcessState.STOPPED, ProcessState.FAILED}
        # The supervisor sets proc.proc to None after a clean stop.

    @pytest.mark.asyncio
    async def test_stop_missing_process(self, supervisor):
        # Should not raise.
        await supervisor.stop("nonexistent")

    @pytest.mark.asyncio
    async def test_start_skips_disabled_process(self, supervisor, tmp_path):
        script = tmp_path / "sleep.py"
        script.write_text("import time; time.sleep(30)", encoding="utf-8")
        supervisor.register("disabled", [sys.executable, str(script)], enabled=False)

        result = await supervisor.start("disabled")
        assert result is False
        proc = supervisor.get("disabled")
        assert proc.state == ProcessState.STOPPED
        assert proc.proc is None


class TestRestart:
    @pytest.mark.asyncio
    async def test_restart_stops_and_starts_children(self, supervisor):
        proc = MagicMock()
        proc.shell = False
        proc.state = ProcessState.RUNNING
        proc.proc = MagicMock()
        proc.proc.poll = MagicMock(return_value=None)
        proc.restart_count = 0
        proc.cmd = [sys.executable, "-c", "print('ok')"]

        supervisor._processes["child"] = proc
        supervisor._api_base_url = ""
        supervisor.state = SupervisorState.RUNNING

        with patch.object(supervisor, "stop_all", new=AsyncMock()) as mock_stop:
            with patch.object(supervisor, "start_all", new=AsyncMock()) as mock_start:
                await supervisor.restart()

        mock_stop.assert_awaited_once_with(
            keep_shell=True, graceful_timeout=5.0, force_timeout=5.0
        )
        mock_start.assert_awaited_once()
        assert supervisor.state == SupervisorState.RUNNING

    @pytest.mark.asyncio
    async def test_restart_refuses_when_shutting_down(self, supervisor):
        supervisor.state = SupervisorState.SHUTTING_DOWN
        with pytest.raises(RuntimeError):
            await supervisor.restart()


class TestShutdownFromCountdown:
    @pytest.mark.asyncio
    async def test_shutdown_allowed_from_countdown(self, supervisor):
        supervisor.state = SupervisorState.COUNTDOWN
        with patch.object(supervisor, "stop_all", new=AsyncMock()):
            with patch.object(supervisor, "stop_api_server", new=AsyncMock()):
                await supervisor.shutdown()
        assert supervisor.state == SupervisorState.COMPLETE


class TestShutdown:
    @pytest.mark.asyncio
    async def test_full_shutdown_stops_api_and_children(self, supervisor):
        api_task = MagicMock()
        supervisor._api_server_task = api_task
        supervisor._api_server = MagicMock()

        child = MagicMock()
        child.shell = False
        child.state = ProcessState.RUNNING
        child.proc = MagicMock()
        child.proc.poll = MagicMock(return_value=None)
        supervisor._processes["child"] = child

        supervisor.state = SupervisorState.RUNNING

        with patch.object(supervisor, "stop_all", new=AsyncMock()) as mock_stop:
            await supervisor.shutdown()

        assert supervisor.state == SupervisorState.COMPLETE
        assert mock_stop.call_count == 2

    @pytest.mark.asyncio
    async def test_shutdown_countdown_can_be_cancelled(self, supervisor):
        supervisor.state = SupervisorState.RUNNING
        shutdown_cancel_event.clear()

        task = asyncio.create_task(supervisor.shutdown_countdown(delay=2.0))
        await asyncio.sleep(0.05)
        shutdown_cancel_event.set()

        result = await task
        assert result is False
        assert supervisor.state == SupervisorState.RUNNING

    @pytest.mark.asyncio
    async def test_shutdown_countdown_runs_to_completion(self, supervisor):
        supervisor.state = SupervisorState.RUNNING
        shutdown_cancel_event.clear()

        with patch.object(supervisor, "shutdown", new=AsyncMock()) as mock_shutdown:
            result = await supervisor.shutdown_countdown(delay=0.1)

        assert result is True
        mock_shutdown.assert_awaited_once()


class TestWaitForPort:
    @pytest.mark.asyncio
    async def test_wait_for_port_free_returns_immediately(self, supervisor, tmp_path):
        from core.lifecycle import _wait_for_port_free

        # Use a high ephemeral port that is almost certainly free.
        import socket

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]

        # Port is free now because the socket is closed.
        result = await _wait_for_port_free("127.0.0.1", port, timeout=1.0)
        assert result is True
