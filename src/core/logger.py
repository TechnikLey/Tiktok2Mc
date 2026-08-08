"""Unified logging and crash reporting system for TikTok2MC.

Provides:
- Consistent logging across all Python modules
- Structured crash report generation
- Global exception hook (sys.excepthook + threading.excepthook)
- Periodic heartbeat logging for long-running processes
- Non-blocking / asynchronous file logging via QueueHandler
- Recurrence pattern tracking for frequent crashes
- Integration with ``CrashManager`` and ``HealthMonitor``

Usage:
    from core.logger import initialize_logging, install_global_exception_hook, start_heartbeat

    log = initialize_logging(__name__)
    install_global_exception_hook("my_module")
    hb = start_heartbeat(log, interval=60.0)
"""
from __future__ import annotations

import asyncio
import atexit
import json
import logging
import logging.handlers
import os
import platform
import queue
import sys
import threading
import time
import traceback
from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar

# Optional psutil for memory diagnostics
try:
    import psutil

    _PSUTIL_AVAILABLE = True
except ImportError:
    _PSUTIL_AVAILABLE = False

# Lazy imports for integration — imported inside functions to avoid cycles
_CRASH_MANAGER: Any = None
_CRASH_MANAGER_LOCK = threading.Lock()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_LOG_FORMAT = "%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
_LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_CIRCULAR_BUFFER_SIZE = 500
_DEFAULT_HEARTBEAT_INTERVAL = 60.0
_CRASH_DEDUP_SECONDS = 2.0
_CRASH_HISTORY_WINDOW = 600  # 10 minutes for recurrence warnings

# ---------------------------------------------------------------------------
# Circular log buffer (kept in memory for crash reports)
# ---------------------------------------------------------------------------


class _CircularBufferHandler(logging.Handler):
    """Keeps the last N formatted log records in memory."""

    def __init__(self, capacity: int = _CIRCULAR_BUFFER_SIZE) -> None:
        super().__init__()
        self._buffer: deque[str] = deque(maxlen=capacity)
        self._formatter = logging.Formatter(_LOG_FORMAT, _LOG_DATE_FORMAT)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._buffer.append(self._formatter.format(record))
        except Exception:  # a logging handler must never raise
            self.handleError(record)

    def get_recent(self, count: int = 100) -> list[str]:
        return list(self._buffer)[-count:]


# Global reference so we can retrieve recent logs without scanning root handlers
_circular_handler: _CircularBufferHandler | None = None

# ---------------------------------------------------------------------------
# Crash Reporter
# ---------------------------------------------------------------------------


