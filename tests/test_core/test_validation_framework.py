import asyncio

import pytest


class TestValidationResult:
    def test_default_construction(self):
        from core.validation_framework import ValidationResult

        r = ValidationResult(name="check-1", passed=True)
        assert r.name == "check-1"
        assert r.passed is True
        assert r.message == ""

    def test_format_pass(self):
        from core.validation_framework import ValidationResult

        r = ValidationResult(name="check", passed=True, message="all good")
        assert "[PASS] check: all good" in r.format()

    def test_format_fail(self):
        from core.validation_framework import ValidationResult

        r = ValidationResult(name="check", passed=False, message="bad")
        assert "[FAIL] check: bad" in r.format()

    def test_format_with_error_code(self):
        from core.error_codes import CORE_0004
        from core.validation_framework import ValidationResult

        r = ValidationResult(name="timeout", passed=False, error_code=CORE_0004)
        text = r.format()
        assert "[CORE-0004]" in text
        assert "[FAIL]" in text

    def test_to_dict(self):
        from core.error_codes import Severity
        from core.validation_framework import ValidationResult

        r = ValidationResult(name="x", passed=True, severity=Severity.ERROR)
        d = r.to_dict()
        assert d["name"] == "x"
        assert d["passed"] is True
        assert d["severity"] == "ERROR"

    def test_to_dict_with_error_code(self):
        from core.error_codes import CONFIG_0001
        from core.validation_framework import ValidationResult

        r = ValidationResult(name="cfg", passed=False, error_code=CONFIG_0001)
        d = r.to_dict()
        assert d["error_code"] == "CONFIG-0001"


class TestValidationSuite:
    def test_empty_suite(self):
        from core.validation_framework import ValidationSuite

        s = ValidationSuite(name="empty")
        assert s.name == "empty"
        assert s.all_passed() is True
        assert s.failures() == []

    def test_all_passed(self):
        from core.validation_framework import ValidationResult, ValidationSuite

        s = ValidationSuite(name="all-good")
        s.add(ValidationResult("a", True))
        s.add(ValidationResult("b", True))
        assert s.all_passed() is True
        assert s.failures() == []

    def test_some_failed(self):
        from core.validation_framework import ValidationResult, ValidationSuite

        s = ValidationSuite(name="partial")
        s.add(ValidationResult("a", True))
        s.add(ValidationResult("b", False))
        assert s.all_passed() is False
        assert len(s.failures()) == 1

    def test_warnings(self):
        from core.error_codes import Severity
        from core.validation_framework import ValidationResult, ValidationSuite

        s = ValidationSuite(name="w")
        s.add(ValidationResult("a", True, severity=Severity.INFO))
        s.add(ValidationResult("b", True, severity=Severity.WARNING))
        assert len(s.warnings()) == 1

    def test_critical_failures(self):
        from core.error_codes import Severity
        from core.validation_framework import ValidationResult, ValidationSuite

        s = ValidationSuite(name="crit")
        s.add(ValidationResult("a", False, severity=Severity.ERROR))
        s.add(ValidationResult("b", False, severity=Severity.WARNING))
        assert len(s.critical_failures()) == 1

    def test_summary(self):
        from core.validation_framework import ValidationResult, ValidationSuite

        s = ValidationSuite(name="sum")
        s.add(ValidationResult("a", True))
        s.add(ValidationResult("b", False))
        text = s.summary()
        assert "sum: 1/2 passed, 1 failed" in text
        assert "[PASS]" in text
        assert "[FAIL]" in text

    def test_to_dict(self):
        from core.validation_framework import ValidationResult, ValidationSuite

        s = ValidationSuite(name="d")
        s.add(ValidationResult("a", True))
        d = s.to_dict()
        assert d["name"] == "d"
        assert d["total"] == 1
        assert d["passed"] == 1


class TestTimeoutResult:
    def test_success_default(self):
        from core.validation_framework import TimeoutResult

        r = TimeoutResult(success=True)
        assert r.success is True
        assert r.timed_out is False

    def test_timeout(self):
        from core.validation_framework import TimeoutResult

        r = TimeoutResult(success=False, timed_out=True, elapsed=5.0)
        assert r.timed_out is True
        assert r.elapsed == 5.0


class TestRunWithTimeout:
    @pytest.mark.asyncio
    async def test_async_timeout_success(self):
        from core.validation_framework import run_with_timeout

        async def quick():
            await asyncio.sleep(0.01)
            return 42

        result = await run_with_timeout(quick(), timeout=5.0)
        assert result.success is True
        assert result.result == 42
        assert result.timed_out is False

    @pytest.mark.asyncio
    async def test_async_timeout_exceeded(self):
        from core.validation_framework import run_with_timeout

        async def slow():
            await asyncio.sleep(10)

        result = await run_with_timeout(slow(), timeout=0.05)
        assert result.success is False
        assert result.timed_out is True
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_async_timeout_exception(self):
        from core.validation_framework import run_with_timeout

        async def failing():
            raise ValueError("oops")

        result = await run_with_timeout(failing(), timeout=5.0)
        assert result.success is False
        assert result.timed_out is False
        assert result.error is not None


class TestRunWithTimeoutSync:
    def test_sync_success(self):
        from core.validation_framework import run_with_timeout_sync

        def quick():
            return 42

        result = run_with_timeout_sync(quick, timeout=5.0)
        assert result.success is True
        assert result.result == 42

    def test_sync_timeout(self):
        import time

        from core.validation_framework import run_with_timeout_sync

        def slow():
            time.sleep(10)
            return 42

        result = run_with_timeout_sync(slow, timeout=0.05)
        assert result.success is False
        assert result.timed_out is True

    def test_sync_exception(self):
        from core.validation_framework import run_with_timeout_sync

        def failing():
            raise ValueError("sync fail")

        result = run_with_timeout_sync(failing, timeout=5.0)
        assert result.success is False
        assert result.error is not None


