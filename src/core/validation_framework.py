"""Validation framework for TikTok2Mc.

Provides structured validation for:
- Startup validation
- Shutdown validation
- Runtime validation
- Operation timeouts

Every validation step produces a clear result that can be logged,
surfaced to the user, and assigned an error code.
"""

from __future__ import annotations

import asyncio
import logging
import os
import socket
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.error_codes import (
    CONFIG_0001,
    CORE_0004,
    STARTUP_0003,
    ErrorCode,
    Severity,
)
from core.health_monitor import HealthState
from core.utils import normalize_config_version
from core.version import EXPECTED_CONFIG_VERSION

log = logging.getLogger(__name__)


# ==============================================================================
# Validation result types
# ==============================================================================


@dataclass
class ValidationResult:
    """Result of a single validation step."""

    name: str
    passed: bool
    message: str = ""
    error_code: ErrorCode | None = None
    severity: Severity = Severity.WARNING
    detail: str = ""

    def format(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        msg = f"[{status}] {self.name}"
        if self.message:
            msg += f": {self.message}"
        if self.error_code:
            msg = f"[{self.error_code.code}] {msg}"
        return msg

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "message": self.message,
            "error_code": self.error_code.code if self.error_code else None,
            "severity": self.severity.label(),
        }


@dataclass
class ValidationSuite:
    """A collection of related validation steps."""

    name: str
    description: str = ""
    steps: list[ValidationResult] = field(default_factory=list)
    _stop_on_failure: bool = False

    def add(self, result: ValidationResult) -> None:
        self.steps.append(result)

    def all_passed(self) -> bool:
        return all(s.passed for s in self.steps)

    def failures(self) -> list[ValidationResult]:
        return [s for s in self.steps if not s.passed]

    def warnings(self) -> list[ValidationResult]:
        return [s for s in self.steps if s.passed and s.severity >= Severity.WARNING]

    def critical_failures(self) -> list[ValidationResult]:
        return [s for s in self.steps if not s.passed and s.severity >= Severity.ERROR]

    def summary(self) -> str:
        total = len(self.steps)
        passed = sum(1 for s in self.steps if s.passed)
        failed = total - passed
        lines = [
            f"[VALIDATION] {self.name}: {passed}/{total} passed, {failed} failed",
        ]
        for s in self.steps:
            lines.append(f"  {s.format()}")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "total": len(self.steps),
            "passed": sum(1 for s in self.steps if s.passed),
            "failed": sum(1 for s in self.steps if not s.passed),
            "steps": [s.to_dict() for s in self.steps],
        }


# ==============================================================================
# Timeout helpers
# ==============================================================================


@dataclass
class TimeoutResult:
    """Result of a timed operation."""

    success: bool
    result: Any = None
    elapsed: float = 0.0
    timed_out: bool = False
    error: str | None = None


async def run_with_timeout(
    coro, timeout: float, label: str = "operation"
) -> TimeoutResult:
    """Run an async operation with a timeout.

    If the timeout expires, a CORE-0004 error is logged and the
    result indicates timeout.
    """
    start = time.time()
    try:
        result = await asyncio.wait_for(coro, timeout=timeout)
        elapsed = time.time() - start
        return TimeoutResult(success=True, result=result, elapsed=elapsed)
    except asyncio.TimeoutError:
        elapsed = time.time() - start
        log.warning(
            "[CORE-0004] Operation '%s' timed out after %.1fs (timeout=%.1fs)",
            label,
            elapsed,
            timeout,
        )
        return TimeoutResult(
            success=False,
            timed_out=True,
            elapsed=elapsed,
            error=f"Timed out after {elapsed:.1f}s (limit {timeout:.1f}s)",
        )
    except Exception as exc:  # framework purpose: capture any failure from wrapped op
        elapsed = time.time() - start
        return TimeoutResult(success=False, elapsed=elapsed, error=str(exc))


def run_with_timeout_sync(
    func, timeout: float, label: str = "operation"
) -> TimeoutResult:
    """Run a synchronous operation with a timeout via threading."""
    start = time.time()
    result_container: list[Any] = []
    error_container: list[Exception | None] = [None]

    def _target():
        try:
            result_container.append(func())
        except Exception as e:  # framework purpose: capture any failure from wrapped op
            error_container[0] = e

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    t.join(timeout=timeout)

    elapsed = time.time() - start

    if t.is_alive():
        return TimeoutResult(
            success=False,
            timed_out=True,
            elapsed=elapsed,
            error=f"Timed out after {elapsed:.1f}s (limit {timeout:.1f}s)",
        )

    if error_container[0] is not None:
        return TimeoutResult(
            success=False, elapsed=elapsed, error=str(error_container[0])
        )

    return TimeoutResult(
        success=True,
        result=result_container[0] if result_container else None,
        elapsed=elapsed,
    )


# ==============================================================================
# Startup validation
# ==============================================================================