class CrashReporter:
    """Generates structured JSON crash reports and tracks recurrence."""

    _history: ClassVar[dict[str, dict[str, Any]]] = {}
    _history_lock = threading.Lock()

    def __init__(self, module_name: str, log_dir: Path) -> None:
        self.module_name = module_name
        self.crash_dir = log_dir / "crash_reports"
        self.crash_dir.mkdir(parents=True, exist_ok=True)
        self._last_signature: str | None = None
        self._last_time: float = 0.0

    @staticmethod
    def _safe_config_snapshot() -> dict[str, Any] | None:
        """Attempt to load the active config without crashing."""
        try:
            from core.paths import get_config_file
            from core.utils import load_config

            cfg_path = get_config_file()
            if cfg_path.exists():
                return load_config(cfg_path)
        except Exception:  # snapshot is best-effort — must never crash the reporter
            pass
        return None

    def _generate_filename(self) -> Path:
        timestamp = datetime.now(tz=UTC).strftime("%Y%m%d_%H%M%S_%f")
        return self.crash_dir / f"crash_{timestamp}_{self.module_name}.json"

    def _track_recurrence(self, signature: str) -> bool:
        """Return True if we should warn about a recurring crash."""
        with self._history_lock:
            now = time.time()
            entry = self._history.get(signature)
            if entry is None:
                self._history[signature] = {
                    "count": 1,
                    "first_seen": now,
                    "last_seen": now,
                }
                return False
            entry["count"] += 1
            entry["last_seen"] = now
            # Warn every 5 occurrences within the history window
            return entry["count"] % 5 == 0 and (now - entry["first_seen"]) < _CRASH_HISTORY_WINDOW

    def report(
        self,
        exc_type: type | None,
        exc_value: BaseException | None,
        exc_tb: Any | None,
        recent_logs: list[str],
    ) -> Path | None:
        """Write a crash report file. Returns the path or None on failure."""
        if exc_type is None or exc_value is None:
            return None

        signature = f"{self.module_name}:{exc_type.__name__}:{str(exc_value)[:80]}"

        # Dedup rapid duplicate reports
        now = time.time()
        if signature == self._last_signature and (now - self._last_time) < _CRASH_DEDUP_SECONDS:
            return None
        self._last_signature = signature
        self._last_time = now

        stack = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))

        payload: dict[str, Any] = {
            "timestamp": datetime.now(tz=UTC).isoformat(),
            "module": self.module_name,
            "python_version": sys.version,
            "platform": platform.platform(),
            "os": os.name,
            "cwd": str(Path.cwd()),
            "exception_type": exc_type.__name__,
            "exception_message": str(exc_value),
            "stack_trace": stack,
            "config_snapshot": self._safe_config_snapshot(),
            "recent_logs": recent_logs,
        }

        path = self._generate_filename()

        def _write() -> None:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2, ensure_ascii=False, default=str)
            except (OSError, TypeError):
                pass

        # Write in a daemon thread so we never block shutdown
        t = threading.Thread(target=_write, daemon=True)
        t.start()
        t.join(timeout=3.0)

        # Recurrence warning
        if self._track_recurrence(signature):
            with self._history_lock:
                count = self._history[signature]["count"]
            logging.getLogger("crash_reporter").warning(
                "Recurring crash in '%s': %s occurred %d times.",
                self.module_name,
                exc_type.__name__,
                count,
            )

        return path


# ---------------------------------------------------------------------------
# Heartbeat
# ---------------------------------------------------------------------------


class Heartbeat:
    """Periodic heartbeat for long-running processes."""

    def __init__(
        self,
        logger: logging.Logger,
        interval: float = _DEFAULT_HEARTBEAT_INTERVAL,
        subsystems: list[Callable[[], bool]] | None = None,
    ) -> None:
        self.logger = logger
        self.interval = max(interval, 5.0)
        self.subsystems = subsystems or []
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def _memory_snapshot(self) -> dict[str, Any] | None:
        if not _PSUTIL_AVAILABLE:
            return None
        try:
            proc = psutil.Process()
            mem = proc.memory_info()
            return {
                "rss_mb": round(mem.rss / (1024 * 1024), 2),
                "vms_mb": round(mem.vms / (1024 * 1024), 2),
                "percent": round(proc.memory_percent(), 2),
            }
        except Exception:  # memory snapshot is best-effort
            return None

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            self._beat()
            self._stop_event.wait(self.interval)

    def _beat(self) -> None:
        try:
            parts = ["heartbeat", "status=alive"]
            for i, check in enumerate(self.subsystems):
                try:
                    ok = "ok" if check() else "fail"
                except Exception:  # a broken subsystem check must not break the heartbeat
                    ok = "error"
                parts.append(f"subsystem_{i}={ok}")

            mem = self._memory_snapshot()
            if mem:
                parts.append(f"memory_rss={mem['rss_mb']}MB")
                parts.append(f"memory_percent={mem['percent']}%")

            self.logger.info(" | ".join(parts))

            # Report heartbeat to health monitor
            try:
                from core.health_monitor import get_health_monitor
                hm = get_health_monitor()
                hm.record_heartbeat("process." + (self.logger.name or "unknown"))
            except Exception:  # heartbeat reporting is best-effort
                pass

        except Exception as exc:  # the heartbeat loop must never die
            self.logger.debug("Heartbeat error: %s", exc)

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="Heartbeat")
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None


