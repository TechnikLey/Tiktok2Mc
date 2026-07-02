import pytest


class TestSeverity:
    def test_enum_values(self):
        from core.error_codes import Severity

        assert Severity.DEBUG.value == 0
        assert Severity.INFO.value == 1
        assert Severity.NOTICE.value == 2
        assert Severity.WARNING.value == 3
        assert Severity.ERROR.value == 4
        assert Severity.CRITICAL.value == 5
        assert Severity.FATAL.value == 6

    def test_label(self):
        from core.error_codes import Severity

        assert Severity.DEBUG.label() == "DEBUG"
        assert Severity.ERROR.label() == "ERROR"

    def test_from_string_valid(self):
        from core.error_codes import Severity

        assert Severity.from_string("ERROR") == Severity.ERROR
        assert Severity.from_string("warning") == Severity.WARNING
        assert Severity.from_string("FATAL") == Severity.FATAL

    def test_from_string_invalid_defaults_to_warning(self):
        from core.error_codes import Severity

        assert Severity.from_string("UNKNOWN") == Severity.WARNING


class TestSubsystem:
    def test_enum_values(self):
        from core.error_codes import Subsystem

        assert Subsystem.CORE.value == "CORE"
        assert Subsystem.PLUGIN.value == "PLUGIN"
        assert Subsystem.TIKTOK.value == "TIKTOK"

    def test_from_string_valid(self):
        from core.error_codes import Subsystem

        assert Subsystem.from_string("CORE") == Subsystem.CORE
        assert Subsystem.from_string("plugin") == Subsystem.PLUGIN

    def test_from_string_invalid_defaults_to_core(self):
        from core.error_codes import Subsystem

        assert Subsystem.from_string("NONEXISTENT") == Subsystem.CORE


class TestErrorCode:
    def test_create_error_code(self):
        from core.error_codes import ErrorCode, Severity, Subsystem

        ec = ErrorCode(
            code="TEST-0001",
            subsystem=Subsystem.CORE,
            severity=Severity.ERROR,
            message="Test error",
        )
        assert ec.code == "TEST-0001"
        assert ec.subsystem == Subsystem.CORE

    def test_format_basic(self):
        from core.error_codes import ErrorCode, Severity, Subsystem

        ec = ErrorCode(
            code="TEST-0001",
            subsystem=Subsystem.CORE,
            severity=Severity.ERROR,
            message="Test error",
        )
        text = ec.format()
        assert "TEST-0001" in text
        assert "Test error" in text

    def test_format_with_detail(self):
        from core.error_codes import ErrorCode, Severity, Subsystem

        ec = ErrorCode(
            code="TEST-0001",
            subsystem=Subsystem.CORE,
            severity=Severity.ERROR,
            message="Test error",
        )
        text = ec.format(detail="Something went wrong")
        assert "Something went wrong" in text

    def test_format_with_context(self):
        from core.error_codes import ErrorCode, Severity, Subsystem

        ec = ErrorCode(
            code="TEST-0001",
            subsystem=Subsystem.CORE,
            severity=Severity.ERROR,
            message="Test error",
        )
        text = ec.format(context={"file": "test.txt"})
        assert "test.txt" in text

    def test_format_with_recovery(self):
        from core.error_codes import ErrorCode, Severity, Subsystem

        ec = ErrorCode(
            code="TEST-0001",
            subsystem=Subsystem.CORE,
            severity=Severity.ERROR,
            message="Test error",
            recovery_hint="Restart the service",
        )
        text = ec.format()
        assert "Restart" in text

    def test_with_context_creates_error_instance(self):
        from core.error_codes import ErrorCode, Severity, Subsystem

        ec = ErrorCode(
            code="TEST-0001",
            subsystem=Subsystem.CORE,
            severity=Severity.ERROR,
            message="Test error",
        )
        ei = ec.with_context(component="svc", detail="test")
        assert ei.code == "TEST-0001"
        assert ei.context == {"component": "svc", "detail": "test"}

    def test_to_dict(self):
        from core.error_codes import ErrorCode, Severity, Subsystem

        ec = ErrorCode(
            code="TEST-0001",
            subsystem=Subsystem.CORE,
            severity=Severity.ERROR,
            message="Test error",
            description="A test",
            recovery_hint="Restart",
            impact="None",
        )
        d = ec.to_dict()
        assert d["code"] == "TEST-0001"
        assert d["severity"] == "ERROR"