def validate_config_exists(config_path: Path) -> ValidationResult:
    """Validate that the main config file exists and is readable."""
    if not config_path.exists():
        return ValidationResult(
            name="Config file exists",
            passed=False,
            message=f"Config file not found at {config_path}",
            error_code=CONFIG_0001,
            severity=Severity.FATAL,
        )
    if not os.access(str(config_path), os.R_OK):
        return ValidationResult(
            name="Config file readable",
            passed=False,
            message=f"Config file at {config_path} is not readable",
            error_code=CONFIG_0001,
            severity=Severity.FATAL,
        )
    return ValidationResult(
        name="Config file exists",
        passed=True,
        message=f"Config found at {config_path}",
    )


def validate_directory(path: Path, name: str, create: bool = False) -> ValidationResult:
    """Validate that a directory exists and is accessible."""
    if create and not path.exists():
        try:
            path.mkdir(parents=True, exist_ok=True)
            return ValidationResult(
                name=f"Directory '{name}' exists",
                passed=True,
                message=f"Created {path}",
            )
        except OSError as exc:
            return ValidationResult(
                name=f"Directory '{name}' exists",
                passed=False,
                message=f"Cannot create {path}: {exc}",
                severity=Severity.ERROR,
            )
    if not path.exists():
        return ValidationResult(
            name=f"Directory '{name}' exists",
            passed=False,
            message=f"Directory not found: {path}",
            severity=Severity.ERROR,
        )
    if not path.is_dir():
        return ValidationResult(
            name=f"Directory '{name}' exists",
            passed=False,
            message=f"Path exists but is not a directory: {path}",
            severity=Severity.ERROR,
        )
    return ValidationResult(
        name=f"Directory '{name}' exists",
        passed=True,
    )


def validate_file(path: Path, name: str) -> ValidationResult:
    """Validate that a file exists."""
    if not path.exists():
        return ValidationResult(
            name=f"File '{name}' exists",
            passed=False,
            message=f"File not found: {path}",
            severity=Severity.ERROR,
        )
    return ValidationResult(
        name=f"File '{name}' exists",
        passed=True,
    )