# ---------------------------------------------------------------------------
# EventBus log publisher (lightweight, non-blocking)
# ---------------------------------------------------------------------------

class _EventBusHandler(logging.Handler):
    """Publish log records to the central EventBus as ``log.unified`` events.

    This is a *best-effort* handler: if the event bus is not available or
    the queue is full the record is silently dropped so logging never blocks
    the application.
    """

    def __init__(self) -> None:
        super().__init__()
        self._event_bus: Any = None
        self._lock = threading.Lock()

    def _get_bus(self) -> Any:
        if self._event_bus is not None:
            return self._event_bus
        with self._lock:
            if self._event_bus is not None:
                return self._event_bus
            try:
                from core.api.eventbus import event_bus

                self._event_bus = event_bus
            except Exception:  # event bus is optional; logging must never block
                pass
        return self._event_bus

    def emit(self, record: logging.LogRecord) -> None:
        bus = self._get_bus()
        if bus is None:
            return
        try:
            # Use the running loop if available, otherwise fire-and-forget
            loop = asyncio.get_running_loop()
            loop.call_soon_threadsafe(
                lambda: asyncio.create_task(
                    bus.publish(
                        "log.unified",
                        {
                            "level": record.levelname.lower(),
                            "name": record.name,
                            "message": self.format(record),
                            "raw": record.getMessage(),
                            "timestamp": record.created,
                        },
                    )
                )
            )
        except RuntimeError:
            # No running loop — best-effort sync publish (should not happen
            # in normal asyncio apps but keeps the handler safe everywhere).
            pass
        except Exception:  # a logging handler must never raise
            self.handleError(record)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_log_dir() -> Path:
    from core.paths import get_root_dir

    return (get_root_dir() / "logs").resolve()


def _stop_queue_listener(listener: logging.handlers.QueueListener | None) -> None:
    if listener is not None:
        try:
            listener.stop()
        except Exception:  # shutdown must never raise
            pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def initialize_logging(
    module_name: str,
    level: int = logging.INFO,
    log_to_file: bool = True,
) -> logging.Logger:
    """Initialize unified logging for a process entry point.

    Returns a logger configured for *module_name*.  Console output is
    immediate; file writes are asynchronous via QueueHandler so the
    application never blocks on disk I/O.
    """
    global _circular_handler

    root = logging.getLogger()
    already_initialized = getattr(root, "_unified_logging_initialized", False)

    formatter = logging.Formatter(_LOG_FORMAT, _LOG_DATE_FORMAT)

    if not already_initialized:
        root.setLevel(logging.DEBUG)
        root._unified_logging_initialized = True  # type: ignore[attr-defined]

        # Console -> stdout (immediate)
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(formatter)
        ch.setLevel(level)
        root.addHandler(ch)

        # Circular buffer (all modules)
        _circular_handler = _CircularBufferHandler()
        _circular_handler.setLevel(logging.DEBUG)
        root.addHandler(_circular_handler)

        # EventBus publisher for live GUI streaming
        _eb_handler = _EventBusHandler()
        _eb_handler.setLevel(logging.DEBUG)
        root.addHandler(_eb_handler)

        # Async unified log file (all modules)
        if log_to_file:
            log_dir = _get_log_dir()
            log_dir.mkdir(parents=True, exist_ok=True)

            q: queue.Queue[logging.LogRecord] = queue.Queue(-1)
            qh = logging.handlers.QueueHandler(q)
            qh.setLevel(logging.DEBUG)
            root.addHandler(qh)

            unified_path = log_dir / "unified.log"
            fh = logging.FileHandler(unified_path, encoding="utf-8")
            fh.setFormatter(formatter)
            fh.setLevel(logging.DEBUG)

            listener = logging.handlers.QueueListener(q, fh, respect_handler_level=True)
            listener.start()
            atexit.register(lambda: _stop_queue_listener(listener))

    # Module-specific logger
    logger = logging.getLogger(module_name)
    logger.setLevel(level)

    # Per-module file (direct, not queued — low volume, easy to grep)
    if log_to_file and not already_initialized:
        log_dir = _get_log_dir()
        module_fh = logging.FileHandler(log_dir / f"{module_name}.log", encoding="utf-8")
        module_fh.setFormatter(formatter)
        module_fh.setLevel(level)
        logger.addHandler(module_fh)

    if not already_initialized:
        logger.info("Unified logging initialized for '%s' at level %s", module_name, logging.getLevelName(level))

    return logger