class TestStartupValidation:
    def test_validate_config_exists(self, tmp_path):
        from core.validation_framework import validate_config_exists

        cfg = tmp_path / "config.yaml"
        cfg.write_text("key: value")
        result = validate_config_exists(cfg)
        assert result.passed is True

    def test_validate_config_missing(self, tmp_path):
        from core.validation_framework import validate_config_exists

        cfg = tmp_path / "nonexistent.yaml"
        result = validate_config_exists(cfg)
        assert result.passed is False

    def test_validate_directory_exists(self, tmp_path):
        from core.validation_framework import validate_directory

        d = tmp_path / "mydir"
        d.mkdir()
        result = validate_directory(d, "mydir")
        assert result.passed is True

    def test_validate_directory_missing(self, tmp_path):
        from core.validation_framework import validate_directory

        d = tmp_path / "missing"
        result = validate_directory(d, "missing")
        assert result.passed is False

    def test_validate_directory_created(self, tmp_path):
        from core.validation_framework import validate_directory

        d = tmp_path / "auto_create"
        result = validate_directory(d, "auto", create=True)
        assert result.passed is True
        assert d.exists()

    def test_validate_directory_creation_failure(self, tmp_path, monkeypatch):
        from core.validation_framework import validate_directory

        d = tmp_path / "fail_create"
        monkeypatch.setattr(
            type(d),
            "mkdir",
            lambda self, **kw: (_ for _ in ()).throw(PermissionError("denied")),
        )
        result = validate_directory(d, "fail", create=True)
        assert result.passed is False

    def test_validate_directory_not_a_dir(self, tmp_path):
        from core.validation_framework import validate_directory

        f = tmp_path / "file"
        f.write_text("content")
        result = validate_directory(f, "not-a-dir")
        assert result.passed is False

    def test_validate_file_exists(self, tmp_path):
        from core.validation_framework import validate_file

        f = tmp_path / "test.txt"
        f.write_text("hello")
        result = validate_file(f, "test.txt")
        assert result.passed is True

    def test_validate_file_missing(self, tmp_path):
        from core.validation_framework import validate_file

        f = tmp_path / "missing.txt"
        result = validate_file(f, "missing.txt")
        assert result.passed is False

    def test_validate_port_free(self):
        import socket

        from core.validation_framework import validate_port_free

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
            result = validate_port_free("127.0.0.1", port, "test port")
            assert result.passed is False

    def test_validate_port_available(self):
        from core.validation_framework import validate_port_free

        result = validate_port_free("127.0.0.1", 59999, "free port")
        assert result.passed is True

    def test_validate_executable(self, tmp_path):
        from core.validation_framework import validate_executable

        exe = tmp_path / "test_script"
        exe.write_text("#!/bin/sh")
        result = validate_executable(exe, "test")
        assert result.passed is True

    def test_validate_executable_missing(self, tmp_path):
        from core.validation_framework import validate_executable

        exe = tmp_path / "missing"
        result = validate_executable(exe, "missing")
        assert result.passed is False

    def test_run_startup_validation(self, tmp_path):
        from core.validation_framework import run_startup_validation

        cfg = tmp_path / "config.yaml"
        cfg.write_text("key: val")
        suite = run_startup_validation(
            config_path=cfg,
            required_dirs=[(tmp_path / "logs", "logs", True)],
            required_files=[(cfg, "config")],
        )
        assert suite.all_passed() is True

    def test_run_startup_validation_failure(self, tmp_path):
        from core.validation_framework import run_startup_validation

        missing = tmp_path / "nonexistent.yaml"
        suite = run_startup_validation(
            config_path=missing,
        )
        assert suite.all_passed() is False
        assert len(suite.critical_failures()) >= 1


class TestRuntimeValidation:
    def test_runtime_validation_healthy(self):
        from core.health_monitor import HealthMonitor, HealthState
        from core.validation_framework import validate_runtime

        hm = HealthMonitor()
        hm.register("svc", HealthState.RUNNING)
        hm.record_heartbeat("svc")
        suite = validate_runtime(health_monitor=hm, components=["svc"])
        assert suite.all_passed() is True

    def test_runtime_validation_failed(self):
        from core.health_monitor import HealthMonitor, HealthState
        from core.validation_framework import validate_runtime

        hm = HealthMonitor()
        hm.register("svc", HealthState.FAILED)
        suite = validate_runtime(health_monitor=hm, components=["svc"])
        assert suite.all_passed() is False

    def test_runtime_validation_unknown(self):
        from core.health_monitor import HealthMonitor, HealthState
        from core.validation_framework import validate_runtime

        hm = HealthMonitor()
        hm.register("svc", HealthState.UNKNOWN)
        suite = validate_runtime(health_monitor=hm, components=["svc"])
        assert suite.all_passed() is False

    def test_runtime_validation_missing_component(self):
        from core.health_monitor import HealthMonitor
        from core.validation_framework import validate_runtime

        hm = HealthMonitor()
        suite = validate_runtime(health_monitor=hm, components=["missing"])
        assert suite.all_passed() is False


class TestShutdownValidation:
    def test_shutdown_no_checks(self):
        from core.validation_framework import validate_shutdown

        suite = validate_shutdown()
        assert suite.all_passed() is True

    def test_shutdown_with_completed_thread(self):
        import threading

        from core.validation_framework import validate_shutdown

        done = threading.Thread(target=lambda: None, name="done")
        done.start()
        done.join()
        suite = validate_shutdown(threads_to_check=[done])
        assert suite.all_passed() is True