def validate_port_free(host: str, port: int, description: str) -> ValidationResult:
    """Validate that a port is free to bind."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((host, port))
        return ValidationResult(
            name=f"Port {port} ({description})",
            passed=True,
        )
    except OSError:
        return ValidationResult(
            name=f"Port {port} ({description})",
            passed=False,
            message=f"Port {port} is already in use",
            error_code=STARTUP_0003,
            severity=Severity.ERROR,
        )


def validate_executable(path: Path, name: str) -> ValidationResult:
    """Validate that an executable exists and is runnable."""
    if not path.exists():
        return ValidationResult(
            name=f"Executable '{name}'",
            passed=False,
            message=f"Not found at {path}",
            severity=Severity.ERROR,
        )
    if not os.access(str(path), os.X_OK) and sys.platform != "win32":
        return ValidationResult(
            name=f"Executable '{name}'",
            passed=False,
            message=f"Not executable: {path}",
            severity=Severity.ERROR,
        )
    return ValidationResult(
        name=f"Executable '{name}'",
        passed=True,
    )


def run_startup_validation(
    config_path: Path | None = None,
    required_dirs: list[tuple[Path, str, bool]] | None = None,
    required_files: list[tuple[Path, str]] | None = None,
    required_ports: list[tuple[str, int, str]] | None = None,
    required_executables: list[tuple[Path, str]] | None = None,
) -> ValidationSuite:
    """Run a comprehensive startup validation suite.

    Returns a ValidationSuite with all results. The caller should
    check critical_failures() and determine if startup should proceed.
    """
    suite = ValidationSuite(
        name="Startup Validation",
        description="Validates system readiness before starting",
    )

    if config_path is not None:
        suite.add(validate_config_exists(config_path))

    if required_dirs:
        for path, name, create in required_dirs:
            suite.add(validate_directory(path, name, create=create))

    if required_files:
        for path, name in required_files:
            suite.add(validate_file(path, name))

    if required_ports:
        for host, port, desc in required_ports:
            suite.add(validate_port_free(host, port, desc))

    if required_executables:
        for path, name in required_executables:
            suite.add(validate_executable(path, name))

    return suite


# ==============================================================================
# Shutdown validation
# ==============================================================================


def validate_shutdown(
    *,
    threads_to_check: list[threading.Thread] | None = None,
    tasks_to_check: list[asyncio.Task] | None = None,
    timeout: float = 10.0,
) -> ValidationSuite:
    """Run shutdown validation to ensure clean termination.

    Checks that threads have exited and tasks have completed.
    """
    suite = ValidationSuite(
        name="Shutdown Validation", description="Verifies clean shutdown"
    )

    if threads_to_check:
        for t in threads_to_check:
            t.join(timeout=timeout)
            if t.is_alive():
                suite.add(
                    ValidationResult(
                        name=f"Thread '{t.name}' terminated",
                        passed=False,
                        message="Thread did not exit within timeout",
                        severity=Severity.WARNING,
                        error_code=CORE_0004,
                    )
                )
            else:
                suite.add(
                    ValidationResult(
                        name=f"Thread '{t.name}' terminated",
                        passed=True,
                    )
                )

    if tasks_to_check:
        for task in tasks_to_check:
            if not task.done():
                task.cancel()
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        loop.run_until_complete(
                            asyncio.wait_for(asyncio.shield(task), timeout=timeout)
                        )
                except (asyncio.TimeoutError, asyncio.CancelledError, RuntimeError):
                    suite.add(
                        ValidationResult(
                            name=f"Task '{task.get_name()}' terminated",
                            passed=False,
                            message="Task did not cancel cleanly",
                            severity=Severity.WARNING,
                        )
                    )
                    continue
            suite.add(
                ValidationResult(
                    name=f"Task '{task.get_name()}' terminated",
                    passed=True,
                )
            )

    return suite


# ==============================================================================
# Runtime validation
# ==============================================================================


def validate_runtime(
    health_monitor=None,
    components: list[str] | None = None,
    heartbeat_timeout: float = 60.0,
) -> ValidationSuite:
    """Run runtime validation checks.

    Verifies:
    - Components are in expected health states
    - Heartbeats are recent
    - No unexpected failures
    """
    suite = ValidationSuite(
        name="Runtime Validation", description="Periodic runtime health checks"
    )

    if health_monitor is None:
        from core.health_monitor import get_health_monitor

        health_monitor = get_health_monitor()

    if components:
        for comp in components:
            state = health_monitor.get_state(comp)
            if state in (HealthState.FAILED,):
                suite.add(
                    ValidationResult(
                        name=f"Component '{comp}' health",
                        passed=False,
                        message="Component is in FAILED state",
                        severity=Severity.ERROR,
                    )
                )
            elif state == HealthState.DEGRADED:
                suite.add(
                    ValidationResult(
                        name=f"Component '{comp}' health",
                        passed=False,
                        message="Component is in DEGRADED state",
                        severity=Severity.WARNING,
                    )
                )
            elif state == HealthState.UNKNOWN:
                suite.add(
                    ValidationResult(
                        name=f"Component '{comp}' health",
                        passed=False,
                        message="Component state is UNKNOWN",
                        severity=Severity.WARNING,
                    )
                )
            else:
                suite.add(
                    ValidationResult(
                        name=f"Component '{comp}' health",
                        passed=True,
                        message=f"State: {state.value}",
                    )
                )

            # Check heartbeat
            alive = health_monitor.check_heartbeat(comp, timeout=heartbeat_timeout)
            if not alive:
                suite.add(
                    ValidationResult(
                        name=f"Component '{comp}' heartbeat",
                        passed=False,
                        message=f"Heartbeat timeout ({heartbeat_timeout}s)",
                        severity=Severity.WARNING,
                    )
                )
            else:
                suite.add(
                    ValidationResult(
                        name=f"Component '{comp}' heartbeat",
                        passed=True,
                    )
                )

    return suite


# ==============================================================================
# Config schema validation
# ==============================================================================

_CONFIG_SCHEMA: dict[str, type] = {
    "api": dict,
    "api_key": str,
    "auto_update_config": bool,
    "comment_commands": dict,
    "config_advanced": bool,
    "config_version": str,
    "console": dict,
    "control_method": str,
    "gui": dict,
    "java": dict,
    "mc_version": str,
    "minecraft_server_api": dict,
    "overlay": dict,
    "plugin_sandbox": dict,
    "port_policy": dict,
    "rcon": dict,
    "server_host": str,
    "shutdown": dict,
    "show_sudo_warning": bool,
    "tiktok": dict,
    "update": dict,
}


def validate_config_schema(data: Any, path: str = "") -> None:
    """Validate *data* against the config schema.

    Raises ``TypeError`` on the first violation.
    ``config_version`` must be a recognised semantic version.
    """
    if not isinstance(data, dict):
        raise TypeError(f"Config must be a dict, got {type(data).__name__}")

    for key, expected_type in _CONFIG_SCHEMA.items():
        full_key = f"{path}.{key}" if path else key
        if key not in data:
            continue
        value = data[key]
        if not isinstance(value, expected_type):
            raise TypeError(
                f"{full_key!r} must be {expected_type.__name__}, "
                f"got {type(value).__name__}"
            )

    raw_ver = data.get("config_version", "")
    try:
        norm_ver = normalize_config_version(raw_ver)
    except ValueError as e:
        raise ValueError(f"config_version is not a recognised version format: {e}")

    major = int(norm_ver.split(".")[0])
    if major < 1:
        log.info(
            "Config version %s is legacy — will be normalised to %s on write",
            norm_ver,
            EXPECTED_CONFIG_VERSION,
        )

    known = set(_CONFIG_SCHEMA)
    unknown = set(data) - known
    if unknown:
        log.warning("Unknown config keys (possible typo): %s", sorted(unknown))
