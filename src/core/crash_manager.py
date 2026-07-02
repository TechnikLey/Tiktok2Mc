"""Centralized crash management for TikTok2Mc.

Captures and classifies all types of exceptions:
- Main thread exceptions
- Worker thread exceptions
- asyncio task exceptions
- Future exceptions
- Plugin crashes
- API crashes

Every crash is assigned an error code, logged with structured context,
preserves stack traces, and notifies the health monitor.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import threading
import time
import traceback
from concurrent.futures import Future
from typing import Any, Callable, Optional

from core.error_codes import (
    CORE_0001,
    CORE_0002,
    CORE_0004,
    ErrorCode,
    ErrorInstance,
    Severity,
    Subsystem,
    get_error_code,
)
from core.health_monitor import get_health_monitor, HealthState

log = logging.getLogger(__name__)


class CrashManager:
    """Central manager for crash detection, classification, and reporting.

    Installs hooks into:
    - sys.excepthook
    - threading.excepthook
    - asyncio loop exception handler
    - Future add_done_callback for unhandled exceptions

    Usage:
        crash_mgr = CrashManager("my_module")
        crash_mgr.install()

    Then use the helper methods to report specific failures.
    """

    def __init__(self, module_name: str) -> None:
        self.module_name = module_name
        self._health = get_health_monitor()
        self._crash_count: int = 0
        self._last_crashes: list[dict[str, Any]] = []
        self._max_history: int = 50
        self._installed = False

    # ------------------------------------------------------------------
    # Installation
    # ------------------------------------------------------------------

    def install(self) -> None:
        """Install all exception hooks.

        Safe to call multiple times — only installs once.
        """
        if self._installed:
            return
        self._installed = True

        self._install_sys_excepthook()
        self._install_threading_excepthook()
        log.info("[CRASH] CrashManager installed for '%s'", self.module_name)

    def install_asyncio(self, loop: asyncio.AbstractEventLoop) -> None:
        """Install the asyncio exception handler on the given loop."""
        original_handler = loop.get_exception_handler()

        def _handle_exception(loop: asyncio.AbstractEventLoop, context: dict[str, Any]) -> None:
            exc = context.get("exception")
            message = context.get("message", "Unknown asyncio error")
            future = context.get("future")

            if exc is not None:
                self.report_exception(
                    error_code=CORE_0001,
                    exc=exc,
                    context_info={
                        "message": message,
                        "source": "asyncio",
                        "future": str(future) if future else None,
                    },
                )
            else:
                log.error("[CRASH] asyncio error: %s", message)

            if original_handler:
                original_handler(loop, context)

        loop.set_exception_handler(_handle_exception)
        log.info("[CRASH] asyncio exception handler installed")

    # ------------------------------------------------------------------
    # Internal hooks
    # ------------------------------------------------------------------

    def _install_sys_excepthook(self) -> None:
        original = sys.excepthook

        def _hook(exc_type, exc_value, exc_tb):
            if issubclass(exc_type, KeyboardInterrupt):
                original(exc_type, exc_value, exc_tb)
                return
            self.report_exception(
                error_code=CORE_0001,
                exc=exc_value,
                exc_type=exc_type,
                exc_tb=exc_tb,
                context_info={"source": "sys.excepthook"},
            )
            original(exc_type, exc_value, exc_tb)

        sys.excepthook = _hook

    def _install_threading_excepthook(self) -> None:
        if not hasattr(threading, "excepthook"):
            return
        original = threading.excepthook

        def _hook(args):
            logger = log.getChild("threading")
            name = args.thread.name if args.thread else "unknown"
            exc_type = args.exc_type or type(Exception)
            exc_value = args.exc_value or Exception("Unknown thread exception")
            exc_tb = args.exc_traceback

            logger.critical(
                "Unhandled exception in thread '%s': %s: %s",
                name, exc_type.__name__, exc_value,
                exc_info=(exc_type, exc_value, exc_tb),
            )
            self.report_exception(
                error_code=CORE_0002,
                exc=exc_value,
                exc_type=exc_type,
                exc_tb=exc_tb,
                context_info={"source": "threading.excepthook", "thread_name": name},
            )
            original(args)

        threading.excepthook = _hook

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def report_exception(
        self,
        error_code: ErrorCode,
        exc: BaseException,
        exc_type: Optional[type] = None,
        exc_tb: Optional[Any] = None,
        context_info: Optional[dict[str, Any]] = None,
    ) -> ErrorInstance:
        """Report an exception with a structured error code.

        Returns the ErrorInstance for further use.
        """
        self._crash_count += 1
        exc_type = exc_type or type(exc)
        exc_tb = exc_tb or getattr(exc, "__traceback__", None)

        stack = "".join(traceback.format_exception(exc_type, exc, exc_tb)) if exc_tb else str(exc)

        instance = error_code.with_context(
            module=self.module_name,
            **(context_info or {}),
        )
        instance.root_exception = exc
        instance.timestamp = time.time()

        # Log the error with full context
        severity_name = error_code.severity.label()
        log.log(
            _severity_to_logging_level(error_code.severity),
            "[%s] %s\n%s\nImpact: %s\nRecovery: %s\nStack:\n%s",
            error_code.code,
            error_code.message,
            str(exc),
            error_code.impact,
            error_code.recovery_hint,
            stack,
        )

        # Update health monitor
        self._health.record_error(self.module_name, f"{error_code.code}: {error_code.message}: {exc}")

        # Record to history
        crash_record = {
            "timestamp": instance.timestamp,
            "code": error_code.code,
            "severity": severity_name,
            "module": self.module_name,
            "exception": f"{exc_type.__name__}: {exc}",
            "context": context_info,
            "stack": stack[:2000],
        }
        self._last_crashes.append(crash_record)
        if len(self._last_crashes) > self._max_history:
            self._last_crashes.pop(0)

        return instance

    def report_error(
        self,
        error_code: ErrorCode,
        detail: str = "",
        context_info: Optional[dict[str, Any]] = None,
    ) -> ErrorInstance:
        """Report a non-exception error with a structured error code."""
        instance = error_code.with_context(
            module=self.module_name,
            detail=detail,
            **(context_info or {}),
        )
        instance.timestamp = time.time()

        severity_name = error_code.severity.label()
        log.log(
            _severity_to_logging_level(error_code.severity),
            "[%s] %s\n%s\nImpact: %s\nRecovery: %s",
            error_code.code,
            error_code.message,
            detail or "",
            error_code.impact,
            error_code.recovery_hint,
        )

        # Update health monitor
        full_msg = f"{error_code.code}: {error_code.message}"
        if detail:
            full_msg += f" - {detail}"
        self._health.record_error(self.module_name, full_msg)

        crash_record = {
            "timestamp": instance.timestamp,
            "code": error_code.code,
            "severity": severity_name,
            "module": self.module_name,
            "detail": detail,
            "context": context_info,
        }
        self._last_crashes.append(crash_record)
        if len(self._last_crashes) > self._max_history:
            self._last_crashes.pop(0)

        return instance

    # ------------------------------------------------------------------
    # asyncio / Future helpers
    # ------------------------------------------------------------------

    def observe_task(self, task: asyncio.Task, component: str = "") -> None:
        """Add a done callback to an asyncio Task that reports unhandled exceptions."""

        def _on_done(t: asyncio.Task) -> None:
            if t.cancelled():
                return
            exc = t.exception()
            if exc is not None:
                self.report_exception(
                    error_code=CORE_0001,
                    exc=exc,
                    context_info={
                        "source": "asyncio.Task",
                        "task_name": t.get_name(),
                        "component": component or self.module_name,
                    },
                )

        task.add_done_callback(_on_done)

    def observe_future(self, future: Future, component: str = "") -> None:
        """Add a done callback to a concurrent.futures.Future."""

        def _on_done(f: Future) -> None:
            if f.cancelled():
                return
            exc = f.exception()
            if exc is not None:
                self.report_exception(
                    error_code=CORE_0002,
                    exc=exc,
                    context_info={
                        "source": "concurrent.futures",
                        "component": component or self.module_name,
                    },
                )

        future.add_done_callback(_on_done)

    # ------------------------------------------------------------------
    # Worker wrappers
    # ------------------------------------------------------------------

    def supervised_thread(self, target: Callable, name: str = "", daemon: bool = False) -> threading.Thread:
        """Create a thread that catches and reports all exceptions.

        The thread is wrapped so any unhandled exception is caught and
        reported via the crash manager before propagating.
        """

        def _wrapped() -> None:
            try:
                target()
            except Exception as exc:
                self.report_exception(
                    error_code=CORE_0002,
                    exc=exc,
                    context_info={"source": "supervised_thread", "thread_name": name or target.__name__},
                )
                raise

        thread_name = name or target.__name__
        t = threading.Thread(target=_wrapped, name=thread_name, daemon=daemon)
        return t

    async def supervised_async_task(self, coro, name: str = "") -> Any:
        """Run an async function and report any unhandled exception."""
        try:
            return await coro
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.report_exception(
                error_code=CORE_0001,
                exc=exc,
                context_info={"source": "supervised_async_task", "task_name": name},
            )
            raise

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_crash_history(self) -> list[dict[str, Any]]:
        return list(self._last_crashes)

    def get_crash_count(self) -> int:
        return self._crash_count

    def get_stats(self) -> dict[str, Any]:
        return {
            "module": self.module_name,
            "crash_count": self._crash_count,
            "history_size": len(self._last_crashes),
        }


# ------------------------------------------------------------------
# Module-level singleton
# ------------------------------------------------------------------

_crash_manager: CrashManager | None = None
_crash_manager_lock = threading.Lock()


def get_crash_manager() -> CrashManager:
    """Return the global ``CrashManager``, creating it on first call."""
    global _crash_manager
    if _crash_manager is None:
        with _crash_manager_lock:
            if _crash_manager is None:
                _crash_manager = CrashManager("global")
    return _crash_manager


def _severity_to_logging_level(severity: Severity) -> int:
    import logging
    mapping = {
        Severity.DEBUG: logging.DEBUG,
        Severity.INFO: logging.INFO,
        Severity.NOTICE: logging.INFO,
        Severity.WARNING: logging.WARNING,
        Severity.ERROR: logging.ERROR,
        Severity.CRITICAL: logging.CRITICAL,
        Severity.FATAL: logging.CRITICAL,
    }
    return mapping.get(severity, logging.WARNING)
