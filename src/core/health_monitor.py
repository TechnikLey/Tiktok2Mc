"""Health monitoring framework for TikTok2Mc.

Every major subsystem exposes a health state with valid transitions.
Unexpected transitions are detected automatically and generate error codes.

Health States:
    STARTING   - Component is initializing
    RUNNING    - Component is operating normally
    STOPPING   - Component is shutting down
    STOPPED    - Component is stopped
    DEGRADED   - Component is running with reduced functionality
    FAILED     - Component has failed
    RECOVERING - Component is attempting recovery
    UNKNOWN    - Component state is not known

Valid Transitions:
    UNKNOWN    -> STARTING
    STARTING   -> RUNNING | FAILED | DEGRADED | STOPPED
    RUNNING    -> DEGRADED | FAILED | STOPPING | RECOVERING
    DEGRADED   -> RUNNING | FAILED | STOPPING | RECOVERING
    RECOVERING -> RUNNING | DEGRADED | FAILED | STOPPING
    FAILED     -> RECOVERING | STOPPED | STARTING
    STOPPING   -> STOPPED | FAILED
    STOPPED    -> STARTING
"""

from __future__ import annotations

import enum
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)


class HealthState(str, enum.Enum):
    """Lifecycle state of a monitored subsystem.

The values are serialized as their uppercase names; use ``.value`` when
putting a state into an API response."""

    UNKNOWN = "UNKNOWN"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"
    RECOVERING = "RECOVERING"


_VALID_TRANSITIONS: dict[HealthState, set[HealthState]] = {
    HealthState.UNKNOWN: {HealthState.STARTING},
    HealthState.STARTING: {
        HealthState.RUNNING,
        HealthState.FAILED,
        HealthState.DEGRADED,
        HealthState.STOPPING,
        HealthState.STOPPED,
    },
    HealthState.RUNNING: {
        HealthState.DEGRADED,
        HealthState.FAILED,
        HealthState.STOPPING,
        HealthState.RECOVERING,
    },
    HealthState.DEGRADED: {
        HealthState.RUNNING,
        HealthState.FAILED,
        HealthState.STOPPING,
        HealthState.RECOVERING,
    },
    HealthState.RECOVERING: {
        HealthState.RUNNING,
        HealthState.DEGRADED,
        HealthState.FAILED,
        HealthState.STOPPING,
    },
    HealthState.FAILED: {
        HealthState.RECOVERING,
        HealthState.STOPPED,
        HealthState.STARTING,
    },
    HealthState.STOPPING: {HealthState.STOPPED, HealthState.FAILED},
    HealthState.STOPPED: {HealthState.STARTING},
}


@dataclass
class HeartbeatRecord:
    """Latest heartbeat and error information for one component.

Timestamps are Unix epoch seconds. ``uptime`` stores the time of the first
heartbeat rather than a duration."""

    component: str
    alive: bool = True
    last_activity: float = 0.0
    last_successful_operation: float = 0.0
    last_error: str | None = None
    last_error_time: float = 0.0
    response_time_ms: float = 0.0
    uptime: float = 0.0
    missed_beats: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable copy of the record.

Floating-point timings are rounded to two decimals for display."""

        return {
            "component": self.component,
            "alive": self.alive,
            "last_activity": self.last_activity,
            "last_successful_operation": self.last_successful_operation,
            "last_error": self.last_error,
            "last_error_time": self.last_error_time,
            "response_time_ms": round(self.response_time_ms, 2),
            "uptime": round(self.uptime, 2),
            "missed_beats": self.missed_beats,
        }


class HealthMonitor:
    """Central health monitor for all application subsystems.

    Thread-safe. Maintains health state and heartbeat records for
    every registered component.
    """

    def __init__(self) -> None:
        """Create an empty monitor with its own lock and start time."""
        self._lock = threading.Lock()
        self._states: dict[str, HealthState] = {}
        self._heartbeats: dict[str, HeartbeatRecord] = {}
        self._state_listeners: list[
            Callable[[str, HealthState, HealthState], None]
        ] = []
        self._start_time: float = time.time()
        self._last_error: str | None = None
        self._last_error_time: float = 0.0

    # ------------------------------------------------------------------
    # State management
    # ------------------------------------------------------------------

    def register(
        self, component: str, initial_state: HealthState = HealthState.UNKNOWN
    ) -> None:
        """Register a component if it is not registered yet.