def get_recent_logs(count: int = 100) -> list[str]:
    """Retrieve recent log lines from the circular buffer."""
    if _circular_handler is not None:
        return _circular_handler.get_recent(count)
    return []


def install_global_exception_hook(module_name: str) -> None:
    """Install sys.excepthook and (when available) threading.excepthook
    so every uncaught exception produces a crash report.
    """
    log_dir = _get_log_dir()
    reporter = CrashReporter(module_name, log_dir)

    # --- sys.excepthook ---
    original_sys_excepthook = sys.excepthook

    def _sys_excepthook(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            original_sys_excepthook(exc_type, exc_value, exc_tb)
            return

        logger = logging.getLogger(module_name)
        logger.critical(
            "Unhandled exception: %s: %s",
            exc_type.__name__,
            exc_value,
            exc_info=(exc_type, exc_value, exc_tb),
        )
        path = reporter.report(exc_type, exc_value, exc_tb, get_recent_logs(200))
        if path:
            logger.critical("Crash report written to: %s", path)
        original_sys_excepthook(exc_type, exc_value, exc_tb)

    sys.excepthook = _sys_excepthook

    # --- threading.excepthook (Python 3.8+) ---
    if hasattr(threading, "excepthook"):
        original_threading_excepthook = threading.excepthook  # type: ignore[attr-defined]

        def _threading_excepthook(args):
            logger = logging.getLogger(module_name)
            logger.critical(
                "Unhandled exception in thread '%s': %s: %s",
                args.thread.name,
                args.exc_type.__name__ if args.exc_type else "Unknown",
                args.exc_value,
                exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
            )
            path = reporter.report(
                args.exc_type, args.exc_value, args.exc_traceback, get_recent_logs(200)
            )
            if path:
                logger.critical("Crash report written to: %s", path)
            original_threading_excepthook(args)

        threading.excepthook = _threading_excepthook  # type: ignore[attr-defined]


def handle_unhandled_exception(module_name: str) -> None:
    """Generate a crash report for the *current* exception.

    Intended to be called inside an ``except`` block at the highest
    execution level so the process can exit gracefully after reporting.
    """
    exc_type, exc_value, exc_tb = sys.exc_info()
    if exc_type is None or issubclass(exc_type, KeyboardInterrupt):
        return

    logger = logging.getLogger(module_name)
    logger.critical(
        "Unhandled exception: %s: %s",
        exc_type.__name__,
        exc_value,
        exc_info=(exc_type, exc_value, exc_tb),
    )

    reporter = CrashReporter(module_name, _get_log_dir())
    path = reporter.report(exc_type, exc_value, exc_tb, get_recent_logs(200))
    if path:
        logger.critical("Crash report saved to: %s", path)


def start_heartbeat(
    logger: logging.Logger,
    interval: float = _DEFAULT_HEARTBEAT_INTERVAL,
    subsystems: list[Callable[[], bool]] | None = None,
) -> Heartbeat:
    """Start a periodic heartbeat for the current process."""
    hb = Heartbeat(logger, interval=interval, subsystems=subsystems)
    hb.start()
    return hb


# Legacy compatibility wrappers (kept so existing code does not break)
configure_root_logger = initialize_logging
setup_logger = initialize_logging
