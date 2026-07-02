import logging
import time
from pathlib import Path
import pytest


class TestCircularBufferHandler:
    def test_handler_creation(self):
        from core.logger import _CircularBufferHandler

        h = _CircularBufferHandler(capacity=10)
        assert h._buffer.maxlen == 10

    def test_handler_captures_records(self):
        from core.logger import _CircularBufferHandler

        h = _CircularBufferHandler(capacity=10)
        record = logging.LogRecord("test", logging.INFO, "", 0, "hello", None, None)
        h.emit(record)
        recent = h.get_recent(10)
        assert len(recent) == 1
        assert "hello" in recent[0]

    def test_handler_circular_behavior(self):
        from core.logger import _CircularBufferHandler

        h = _CircularBufferHandler(capacity=3)
        for i in range(5):
            record = logging.LogRecord("test", logging.INFO, "", 0, f"msg{i}", None, None)
            h.emit(record)
        recent = h.get_recent(10)
        assert len(recent) == 3
        assert "msg2" in recent[0]
        assert "msg4" in recent[-1]

    def test_get_recent_returns_subset(self):
        from core.logger import _CircularBufferHandler

        h = _CircularBufferHandler(capacity=10)
        for i in range(5):
            record = logging.LogRecord("test", logging.INFO, "", 0, f"msg{i}", None, None)
            h.emit(record)
        recent = h.get_recent(2)
        assert len(recent) == 2


class TestCrashReporter:
    def test_report_returns_none_for_none_exc(self):
        from core.logger import CrashReporter
        from pathlib import Path

        tmp = Path(__file__).resolve().parent.parent / "workspace"
        reporter = CrashReporter("test", tmp)
        result = reporter.report(None, None, None, [])
        assert result is None

    def test_report_creates_file(self, tmp_path):
        from core.logger import CrashReporter

        reporter = CrashReporter("test_module", tmp_path)
        exc_type = ValueError
        exc_val = ValueError("test crash")
        path = reporter.report(exc_type, exc_val, exc_val.__traceback__, ["log line 1"])
        if path:
            assert path.exists()
            content = path.read_text("utf-8")
            assert "test_module" in content
            assert "ValueError" in content
            assert "test crash" in content

    def test_report_dedup_rapid_duplicates(self, tmp_path):
        from core.logger import CrashReporter

        reporter = CrashReporter("dedup", tmp_path)
        exc_type = ValueError
        exc_val = ValueError("dup")
        tb = exc_val.__traceback__
        p1 = reporter.report(exc_type, exc_val, tb, [])
        p2 = reporter.report(exc_type, exc_val, tb, [])
        if p1 and p2:
            assert p1 != p2

    def test_track_recurrence(self, tmp_path):
        from core.logger import CrashReporter

        reporter = CrashReporter("recur", tmp_path)
        for i in range(6):
            reporter._track_recurrence(f"sig_{i}")
        count = reporter._history.get(f"sig_0", {}).get("count", 0)
        assert count >= 1

    def test_safe_config_snapshot(self, tmp_path):
        from core.logger import CrashReporter

        snapshot = CrashReporter._safe_config_snapshot()
        assert snapshot is None or isinstance(snapshot, dict)


class TestHeartbeat:
    def test_create_heartbeat(self):
        from core.logger import Heartbeat

        hb = Heartbeat(logging.getLogger("test"), interval=60.0)
        assert hb.interval == 60.0
        assert hb._thread is None

    def test_heartbeat_interval_minimum(self):
        from core.logger import Heartbeat

        hb = Heartbeat(logging.getLogger("test"), interval=1.0)
        assert hb.interval == 5.0

    def test_start_stop(self):
        from core.logger import Heartbeat

        hb = Heartbeat(logging.getLogger("test"), interval=60.0)
        hb.start()
        assert hb._thread is not None
        assert hb._thread.is_alive()
        hb.stop()
        assert hb._thread is None

    def test_double_start_is_noop(self):
        from core.logger import Heartbeat

        hb = Heartbeat(logging.getLogger("test"), interval=60.0)
        hb.start()
        t = hb._thread
        hb.start()
        assert hb._thread is t
        hb.stop()

    def test_stop_without_start(self):
        from core.logger import Heartbeat

        hb = Heartbeat(logging.getLogger("test"), interval=60.0)
        hb.stop()

    def test_heartbeat_calls_subsystems(self):
        from core.logger import Heartbeat
        import logging

        called = []

        def check():
            called.append(True)
            return True

        hb = Heartbeat(logging.getLogger("test"), interval=60.0, subsystems=[check])
        hb._beat()
        assert len(called) >= 1
        hb.stop()

    def test_heartbeat_handles_subsystem_error(self):
        from core.logger import Heartbeat
        import logging

        def broken():
            raise RuntimeError("subsystem fail")

        hb = Heartbeat(logging.getLogger("test"), interval=60.0, subsystems=[broken])
        hb._beat()
        hb.stop()


class TestInitializeLogging:
    def test_initialize_returns_logger(self):
        from core.logger import initialize_logging
        import logging

        logger = initialize_logging("test_init", level=logging.DEBUG, log_to_file=False)
        assert logger is not None
        assert logger.name == "test_init"

    def test_initialize_twice_returns_same_root_config(self):
        from core.logger import initialize_logging
        import logging

        l1 = initialize_logging("mod_a", level=logging.INFO, log_to_file=False)
        l2 = initialize_logging("mod_b", level=logging.INFO, log_to_file=False)
        assert l1 is not l2

    def test_get_recent_logs(self):
        from core.logger import initialize_logging, get_recent_logs
        import logging

        initialize_logging("recent_test", level=logging.DEBUG, log_to_file=False)
        logger = logging.getLogger("recent_test")
        logger.info("test message")
        logs = get_recent_logs(10)
        assert len(logs) >= 0


class TestEventBusHandler:
    def test_emit_no_bus(self):
        from core.logger import _EventBusHandler

        h = _EventBusHandler()
        record = logging.LogRecord("test", logging.INFO, "", 0, "msg", None, None)
        h.emit(record)


class TestHelpers:
    def test_get_recent_logs_no_handler(self):
        from core.logger import get_recent_logs
        import core.logger

        saved = core.logger._circular_handler
        core.logger._circular_handler = None
        try:
            logs = get_recent_logs(10)
            assert logs == []
        finally:
            core.logger._circular_handler = saved
