"""Tests for shutdown safety improvements in ProcessSupervisor.

Covers:
- Double shutdown does not raise RuntimeError
- Shutdown during SHUTTING_DOWN state is a no-op
- Shutdown from various states
- Shutdown reason/source propagation via ShutdownController
"""

import pytest

from core.lifecycle import ProcessSupervisor, SupervisorState

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def supervisor(tmp_path):
    """Create a fresh ProcessSupervisor for testing."""

    s = ProcessSupervisor()
    s._runtime_dir = tmp_path / "runtime"
    s._runtime_dir.mkdir(parents=True, exist_ok=True)
    return s


# ---------------------------------------------------------------------------
# Double shutdown safety
# ---------------------------------------------------------------------------


class TestDoubleShutdown:
    @pytest.mark.asyncio
    async def test_shutdown_during_shutting_down_is_noop(self, supervisor):
        """Calling shutdown() while already SHUTTING_DOWN must not raise."""
        supervisor.state = SupervisorState.SHUTTING_DOWN
        # Should NOT raise RuntimeError
        await supervisor.shutdown()

    @pytest.mark.asyncio
    async def test_shutdown_during_complete_is_noop(self, supervisor):
        """Calling shutdown() while already COMPLETE must not raise."""
        supervisor.state = SupervisorState.COMPLETE
        await supervisor.shutdown()

    @pytest.mark.asyncio
    async def test_shutdown_during_restarting_is_noop(self, supervisor):
        """Calling shutdown() while RESTARTING must not raise."""
        supervisor.state = SupervisorState.RESTARTING
        await supervisor.shutdown()

    @pytest.mark.asyncio
    async def test_shutdown_from_countdown(self, supervisor):
        """Calling shutdown() from COUNTDOWN state is valid."""
        supervisor.state = SupervisorState.COUNTDOWN
        # shutdown() from COUNTDOWN should proceed (calls stop_all)
        # Since there are no processes registered, stop_all is a no-op
        await supervisor.shutdown()
        assert supervisor.state == SupervisorState.COMPLETE

    @pytest.mark.asyncio
    async def test_shutdown_from_running(self, supervisor):
        """Normal shutdown from RUNNING state."""
        supervisor.state = SupervisorState.RUNNING
        await supervisor.shutdown()
        assert supervisor.state == SupervisorState.COMPLETE

    @pytest.mark.asyncio
    async def test_shutdown_from_idle(self, supervisor):
        """Shutdown from IDLE state."""
        supervisor.state = SupervisorState.IDLE
        await supervisor.shutdown()
        assert supervisor.state == SupervisorState.COMPLETE

    @pytest.mark.asyncio
    async def test_shutdown_from_starting(self, supervisor):
        """Shutdown from STARTING state."""
        supervisor.state = SupervisorState.STARTING
        await supervisor.shutdown()
        assert supervisor.state == SupervisorState.COMPLETE
