"""Centralized shutdown controller for TikTok2Mc.

Provides a single point of control for all shutdown requests. Every component
that wants to shut down the application must call ``request_shutdown()`` instead
of invoking ``Supervisor.shutdown()`` directly.  The controller:

* Assigns a unique ID to every shutdown for log correlation.
* Captures the caller's stack trace for forensic analysis.
* Enforces a state machine to prevent double-shutdown races.
* Persists a forensic state file so the *next* start can detect whether the
  previous exit was clean or abnormal.
* Logs every state transition with full diagnostics.
"""

from __future__ import annotations

import asyncio
import enum
import json
import logging
import os
import threading
import time
import traceback
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.lifecycle import ProcessSupervisor

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shutdown reason taxonomy
# ---------------------------------------------------------------------------


class ShutdownReason(str, enum.Enum):
    """Why the shutdown was requested."""

    NORMAL_SHUTDOWN = "NORMAL_SHUTDOWN"
    USER_REQUEST = "USER_REQUEST"
    SIGNAL = "SIGNAL"
    EXCEPTION = "EXCEPTION"
    FATAL_ERROR = "FATAL_ERROR"
    WATCHDOG = "WATCHDOG"
    TIMEOUT = "TIMEOUT"
    OS_REQUEST = "OS_REQUEST"
    PLUGIN_REQUEST = "PLUGIN_REQUEST"
    UNKNOWN = "UNKNOWN"


# ---------------------------------------------------------------------------
# Shutdown state machine
# ---------------------------------------------------------------------------


class ShutdownState(str, enum.Enum):
    """Lifecycle states of the shutdown process."""

    RUNNING = "RUNNING"
    SHUTDOWN_REQUESTED = "SHUTDOWN_REQUESTED"
    SHUTDOWN_RUNNING = "SHUTDOWN_RUNNING"
    CLEANUP = "CLEANUP"
    EXITING = "EXITING"
    EXITED = "EXITED"


# Valid state transitions — anything else is logged and rejected.
_VALID_TRANSITIONS: dict[ShutdownState, set[ShutdownState]] = {
    ShutdownState.RUNNING: {ShutdownState.SHUTDOWN_REQUESTED},
    ShutdownState.SHUTDOWN_REQUESTED: {
        ShutdownState.SHUTDOWN_RUNNING,
        ShutdownState.RUNNING,
    },
    # Allow skipping directly to EXITED on error (no supervisor, exception, etc.)
    ShutdownState.SHUTDOWN_RUNNING: {ShutdownState.CLEANUP, ShutdownState.EXITED},
    ShutdownState.CLEANUP: {ShutdownState.EXITING, ShutdownState.EXITED},
    ShutdownState.EXITING: {ShutdownState.EXITED},
    ShutdownState.EXITED: set(),
}


# ---------------------------------------------------------------------------
# Shutdown request record
# ---------------------------------------------------------------------------


class ShutdownRequest:
    """Immutable record of a single shutdown request."""

    __slots__ = (
        "id",
        "process_id",
        "reason",
        "requester",
        "source",
        "stack",
        "thread_id",
        "thread_name",
        "timestamp",
        "timestamp_iso",
    )

    def __init__(
        self,
        *,
        reason: ShutdownReason = ShutdownReason.UNKNOWN,
        source: str = "",
        stack: str = "",
        requester: dict[str, Any] | None = None,
    ) -> None:
        self.id = _make_shutdown_id()
        self.reason = reason
        self.source = source
        self.stack = stack
        self.thread_name = threading.current_thread().name
        self.thread_id = threading.get_ident()
        self.process_id = os.getpid()
        self.timestamp = time.time()
        self.timestamp_iso = time.strftime(
            "%Y-%m-%dT%H:%M:%S", time.localtime(self.timestamp)
        )
        self.requester = requester

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "reason": self.reason.value,
            "source": self.source,
            "stack": self.stack,
            "thread_name": self.thread_name,
            "thread_id": self.thread_id,
            "process_id": self.process_id,
            "timestamp": self.timestamp,
            "timestamp_iso": self.timestamp_iso,
        }
        if self.requester:
            data["requester"] = self.requester
        return data


# ---------------------------------------------------------------------------
# ShutdownController
# ---------------------------------------------------------------------------