Registering an existing component is a no-op, so callers can safely
register during repeated startup paths. A fresh heartbeat record is
created with the current time as last activity."""

        with self._lock:
            if component in self._states:
                return
            self._states[component] = initial_state
            self._heartbeats[component] = HeartbeatRecord(
                component=component,
                last_activity=time.time(),
            )
        log.debug(
            "[HEALTH] Registered '%s' with state %s", component, initial_state.value
        )

    def unregister(self, component: str) -> None:
        """Forget a component's state and heartbeat.

Unknown components are ignored."""

        with self._lock:
            self._states.pop(component, None)
            self._heartbeats.pop(component, None)
        log.debug("[HEALTH] Unregistered '%s'", component)

    def set_state(self, component: str, new_state: HealthState) -> bool:
        """Transition a component to *new_state*.

Unregistered components are registered implicitly. Transitions outside
:data:`_VALID_TRANSITIONS` are logged and rejected. Setting the current
state again counts as success but does not notify listeners.

Returns:
    ``True`` when the state was applied or already current, ``False`` when
    the transition is illegal."""

        with self._lock:
            current = self._states.get(component)
            if current is None:
                self._states[component] = new_state
                self._heartbeats.setdefault(
                    component, HeartbeatRecord(component=component)
                )
                return True

            if current == new_state:
                return True

            allowed = _VALID_TRANSITIONS.get(current, set())
            if new_state not in allowed:
                log.error(
                    "[HEALTH] Illegal state transition '%s': %s -> %s",
                    component,
                    current.value,
                    new_state.value,
                )
                return False

            self._states[component] = new_state
            old_state = current

        log.info(
            "[HEALTH] '%s' state: %s -> %s", component, old_state.value, new_state.value
        )
        for listener in self._state_listeners:
            try:
                listener(component, old_state, new_state)
            except (
                Exception
            ) as exc:  # one broken listener must not break health updates
                log.warning(
                    "[HEALTH] State listener failed for '%s': %s", component, exc
                )
        return True

    def get_state(self, component: str) -> HealthState:
        """Return the component's state, or ``UNKNOWN`` if it is not registered."""
        with self._lock:
            return self._states.get(component, HealthState.UNKNOWN)

    def get_states(self) -> dict[str, str]:
        """Return all component states as a name-to-value mapping."""
        with self._lock:
            return {k: v.value for k, v in self._states.items()}

    def add_state_listener(
        self, callback: Callable[[str, HealthState, HealthState], None]
    ) -> None:
        """Register a callback invoked after every successful state change.

The callback receives ``(component, old_state, new_state)``. Exceptions
raised by listeners are caught and logged so they cannot break health
updates."""

        self._state_listeners.append(callback)

    # ------------------------------------------------------------------
    # Heartbeat tracking
    # ------------------------------------------------------------------

    def record_heartbeat(self, component: str, response_time_ms: float = 0.0) -> None:
        """Record activity for a component and refresh its liveness data.

A missing component is created implicitly. The heartbeat marks the record
alive, resets the missed-beat counter and moves the component to
``RUNNING`` when it was previously unknown, starting, recovering or
degraded. Other states (for example ``STOPPING``) are left untouched."""

        now = time.time()
        with self._lock:
            record = self._heartbeats.get(component)
            if record is None:
                record = HeartbeatRecord(component=component)
                self._heartbeats[component] = record
            record.alive = True
            record.last_activity = now
            record.last_successful_operation = now
            record.response_time_ms = response_time_ms
            record.missed_beats = 0
            if record.uptime == 0.0:
                record.uptime = now
            # Also set state if component exists
            current = self._states.get(component)
            if current in (
                HealthState.UNKNOWN,
                HealthState.STARTING,
                HealthState.RECOVERING,
                HealthState.DEGRADED,
            ):
                self._states[component] = HealthState.RUNNING

    def record_error(self, component: str, error_message: str) -> None:
        """Store the latest error for a component and for the monitor overall.

The component does not change state here; callers decide whether an error
is fatal, degraded or transient."""

        now = time.time()
        with self._lock:
            record = self._heartbeats.get(component)
            if record is None:
                record = HeartbeatRecord(component=component)
                self._heartbeats[component] = record
            record.last_error = error_message
            record.last_error_time = now
            self._last_error = f"[{component}] {error_message}"
            self._last_error_time = now

    def record_success(self, component: str) -> None:
        """Update the last successful operation time of a known component."""
        with self._lock:
            record = self._heartbeats.get(component)
            if record:
                record.last_successful_operation = time.time()

    def check_heartbeat(self, component: str, timeout: float = 60.0) -> bool:
        """Check whether a component has sent activity within *timeout* seconds.

Each check on a stale component increments ``missed_beats``; after three
missed checks the record is marked dead and a ``RUNNING`` component
becomes ``DEGRADED``. A fresh heartbeat resets the counter.

Returns:
    ``True`` when the last activity is within the timeout, otherwise
    ``False`` (including for unknown components)."""

        now = time.time()
        with self._lock:
            record = self._heartbeats.get(component)
            if record is None:
                return False
            elapsed = now - record.last_activity
            if elapsed > timeout:
                record.missed_beats += 1
                if record.missed_beats == 1 or record.missed_beats % 5 == 0:
                    log.warning(
                        "[HEALTH] '%s' missed heartbeat (%ds since last activity, %d missed)",
                        component,
                        elapsed,
                        record.missed_beats,
                    )
                if record.missed_beats >= 3:
                    record.alive = False
                    current = self._states.get(component)
                    if current == HealthState.RUNNING:
                        self._states[component] = HealthState.DEGRADED
                return False
            record.missed_beats = 0
            return True

    def get_heartbeat(self, component: str) -> HeartbeatRecord | None:
        """Return a snapshot of a component's heartbeat, or ``None`` if unknown.

The returned record is a copy and can be mutated without affecting the
monitor."""

        with self._lock:
            record = self._heartbeats.get(component)
            if record:
                return HeartbeatRecord(**record.__dict__)
            return None

    def get_heartbeats(self) -> dict[str, dict[str, Any]]:
        """Return all heartbeat records as JSON-serializable dictionaries."""
        with self._lock:
            return {k: v.to_dict() for k, v in self._heartbeats.items()}

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def uptime(self) -> float:
        """Return the monitor's uptime in seconds."""
        return time.time() - self._start_time

    def summary(self) -> dict[str, Any]:
        """Return aggregate health information for dashboards and diagnostics.

Includes counts by state, per-component states and heartbeats, the lists
of failed and degraded components, and the most recent error."""

        with self._lock:
            states = dict(self._states)
            heartbeats = {k: v.to_dict() for k, v in self._heartbeats.items()}

        failed = [k for k, v in states.items() if v == HealthState.FAILED]
        degraded = [k for k, v in states.items() if v == HealthState.DEGRADED]
        running = [k for k, v in states.items() if v == HealthState.RUNNING]

        return {
            "uptime_seconds": round(time.time() - self._start_time, 2),
            "total_components": len(states),
            "running": len(running),
            "degraded": len(degraded),
            "failed": len(failed),
            "states": {k: v.value for k, v in states.items()},
            "heartbeats": heartbeats,
            "failed_components": failed,
            "degraded_components": degraded,
            "last_error": self._last_error,
            "last_error_time": self._last_error_time,
        }


# Module-level singleton
_monitor: HealthMonitor | None = None
_monitor_lock = threading.Lock()


def get_health_monitor() -> HealthMonitor:
    """Return the process-wide health monitor, creating it on first use."""
    global _monitor
    if _monitor is None:
        with _monitor_lock:
            if _monitor is None:
                _monitor = HealthMonitor()
    return _monitor


def reset_health_monitor() -> None:
    """Replace the global monitor with a fresh instance.

Intended for tests and full restarts; existing references keep pointing at
the previous monitor."""

    global _monitor
    with _monitor_lock:
        _monitor = HealthMonitor()
