import time
import threading
import pytest
from unittest.mock import MagicMock, patch


class TestHealthState:
    def test_enum_values(self):
        from core.health_monitor import HealthState

        assert HealthState.UNKNOWN.value == "UNKNOWN"
        assert HealthState.STARTING.value == "STARTING"
        assert HealthState.RUNNING.value == "RUNNING"
        assert HealthState.STOPPING.value == "STOPPING"
        assert HealthState.STOPPED.value == "STOPPED"
        assert HealthState.DEGRADED.value == "DEGRADED"
        assert HealthState.FAILED.value == "FAILED"
        assert HealthState.RECOVERING.value == "RECOVERING"


class TestHeartbeatRecord:
    def test_defaults(self):
        from core.health_monitor import HeartbeatRecord

        r = HeartbeatRecord(component="test")
        assert r.component == "test"
        assert r.alive is True
        assert r.last_activity == 0.0
        assert r.last_error is None
        assert r.missed_beats == 0

    def test_to_dict(self):
        from core.health_monitor import HeartbeatRecord

        r = HeartbeatRecord(component="test")
        d = r.to_dict()
        assert d["component"] == "test"
        assert d["alive"] is True
        assert d["missed_beats"] == 0


class TestHealthMonitor:
    def test_register_component(self):
        from core.health_monitor import HealthMonitor, HealthState

        hm = HealthMonitor()
        hm.register("comp_a")
        assert hm.get_state("comp_a") == HealthState.UNKNOWN

    def test_register_with_initial_state(self):
        from core.health_monitor import HealthMonitor, HealthState

        hm = HealthMonitor()
        hm.register("comp_a", initial_state=HealthState.STARTING)
        assert hm.get_state("comp_a") == HealthState.STARTING

    def test_register_duplicate_is_noop(self):
        from core.health_monitor import HealthMonitor, HealthState

        hm = HealthMonitor()
        hm.register("comp")
        hm.register("comp", initial_state=HealthState.RUNNING)
        assert hm.get_state("comp") == HealthState.UNKNOWN

    def test_unregister_component(self):
        from core.health_monitor import HealthMonitor, HealthState

        hm = HealthMonitor()
        hm.register("comp")
        assert hm.get_state("comp") == HealthState.UNKNOWN
        hm.unregister("comp")
        assert hm.get_state("comp") == HealthState.UNKNOWN

    def test_unregister_nonexistent_is_safe(self):
        from core.health_monitor import HealthMonitor

        hm = HealthMonitor()
        hm.unregister("nope")

    def test_valid_state_transition(self):
        from core.health_monitor import HealthMonitor, HealthState

        hm = HealthMonitor()
        hm.register("comp")
        assert hm.set_state("comp", HealthState.STARTING) is True
        assert hm.get_state("comp") == HealthState.STARTING

    def test_illegal_state_transition_returns_false(self):
        from core.health_monitor import HealthMonitor, HealthState

        hm = HealthMonitor()
        hm.register("comp")
        assert hm.set_state("comp", HealthState.RUNNING) is False

    def test_set_state_same_state_returns_true(self):
        from core.health_monitor import HealthMonitor, HealthState

        hm = HealthMonitor()
        hm.register("comp", initial_state=HealthState.STARTING)
        assert hm.set_state("comp", HealthState.STARTING) is True

    def test_state_listener_called(self):
        from core.health_monitor import HealthMonitor, HealthState

        hm = HealthMonitor()
        hm.register("comp")
        events = []
        hm.add_state_listener(lambda c, o, n: events.append((c, o, n)))
        hm.set_state("comp", HealthState.STARTING)
        hm.set_state("comp", HealthState.RUNNING)
        assert len(events) == 2
        assert events[0] == ("comp", HealthState.UNKNOWN, HealthState.STARTING)
        assert events[1] == ("comp", HealthState.STARTING, HealthState.RUNNING)

    def test_state_listener_exception_does_not_propagate(self):
        from core.health_monitor import HealthMonitor, HealthState

        hm = HealthMonitor()
        hm.register("comp")

        def listener(c, o, n):
            raise RuntimeError("boom")

        hm.add_state_listener(listener)
        hm.set_state("comp", HealthState.STARTING)
        assert hm.get_state("comp") == HealthState.STARTING

    def test_get_states(self):
        from core.health_monitor import HealthMonitor, HealthState

        hm = HealthMonitor()
        hm.register("a", HealthState.RUNNING)
        hm.register("b", HealthState.STARTING)
        states = hm.get_states()
        assert states == {"a": "RUNNING", "b": "STARTING"}

    def test_set_state_on_unregistered_component_registers_automatically(self):
        from core.health_monitor import HealthMonitor, HealthState

        hm = HealthMonitor()
        assert hm.set_state("auto_reg", HealthState.RUNNING) is True
        assert hm.get_state("auto_reg") == HealthState.RUNNING

    def test_all_valid_transitions(self):
        from core.health_monitor import HealthMonitor, HealthState

        hm = HealthMonitor()
        transitions = [
            (HealthState.UNKNOWN, HealthState.STARTING),
            (HealthState.STARTING, HealthState.RUNNING),
            (HealthState.RUNNING, HealthState.DEGRADED),
            (HealthState.DEGRADED, HealthState.RUNNING),
            (HealthState.RUNNING, HealthState.FAILED),
            (HealthState.FAILED, HealthState.RECOVERING),
            (HealthState.RECOVERING, HealthState.RUNNING),
            (HealthState.RUNNING, HealthState.STOPPING),
            (HealthState.STOPPING, HealthState.STOPPED),
            (HealthState.STOPPED, HealthState.STARTING),
            (HealthState.FAILED, HealthState.STOPPED),
            (HealthState.FAILED, HealthState.STARTING),
            (HealthState.RUNNING, HealthState.RECOVERING),
            (HealthState.RECOVERING, HealthState.DEGRADED),
            (HealthState.STOPPING, HealthState.FAILED),
            (HealthState.STARTING, HealthState.FAILED),
            (HealthState.STARTING, HealthState.DEGRADED),
            (HealthState.DEGRADED, HealthState.FAILED),
            (HealthState.DEGRADED, HealthState.STOPPING),
            (HealthState.DEGRADED, HealthState.RECOVERING),
            (HealthState.RECOVERING, HealthState.FAILED),
            (HealthState.RECOVERING, HealthState.STOPPING),
            (HealthState.STARTING, HealthState.STOPPED),
        ]
        for initial, target in transitions:
            hm = HealthMonitor()
            hm.register("comp", initial)
            assert hm.set_state("comp", target) is True, f"{initial.value} -> {target.value}"

    def test_illegal_transitions(self):
        from core.health_monitor import HealthMonitor, HealthState

        hm = HealthMonitor()
        illegal = [
            (HealthState.UNKNOWN, HealthState.RUNNING),
            (HealthState.UNKNOWN, HealthState.FAILED),
            (HealthState.UNKNOWN, HealthState.STOPPED),
            (HealthState.RUNNING, HealthState.UNKNOWN),
            (HealthState.RUNNING, HealthState.STARTING),
            (HealthState.STOPPED, HealthState.RUNNING),
            (HealthState.FAILED, HealthState.RUNNING),
            (HealthState.FAILED, HealthState.DEGRADED),
            (HealthState.STOPPING, HealthState.RUNNING),
            (HealthState.STOPPING, HealthState.STARTING),
            (HealthState.RECOVERING, HealthState.UNKNOWN),
            (HealthState.RECOVERING, HealthState.STARTING),
            (HealthState.DEGRADED, HealthState.STARTING),
            (HealthState.DEGRADED, HealthState.UNKNOWN),
        ]
        for initial, target in illegal:
            hm = HealthMonitor()
            hm.register("comp", initial)
            assert hm.set_state("comp", target) is False, f"{initial.value} -> {target.value}"

    def test_record_heartbeat_creates_record(self):
        from core.health_monitor import HealthMonitor, HealthState

        hm = HealthMonitor()
        hm.record_heartbeat("comp", response_time_ms=12.5)
        hb = hm.get_heartbeat("comp")
        assert hb is not None
        assert hb.component == "comp"
        assert hb.alive is True
        assert hb.response_time_ms == 12.5
        assert hm.get_state("comp") == HealthState.UNKNOWN

    def test_record_heartbeat_promotes_state(self):
        from core.health_monitor import HealthMonitor, HealthState

        hm = HealthMonitor()
        hm.register("comp", HealthState.RECOVERING)
        hm.record_heartbeat("comp")
        assert hm.get_state("comp") == HealthState.RUNNING

    def test_record_heartbeat_does_not_demote_running(self):
        from core.health_monitor import HealthMonitor, HealthState

        hm = HealthMonitor()
        hm.register("comp", HealthState.DEGRADED)
        hm.record_heartbeat("comp")
        assert hm.get_state("comp") == HealthState.RUNNING

    def test_record_heartbeat_from_failed(self):
        from core.health_monitor import HealthMonitor, HealthState

        hm = HealthMonitor()
        hm.register("comp", HealthState.FAILED)
        hm.record_heartbeat("comp")
        assert hm.get_state("comp") == HealthState.FAILED

    def test_record_heartbeat_from_stopped(self):
        from core.health_monitor import HealthMonitor, HealthState

        hm = HealthMonitor()
        hm.register("comp", HealthState.STOPPED)
        hm.record_heartbeat("comp")
        assert hm.get_state("comp") == HealthState.STOPPED

    def test_record_heartbeat_updates_existing(self):
        from core.health_monitor import HealthMonitor

        hm = HealthMonitor()
        hm.record_heartbeat("comp", response_time_ms=5.0)
        hb1 = hm.get_heartbeat("comp")
        assert hb1.response_time_ms == 5.0
        hm.record_heartbeat("comp", response_time_ms=10.0)
        hb2 = hm.get_heartbeat("comp")
        assert hb2.response_time_ms == 10.0

    def test_record_error(self):
        from core.health_monitor import HealthMonitor

        hm = HealthMonitor()
        hm.record_error("comp", "something went wrong")
        hb = hm.get_heartbeat("comp")
        assert hb is not None
        assert "something went wrong" in hb.last_error

    def test_record_error_on_unregistered_component(self):
        from core.health_monitor import HealthMonitor

        hm = HealthMonitor()
        hm.record_error("comp", "err")
        hb = hm.get_heartbeat("comp")
        assert hb is not None
        assert hb.last_error == "err"

    def test_record_success(self):
        from core.health_monitor import HealthMonitor

        hm = HealthMonitor()
        hm.record_heartbeat("comp")
        hm.record_success("comp")
        hb = hm.get_heartbeat("comp")
        assert hb.last_successful_operation > 0

    def test_record_success_no_record(self):
        from core.health_monitor import HealthMonitor

        hm = HealthMonitor()
        hm.record_success("nope")

    def test_check_heartbeat_missing_component(self):
        from core.health_monitor import HealthMonitor

        hm = HealthMonitor()
        assert hm.check_heartbeat("nope") is False

    def test_check_heartbeat_recent(self):
        from core.health_monitor import HealthMonitor

        hm = HealthMonitor()
        hm.record_heartbeat("comp")
        assert hm.check_heartbeat("comp", timeout=60.0) is True

    def test_check_heartbeat_missed_once(self):
        from core.health_monitor import HealthMonitor

        hm = HealthMonitor()
        hm.record_heartbeat("comp")
        hm._heartbeats["comp"].last_activity = time.time() - 100
        result = hm.check_heartbeat("comp", timeout=30.0)
        assert result is False
        hb = hm.get_heartbeat("comp")
        assert hb.missed_beats == 1

    def test_check_heartbeat_three_misses_marks_alive_false(self):
        from core.health_monitor import HealthMonitor, HealthState

        hm = HealthMonitor()
        hm.register("comp", HealthState.RUNNING)
        hm.record_heartbeat("comp")
        for _ in range(3):
            hm._heartbeats["comp"].last_activity = time.time() - 100
            hm.check_heartbeat("comp", timeout=30.0)
        hb = hm.get_heartbeat("comp")
        assert hb.alive is False

    def test_check_heartbeat_three_misses_degrades_state(self):
        from core.health_monitor import HealthMonitor, HealthState

        hm = HealthMonitor()
        hm.register("comp", HealthState.RUNNING)
        hm.record_heartbeat("comp")
        for _ in range(3):
            hm._heartbeats["comp"].last_activity = time.time() - 100
            hm.check_heartbeat("comp", timeout=30.0)
        assert hm.get_state("comp") == HealthState.DEGRADED

    def test_check_heartbeat_does_not_degrade_non_running(self):
        from core.health_monitor import HealthMonitor, HealthState

        hm = HealthMonitor()
        hm.register("comp", HealthState.FAILED)
        hm.record_heartbeat("comp")
        for _ in range(3):
            hm._heartbeats["comp"].last_activity = time.time() - 100
            hm.check_heartbeat("comp", timeout=30.0)
        assert hm.get_state("comp") == HealthState.FAILED

    def test_check_heartbeat_resets_missed_count_on_success(self):
        from core.health_monitor import HealthMonitor

        hm = HealthMonitor()
        hm.record_heartbeat("comp")
        hm._heartbeats["comp"].last_activity = time.time() - 100
        hm.check_heartbeat("comp", timeout=30.0)
        hm.record_heartbeat("comp")
        assert hm.check_heartbeat("comp", timeout=60.0) is True
        assert hm.get_heartbeat("comp").missed_beats == 0

    def test_get_heartbeats(self):
        from core.health_monitor import HealthMonitor

        hm = HealthMonitor()
        hm.record_heartbeat("a")
        hm.record_heartbeat("b")
        hbs = hm.get_heartbeats()
        assert "a" in hbs
        assert "b" in hbs

    def test_get_heartbeat_returns_copy(self):
        from core.health_monitor import HealthMonitor

        hm = HealthMonitor()
        hm.record_heartbeat("comp")
        hb1 = hm.get_heartbeat("comp")
        hb2 = hm.get_heartbeat("comp")
        hb1.missed_beats = 99
        assert hb2.missed_beats == 0

    def test_uptime(self):
        from core.health_monitor import HealthMonitor

        hm = HealthMonitor()
        uptime = hm.uptime()
        assert uptime >= 0.0

    def test_summary_empty(self):
        from core.health_monitor import HealthMonitor

        hm = HealthMonitor()
        s = hm.summary()
        assert s["total_components"] == 0
        assert s["running"] == 0

    def test_summary_with_failed_and_degraded(self):
        from core.health_monitor import HealthMonitor, HealthState

        hm = HealthMonitor()
        hm.register("ok", HealthState.RUNNING)
        hm.register("bad", HealthState.FAILED)
        hm.register("de", HealthState.DEGRADED)
        s = hm.summary()
        assert s["total_components"] == 3
        assert s["running"] == 1
        assert s["failed"] == 1
        assert s["degraded"] == 1
        assert "bad" in s["failed_components"]
        assert "de" in s["degraded_components"]

    def test_summary_last_error(self):
        from core.health_monitor import HealthMonitor

        hm = HealthMonitor()
        hm.record_error("comp", "test error")
        s = hm.summary()
        assert s["last_error"] is not None

    def test_thread_safety(self):
        from core.health_monitor import HealthMonitor, HealthState

        hm = HealthMonitor()
        errors = []

        def worker():
            try:
                for i in range(100):
                    hm.register(f"t{i}")
                    hm.set_state(f"t{i}", HealthState.RUNNING)
                    hm.record_heartbeat(f"t{i}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors

    def test_summary_with_registered_and_errored(self):
        from core.health_monitor import HealthMonitor, HealthState

        hm = HealthMonitor()
        hm.register("good", HealthState.RUNNING)
        hm.record_error("good", "minor glitch")
        s = hm.summary()
        assert s["total_components"] == 1
        assert s["states"]["good"] == "RUNNING"
        assert "minor glitch" in (s["last_error"] or "")


class TestGetHealthMonitor:
    def test_singleton(self):
        from core.health_monitor import get_health_monitor, reset_health_monitor

        reset_health_monitor()
        m1 = get_health_monitor()
        m2 = get_health_monitor()
        assert m1 is m2

    def test_reset_creates_new_instance(self):
        from core.health_monitor import get_health_monitor, reset_health_monitor

        reset_health_monitor()
        m1 = get_health_monitor()
        reset_health_monitor()
        m2 = get_health_monitor()
        assert m1 is not m2