class ShutdownController:
    """Central coordinator for all shutdown requests.

    Usage::

        ctrl = get_shutdown_controller()

        # Any component that wants to shut down:
        ctrl.request_shutdown(reason=ShutdownReason.USER_REQUEST, source="gui.close")

        # The supervisor main loop:
        await ctrl.wait_for_shutdown()
        # ... supervisor.shutdown() is called internally
    """

    def __init__(self, diagnostics_dir: Path | None = None) -> None:
        self._lock = threading.Lock()
        self._state = ShutdownState.RUNNING
        self._requests: list[ShutdownRequest] = []
        self._accepted: ShutdownRequest | None = None
        self._supervisor: ProcessSupervisor | None = None
        self._shutdown_event: asyncio.Event | None = None
        self._diagnostics_dir = diagnostics_dir
        self._state_file: Path | None = None
        if diagnostics_dir is not None:
            self._state_file = diagnostics_dir / "shutdown_state.json"
        # Previous shutdown diagnostics (loaded at startup)
        self._previous_shutdown: dict[str, Any] | None = None

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def set_supervisor(self, supervisor: ProcessSupervisor) -> None:
        """Bind the supervisor that will perform the actual shutdown."""
        self._supervisor = supervisor

    def set_diagnostics_dir(self, diagnostics_dir: Path) -> None:
        """Set the directory for forensic state files (shutdown_state.json, app_state.json).

        This should be a persistent directory that survives restarts, e.g. ``data/diagnostics/``.
        The directory is created on demand when a state file is written.
        """
        self._diagnostics_dir = diagnostics_dir
        self._state_file = diagnostics_dir / "shutdown_state.json"

    # ------------------------------------------------------------------
    # State machine
    # ------------------------------------------------------------------

    @property
    def state(self) -> ShutdownState:
        with self._lock:
            return self._state

    def _transition(self, target: ShutdownState) -> bool:
        """Attempt a state transition. Returns True on success."""
        with self._lock:
            old = self._state
            allowed = _VALID_TRANSITIONS.get(old, set())
            if target not in allowed:
                log.warning(
                    "[SHUTDOWN] Invalid state transition: %s -> %s (allowed: %s)",
                    old.value,
                    target.value,
                    {s.value for s in allowed} if allowed else "none",
                )
                return False
            self._state = target
        log.info("[SHUTDOWN] State: %s -> %s", old.value, target.value)
        return True

    # ------------------------------------------------------------------
    # Request shutdown
    # ------------------------------------------------------------------

    def request_shutdown(
        self,
        *,
        reason: ShutdownReason = ShutdownReason.UNKNOWN,
        source: str = "",
        requester: dict[str, Any] | None = None,
    ) -> ShutdownRequest | None:
        """Request a shutdown. Returns the accepted request, or None if
        a shutdown is already pending/running.

        This method is safe to call from any thread.
        """
        # Capture stack trace of the caller
        stack = "".join(traceback.format_stack())

        request = ShutdownRequest(
            reason=reason, source=source, stack=stack, requester=requester
        )

        with self._lock:
            self._requests.append(request)

            # Only accept the first request
            if self._state != ShutdownState.RUNNING:
                log.info(
                    "[SHUTDOWN] Request #%s rejected (state=%s, already have #%s)",
                    request.id,
                    self._state.value,
                    self._accepted.id if self._accepted else "none",
                )
                return None

            self._state = ShutdownState.SHUTDOWN_REQUESTED
            self._accepted = request

        log.info(
            "[SHUTDOWN] request received\n"
            "  Shutdown ID: %s\n"
            "  Reason: %s\n"
            "  Source: %s\n"
            "  Thread: %s (id=%s)\n"
            "  Process: %s\n"
            "  Time: %s\n"
            "  Requester: %s\n"
            "  Stack:\n%s",
            request.id,
            request.reason.value,
            request.source,
            request.thread_name,
            request.thread_id,
            request.process_id,
            request.timestamp_iso,
            json.dumps(request.requester) if request.requester else "n/a",
            stack.rstrip(),
        )

        # Write forensic state
        self._write_state("SHUTDOWN_REQUESTED", request)
        return request

    # ------------------------------------------------------------------
    # Execute shutdown (called from the event loop)
    # ------------------------------------------------------------------

    async def execute_shutdown(self) -> None:
        """Execute the actual shutdown sequence.

        This must be called from the event loop (async context).
        Only one execution is allowed; subsequent calls are no-ops.
        """
        if not self._transition(ShutdownState.SHUTDOWN_RUNNING):
            return

        request = self._accepted
        if request is None:
            log.warning("[SHUTDOWN] execute_shutdown called but no request accepted")
            return

        log.info(
            "[SHUTDOWN] executing shutdown\n"
            "  Shutdown ID: %s\n"
            "  Reason: %s\n"
            "  Source: %s",
            request.id,
            request.reason.value,
            request.source,
        )

        if self._supervisor is None:
            log.error("[SHUTDOWN] No supervisor bound — cannot shut down")
            self._transition(ShutdownState.EXITED)
            self._write_state("ERROR", request, error="no supervisor bound")
            return

        # Write forensic state
        self._write_state("SHUTDOWN_RUNNING", request)

        try:
            self._transition(ShutdownState.CLEANUP)
            self._write_state("CLEANUP", request)

            await self._supervisor.shutdown()

            self._transition(ShutdownState.EXITING)
            self._write_state("EXITING", request)

            log.info("[SHUTDOWN] cleanup finished (ID: %s)", request.id)
            self._transition(ShutdownState.EXITED)
            self._write_state("EXITED", request)

        except Exception:
            log.exception(
                "[SHUTDOWN] Exception during shutdown (ID: %s)",
                request.id,
            )
            self._write_state("ERROR", request, error="exception during shutdown")
            # Still transition to EXITED so the system can proceed
            self._transition(ShutdownState.EXITED)

    # ------------------------------------------------------------------
    # Wait for shutdown
    # ------------------------------------------------------------------

    async def wait_for_shutdown(self) -> None:
        """Block until a shutdown is requested. Returns when the controller
        transitions out of RUNNING state."""
        while True:
            if self.state != ShutdownState.RUNNING:
                return
            await asyncio.sleep(0.1)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    @property
    def is_shutdown_requested(self) -> bool:
        return self.state in (
            ShutdownState.SHUTDOWN_REQUESTED,
            ShutdownState.SHUTDOWN_RUNNING,
            ShutdownState.CLEANUP,
            ShutdownState.EXITING,
            ShutdownState.EXITED,
        )

    @property
    def accepted_request(self) -> ShutdownRequest | None:
        with self._lock:
            return self._accepted

    @property
    def all_requests(self) -> list[ShutdownRequest]:
        with self._lock:
            return list(self._requests)

    # ------------------------------------------------------------------
    # Forensic state persistence
    # ------------------------------------------------------------------

    def _write_state(
        self, phase: str, request: ShutdownRequest, error: str | None = None
    ) -> None:
        """Write the current shutdown state to disk for next-start forensics."""
        if self._state_file is None:
            return
        data = {
            "phase": phase,
            "shutdown_id": request.id,
            "reason": request.reason.value,
            "source": request.source,
            "timestamp": request.timestamp,
            "timestamp_iso": request.timestamp_iso,
            "process_id": request.process_id,
            "thread_name": request.thread_name,
        }
        if error:
            data["error"] = error
        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._state_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
            tmp.replace(self._state_file)
        except OSError as exc:
            log.debug("[SHUTDOWN] Failed to write state file: %s", exc)

    def load_previous_shutdown(self) -> dict[str, Any] | None:
        """Load and return the previous shutdown state, or None if unavailable.

        Call this at startup to determine if the last exit was clean.
        The state file is consumed (deleted) after reading.
        """
        if self._state_file is None or not self._state_file.exists():
            return None
        try:
            data = json.loads(self._state_file.read_text(encoding="utf-8"))
            self._previous_shutdown = data
            return data
        except (OSError, json.JSONDecodeError) as exc:
            log.debug("[SHUTDOWN] Failed to read previous state: %s", exc)
            return None

    def consume_previous_shutdown(self) -> dict[str, Any] | None:
        """Load and delete the previous shutdown state file."""
        data = self.load_previous_shutdown()
        if self._state_file is not None and self._state_file.exists():
            try:
                self._state_file.unlink()
            except OSError:
                pass
        return data

    def mark_running(self) -> None:
        """Mark that the application is now running (for next-start forensics).

        Call this after successful startup.
        """
        if self._diagnostics_dir is None:
            return
        self._diagnostics_dir.mkdir(parents=True, exist_ok=True)
        state_file = self._diagnostics_dir / "app_state.json"
        try:
            data = {
                "state": "RUNNING",
                "pid": os.getpid(),
                "start_time": time.time(),
                "start_time_iso": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
            tmp = state_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
            tmp.replace(state_file)
        except OSError as exc:
            log.debug("[SHUTDOWN] Failed to write app state: %s", exc)

    def mark_clean_exit(self) -> None:
        """Mark that the application is exiting cleanly.

        Call this just before process exit.
        """
        if self._diagnostics_dir is None:
            return
        state_file = self._diagnostics_dir / "app_state.json"
        try:
            data = {
                "state": "CLEAN_EXIT",
                "pid": os.getpid(),
                "exit_time": time.time(),
                "exit_time_iso": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
            tmp = state_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
            tmp.replace(state_file)
        except OSError as exc:
            log.debug("[SHUTDOWN] Failed to write clean exit state: %s", exc)

    def get_diagnostics(self) -> dict[str, Any]:
        """Return diagnostic information about the shutdown controller state."""
        with self._lock:
            return {
                "state": self._state.value,
                "total_requests": len(self._requests),
                "accepted_request": self._accepted.to_dict()
                if self._accepted
                else None,
                "previous_shutdown": self._previous_shutdown,
            }


# ---------------------------------------------------------------------------
# Shutdown ID generation
# ---------------------------------------------------------------------------


_shutdown_counter = 0
_shutdown_counter_lock = threading.Lock()


def _make_shutdown_id() -> str:
    """Generate a unique shutdown ID like '2026-08-20T18:31:42-7F31'."""
    global _shutdown_counter
    with _shutdown_counter_lock:
        _shutdown_counter += 1
        seq = _shutdown_counter
    ts = time.strftime("%Y-%m-%dT%H:%M:%S")
    return f"{ts}-{seq:04X}"


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_controller: ShutdownController | None = None
_controller_lock = threading.Lock()


def get_shutdown_controller() -> ShutdownController:
    """Return the global ShutdownController, creating it on first call."""
    global _controller
    if _controller is None:
        with _controller_lock:
            if _controller is None:
                _controller = ShutdownController()
    return _controller


def reset_shutdown_controller() -> None:
    """Reset the singleton (for testing only)."""
    global _controller
    with _controller_lock:
        _controller = None