class TestErrorInstance:
    def test_default_construction(self):
        from core.error_codes import ErrorInstance, Severity, Subsystem

        ei = ErrorInstance(
            code="TEST-0001",
            subsystem=Subsystem.CORE,
            severity=Severity.ERROR,
            message="Test",
        )
        assert ei.code == "TEST-0001"
        assert ei.recovery_status == "none"

    def test_with_exception(self):
        from core.error_codes import ErrorInstance, Severity, Subsystem

        ei = ErrorInstance(
            code="TEST-0001",
            subsystem=Subsystem.CORE,
            severity=Severity.ERROR,
            message="Test",
        )
        exc = ValueError("root cause")
        result = ei.with_exception(exc)
        assert result.root_exception is exc
        assert result is ei

    def test_format_with_exception(self):
        from core.error_codes import ErrorInstance, Severity, Subsystem

        ei = ErrorInstance(
            code="TEST-0001",
            subsystem=Subsystem.CORE,
            severity=Severity.ERROR,
            message="Test error",
        )
        ei.with_exception(ValueError("boom"))
        text = ei.format()
        assert "ValueError" in text
        assert "boom" in text

    def test_format_with_impact_and_recovery(self):
        from core.error_codes import ErrorInstance, Severity, Subsystem

        ei = ErrorInstance(
            code="TEST-0001",
            subsystem=Subsystem.CORE,
            severity=Severity.ERROR,
            message="Test error",
            impact="Service down",
            recovery_hint="Restart",
        )
        text = ei.format()
        assert "Service down" in text
        assert "Restart" in text

    def test_format_with_context(self):
        from core.error_codes import ErrorInstance, Severity, Subsystem

        ei = ErrorInstance(
            code="TEST-0001",
            subsystem=Subsystem.CORE,
            severity=Severity.ERROR,
            message="Test",
            context={"url": "http://example.com"},
        )
        text = ei.format()
        assert "http://example.com" in text


class TestErrorCodeConstants:
    def test_core_codes_exist(self):
        from core import error_codes

        assert error_codes.CORE_0001.code == "CORE-0001"
        assert error_codes.CORE_0002.code == "CORE-0002"
        assert error_codes.CORE_0003.code == "CORE-0003"
        assert error_codes.CORE_0004.code == "CORE-0004"
        assert error_codes.CORE_0005.code == "CORE-0005"
        assert error_codes.CORE_0006.code == "CORE-0006"
        assert error_codes.CORE_0007.code == "CORE-0007"
        assert error_codes.CORE_0008.code == "CORE-0008"
        assert error_codes.CORE_0009.code == "CORE-0009"

    def test_plugin_codes_exist(self):
        from core import error_codes

        assert error_codes.PLUGIN_0001.code == "PLUGIN-0001"
        assert error_codes.PLUGIN_0017.code == "PLUGIN-0017"

    def test_gui_codes_exist(self):
        from core import error_codes

        assert error_codes.GUI_0001.code == "GUI-0001"
        assert error_codes.GUI_0005.code == "GUI-0005"

    def test_api_codes_exist(self):
        from core import error_codes

        assert error_codes.API_0001.code == "API-0001"
        assert error_codes.API_0008.code == "API-0008"

    def test_subsystem_coverage(self):
        from core import error_codes
        from core.error_codes import Subsystem

        subsystems_used = set()
        for attr_name in dir(error_codes):
            attr = getattr(error_codes, attr_name)
            if hasattr(attr, "subsystem"):
                subsystems_used.add(attr.subsystem)

        expected = {
            Subsystem.CORE, Subsystem.PLUGIN, Subsystem.GUI, Subsystem.API,
            Subsystem.NETWORK, Subsystem.CONFIG, Subsystem.OVERLAY,
            Subsystem.LIFECYCLE, Subsystem.MC, Subsystem.TIKTOK, Subsystem.HOOK,
            Subsystem.WATCHER, Subsystem.WORKER, Subsystem.SHUTDOWN,
            Subsystem.STARTUP, Subsystem.VALIDATE, Subsystem.DIAG,
            Subsystem.SANDBOX, Subsystem.SECURITY, Subsystem.BACKUP,
            Subsystem.UPDATE, Subsystem.HEARTBEAT,
        }
        assert subsystems_used == expected

    def test_severity_distribution(self):
        from core import error_codes
        from core.error_codes import Severity

        severities = {}
        for attr_name in dir(error_codes):
            attr = getattr(error_codes, attr_name)
            if hasattr(attr, "severity"):
                s = attr.severity
                severities[s] = severities.get(s, 0) + 1

        assert Severity.WARNING in severities
        assert Severity.ERROR in severities
        assert sum(severities.values()) > 50


class TestLookupHelpers:
    def test_get_error_code_found(self):
        from core.error_codes import get_error_code

        ec = get_error_code("CORE-0001")
        assert ec is not None
        assert ec.code == "CORE-0001"

    def test_get_error_code_not_found(self):
        from core.error_codes import get_error_code

        ec = get_error_code("NONEXISTENT-9999")
        assert ec is None

    def test_list_all_codes(self):
        from core.error_codes import list_all_codes

        codes = list_all_codes()
        assert len(codes) > 50
        codes_sorted = [c.code for c in codes]
        assert codes_sorted == sorted(codes_sorted)

    def test_all_codes_unique(self):
        from core.error_codes import list_all_codes

        codes = list_all_codes()
        code_ids = [c.code for c in codes]
        assert len(code_ids) == len(set(code_ids))

    def test_all_codes_have_required_fields(self):
        from core.error_codes import list_all_codes

        for ec in list_all_codes():
            assert ec.code, f"Missing code in {ec}"
            assert ec.message, f"Missing message in {ec.code}"
            assert ec.subsystem is not None, f"Missing subsystem in {ec.code}"
            assert ec.severity is not None, f"Missing severity in {ec.code}"
