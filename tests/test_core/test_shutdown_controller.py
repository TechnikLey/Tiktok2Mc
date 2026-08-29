"""Tests for the ShutdownController — central shutdown coordination.

Covers:
- Normal shutdown
- Double shutdown (request rejected)
- Concurrent shutdown requests (thread safety)
- State machine transitions
- Invalid state transitions
- Forensic state persistence (write/load/consume)
- Shutdown ID uniqueness
- Diagnostics output
"""

import json
import threading
from unittest.mock import AsyncMock

import pytest

from core.shutdown import (
    ShutdownController,
    ShutdownReason,
    ShutdownRequest,
    ShutdownState,
    _make_shutdown_id,
    get_shutdown_controller,
    reset_shutdown_controller,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Reset the singleton before and after each test."""
    reset_shutdown_controller()
    yield
    reset_shutdown_controller()


@pytest.fixture
def diagnostics_dir(tmp_path):
    """Create a diagnostics directory for forensic state files."""
    d = tmp_path / "data" / "diagnostics"
    d.mkdir(parents=True)
    return d


@pytest.fixture
def controller(diagnostics_dir):
    """Create a fresh ShutdownController with a diagnostics directory."""
    return ShutdownController(diagnostics_dir=diagnostics_dir)


@pytest.fixture
def mock_supervisor():
    """Create a mock ProcessSupervisor."""
    supervisor = AsyncMock()
    supervisor.shutdown = AsyncMock()
    return supervisor


# ---------------------------------------------------------------------------
# Shutdown ID
# ---------------------------------------------------------------------------


class TestShutdownID:
    def test_ids_are_unique(self):
        ids = [_make_shutdown_id() for _ in range(100)]
        assert len(set(ids)) == 100

    def test_ids_contain_timestamp(self):
        shutdown_id = _make_shutdown_id()
        # Format: YYYY-MM-DDTHH:MM:SS-XXXX
        assert "-" in shutdown_id
        parts = shutdown_id.rsplit("-", 1)
        assert len(parts) == 2
        assert len(parts[1]) == 4  # hex counter

    def test_ids_are_monotonically_increasing(self):
        ids = [_make_shutdown_id() for _ in range(10)]
        # Each ID should be lexicographically >= the previous
        for i in range(1, len(ids)):
            assert ids[i] >= ids[i - 1]


# ---------------------------------------------------------------------------
# ShutdownRequest
# ---------------------------------------------------------------------------


class TestShutdownRequest:
    def test_request_creation(self):
        req = ShutdownRequest(
            reason=ShutdownReason.USER_REQUEST,
            source="test:unit",
        )
        assert req.reason == ShutdownReason.USER_REQUEST
        assert req.source == "test:unit"
        assert req.process_id > 0
        assert req.timestamp > 0
        assert req.id is not None

    def test_request_to_dict(self):
        req = ShutdownRequest(
            reason=ShutdownReason.SIGNAL,
            source="signal:SIGTERM",
        )
        d = req.to_dict()
        assert d["reason"] == "SIGNAL"
        assert d["source"] == "signal:SIGTERM"
        assert "id" in d
        assert "timestamp" in d
        assert "thread_name" in d

    def test_request_has_stack_trace(self):
        req = ShutdownRequest(reason=ShutdownReason.UNKNOWN, stack="test_stack_info")
        assert req.stack == "test_stack_info"


# ---------------------------------------------------------------------------
# State Machine
# ---------------------------------------------------------------------------


class TestStateMachine:
    def test_initial_state(self, controller):
        assert controller.state == ShutdownState.RUNNING

    def test_valid_transitions(self, controller):
        # RUNNING -> SHUTDOWN_REQUESTED
        assert controller._transition(ShutdownState.SHUTDOWN_REQUESTED)
        assert controller.state == ShutdownState.SHUTDOWN_REQUESTED

        # SHUTDOWN_REQUESTED -> SHUTDOWN_RUNNING
        assert controller._transition(ShutdownState.SHUTDOWN_RUNNING)
        assert controller.state == ShutdownState.SHUTDOWN_RUNNING

        # SHUTDOWN_RUNNING -> CLEANUP
        assert controller._transition(ShutdownState.CLEANUP)
        assert controller.state == ShutdownState.CLEANUP

        # CLEANUP -> EXITING
        assert controller._transition(ShutdownState.EXITING)
        assert controller.state == ShutdownState.EXITING

        # EXITING -> EXITED
        assert controller._transition(ShutdownState.EXITED)
        assert controller.state == ShutdownState.EXITED

    def test_invalid_transition_from_running(self, controller):
        # RUNNING -> CLEANUP (invalid)
        assert not controller._transition(ShutdownState.CLEANUP)
        assert controller.state == ShutdownState.RUNNING  # unchanged

    def test_invalid_transition_from_exited(self, controller):
        # Move to EXITED
        controller._transition(ShutdownState.SHUTDOWN_REQUESTED)
        controller._transition(ShutdownState.SHUTDOWN_RUNNING)
        controller._transition(ShutdownState.CLEANUP)
        controller._transition(ShutdownState.EXITING)
        controller._transition(ShutdownState.EXITED)

        # EXITED -> any state (all invalid)
        assert not controller._transition(ShutdownState.RUNNING)
        assert not controller._transition(ShutdownState.SHUTDOWN_REQUESTED)
        assert controller.state == ShutdownState.EXITED

    def test_can_return_to_running_from_requested(self, controller):
        # RUNNING -> SHUTDOWN_REQUESTED (valid)
        assert controller._transition(ShutdownState.SHUTDOWN_REQUESTED)
        # SHUTDOWN_REQUESTED -> RUNNING (valid — cancelled)
        assert controller._transition(ShutdownState.RUNNING)
        assert controller.state == ShutdownState.RUNNING


# ---------------------------------------------------------------------------
# Request Shutdown
# ---------------------------------------------------------------------------


class TestRequestShutdown:
    def test_first_request_accepted(self, controller):
        req = controller.request_shutdown(
            reason=ShutdownReason.USER_REQUEST,
            source="test:unit",
        )
        assert req is not None
        assert req.reason == ShutdownReason.USER_REQUEST
        assert controller.state == ShutdownState.SHUTDOWN_REQUESTED

    def test_second_request_rejected(self, controller):
        req1 = controller.request_shutdown(
            reason=ShutdownReason.USER_REQUEST,
            source="first",
        )
        assert req1 is not None

        req2 = controller.request_shutdown(
            reason=ShutdownReason.SIGNAL,
            source="second",
        )
        assert req2 is None  # rejected
        assert len(controller.all_requests) == 2  # recorded but not accepted
        assert controller.accepted_request is req1

    def test_request_in_non_running_state_rejected(self, controller):
        # Move to SHUTDOWN_REQUESTED
        controller.request_shutdown(reason=ShutdownReason.USER_REQUEST, source="first")
        # Try again — should be rejected
        req = controller.request_shutdown(
            reason=ShutdownReason.SIGNAL,
            source="second",
        )
        assert req is None

    def test_request_records_source(self, controller):
        req = controller.request_shutdown(
            reason=ShutdownReason.PLUGIN_REQUEST,
            source="plugin:spotify:stop",
        )
        assert req.source == "plugin:spotify:stop"
        assert req.reason == ShutdownReason.PLUGIN_REQUEST

    def test_request_captures_thread_info(self, controller):
        req = controller.request_shutdown(
            reason=ShutdownReason.UNKNOWN,
            source="test",
        )
        assert req.thread_name == threading.current_thread().name
        assert req.thread_id == threading.get_ident()

    def test_request_captures_stack_trace(self, controller):
        req = controller.request_shutdown(
            reason=ShutdownReason.UNKNOWN,
            source="test",
        )
        assert isinstance(req.stack, str)
        assert len(req.stack) > 0
        assert "test_request_captures_stack_trace" in req.stack


# ---------------------------------------------------------------------------
# Execute Shutdown (with mock supervisor)
# ---------------------------------------------------------------------------


class TestExecuteShutdown:
    @pytest.mark.asyncio
    async def test_execute_calls_supervisor(self, controller, mock_supervisor):
        controller.set_supervisor(mock_supervisor)
        controller.request_shutdown(
            reason=ShutdownReason.USER_REQUEST,
            source="test",
        )
        await controller.execute_shutdown()
        mock_supervisor.shutdown.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_transitions_through_states(
        self, controller, mock_supervisor
    ):
        controller.set_supervisor(mock_supervisor)
        controller.request_shutdown(
            reason=ShutdownReason.USER_REQUEST,
            source="test",
        )
        await controller.execute_shutdown()
        assert controller.state == ShutdownState.EXITED

    @pytest.mark.asyncio
    async def test_execute_noop_without_request(self, controller, mock_supervisor):
        controller.set_supervisor(mock_supervisor)
        # No request made — execute should be a no-op
        await controller.execute_shutdown()
        mock_supervisor.shutdown.assert_not_called()
        assert controller.state == ShutdownState.RUNNING

    @pytest.mark.asyncio
    async def test_execute_noop_without_supervisor(self, controller):
        controller.request_shutdown(
            reason=ShutdownReason.USER_REQUEST,
            source="test",
        )
        # No supervisor bound — should log error and transition to EXITED
        await controller.execute_shutdown()
        assert controller.state == ShutdownState.EXITED

    @pytest.mark.asyncio
    async def test_execute_exception_handled(self, controller, mock_supervisor):
        mock_supervisor.shutdown.side_effect = RuntimeError("boom")
        controller.set_supervisor(mock_supervisor)
        controller.request_shutdown(
            reason=ShutdownReason.USER_REQUEST,
            source="test",
        )
        # Should not raise — exception is caught
        await controller.execute_shutdown()
        # State should still reach EXITED despite the exception
        assert controller.state == ShutdownState.EXITED

    @pytest.mark.asyncio
    async def test_execute_only_runs_once(self, controller, mock_supervisor):
        controller.set_supervisor(mock_supervisor)
        controller.request_shutdown(
            reason=ShutdownReason.USER_REQUEST,
            source="test",
        )
        await controller.execute_shutdown()
        # Second call should be a no-op
        await controller.execute_shutdown()
        assert mock_supervisor.shutdown.call_count == 1


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------


class TestThreadSafety:
    def test_concurrent_requests_only_one_accepted(self, controller):
        results = []
        barrier = threading.Barrier(10)

        def _request():
            barrier.wait()
            req = controller.request_shutdown(
                reason=ShutdownReason.UNKNOWN,
                source=f"thread-{threading.current_thread().name}",
            )
            results.append(req)

        threads = [threading.Thread(target=_request) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        accepted = [r for r in results if r is not None]
        rejected = [r for r in results if r is None]
        assert len(accepted) == 1
        assert len(rejected) == 9
        assert controller.state == ShutdownState.SHUTDOWN_REQUESTED


# ---------------------------------------------------------------------------
# Forensic State Persistence
# ---------------------------------------------------------------------------


class TestForensicState:
    def test_write_and_load_state(self, controller, diagnostics_dir):
        req = controller.request_shutdown(
            reason=ShutdownReason.USER_REQUEST,
            source="test",
        )
        controller._write_state("SHUTDOWN_REQUESTED", req)

        state_file = diagnostics_dir / "shutdown_state.json"
        assert state_file.exists()
        data = json.loads(state_file.read_text(encoding="utf-8"))
        assert data["phase"] == "SHUTDOWN_REQUESTED"
        assert data["reason"] == "USER_REQUEST"
        assert data["shutdown_id"] == req.id

    def test_load_previous_shutdown(self, controller, diagnostics_dir):
        # Write a state file manually
        state_file = diagnostics_dir / "shutdown_state.json"
        state_file.write_text(
            json.dumps(
                {
                    "phase": "SHUTDOWN_RUNNING",
                    "shutdown_id": "test-0001",
                    "reason": "SIGNAL",
                }
            ),
            encoding="utf-8",
        )

        data = controller.load_previous_shutdown()
        assert data is not None
        assert data["phase"] == "SHUTDOWN_RUNNING"
        assert data["shutdown_id"] == "test-0001"

    def test_consume_deletes_file(self, controller, diagnostics_dir):
        state_file = diagnostics_dir / "shutdown_state.json"
        state_file.write_text(
            json.dumps({"phase": "EXITED", "shutdown_id": "test-0002"}),
            encoding="utf-8",
        )

        data = controller.consume_previous_shutdown()
        assert data is not None
        assert not state_file.exists()

    def test_load_returns_none_when_no_file(self, controller):
        assert controller.load_previous_shutdown() is None

    def test_load_handles_corrupt_json(self, controller, diagnostics_dir):
        state_file = diagnostics_dir / "shutdown_state.json"
        state_file.write_text("not valid json {{{", encoding="utf-8")
        assert controller.load_previous_shutdown() is None

    def test_mark_running(self, controller, diagnostics_dir):
        controller.mark_running()
        state_file = diagnostics_dir / "app_state.json"
        assert state_file.exists()
        data = json.loads(state_file.read_text(encoding="utf-8"))
        assert data["state"] == "RUNNING"
        assert data["pid"] > 0

    def test_mark_clean_exit(self, controller, diagnostics_dir):
        controller.mark_clean_exit()
        state_file = diagnostics_dir / "app_state.json"
        assert state_file.exists()
        data = json.loads(state_file.read_text(encoding="utf-8"))
        assert data["state"] == "CLEAN_EXIT"


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------


class TestDiagnostics:
    def test_diagnostics_initial_state(self, controller):
        diag = controller.get_diagnostics()
        assert diag["state"] == "RUNNING"
        assert diag["total_requests"] == 0
        assert diag["accepted_request"] is None

    def test_diagnostics_after_request(self, controller):
        controller.request_shutdown(
            reason=ShutdownReason.USER_REQUEST,
            source="test",
        )
        diag = controller.get_diagnostics()
        assert diag["state"] == "SHUTDOWN_REQUESTED"
        assert diag["total_requests"] == 1
        assert diag["accepted_request"]["reason"] == "USER_REQUEST"


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------


class TestSingleton:
    def test_get_returns_same_instance(self):
        a = get_shutdown_controller()
        b = get_shutdown_controller()
        assert a is b

    def test_reset_creates_new_instance(self):
        a = get_shutdown_controller()
        reset_shutdown_controller()
        b = get_shutdown_controller()
        assert a is not b


# ---------------------------------------------------------------------------
# ShutdownReason taxonomy
# ---------------------------------------------------------------------------


class TestShutdownReason:
    def test_all_reasons_have_values(self):
        reasons = list(ShutdownReason)
        assert len(reasons) >= 9  # at least the documented ones
        for r in reasons:
            assert isinstance(r.value, str)
            assert len(r.value) > 0

    def test_reasons_are_distinct(self):
        values = [r.value for r in ShutdownReason]
        assert len(values) == len(set(values))


# ---------------------------------------------------------------------------
# Integration: wait_for_shutdown + execute_shutdown
# ---------------------------------------------------------------------------


class TestShutdownExecution:
    @pytest.mark.asyncio
    async def test_wait_for_shutdown_returns_after_request(self, controller):
        """wait_for_shutdown should return once a request is accepted."""
        import asyncio

        async def _delayed_request():
            await asyncio.sleep(0.05)
            controller.request_shutdown(
                reason=ShutdownReason.USER_REQUEST,
                source="test:delayed",
            )

        asyncio.create_task(_delayed_request())
        await controller.wait_for_shutdown()
        assert controller.state == ShutdownState.SHUTDOWN_REQUESTED

    @pytest.mark.asyncio
    async def test_execute_transitions_to_exited(self, controller, mock_supervisor):
        """Full lifecycle: request → execute → EXITED with forensic state."""
        import json

        controller.set_supervisor(mock_supervisor)
        req = controller.request_shutdown(
            reason=ShutdownReason.SIGNAL,
            source="test:execute",
        )
        assert req is not None

        await controller.execute_shutdown()
        assert controller.state == ShutdownState.EXITED
        assert req is controller.accepted_request

        # Forensic state file should show EXITED
        state_file = controller._diagnostics_dir / "shutdown_state.json"
        assert state_file.exists()
        data = json.loads(state_file.read_text(encoding="utf-8"))
        assert data["phase"] == "EXITED"
        assert data["reason"] == "SIGNAL"
        assert data["shutdown_id"] == req.id
