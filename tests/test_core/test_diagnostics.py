import pytest


@pytest.fixture(autouse=True)
def _reset_health():
    from core.health_monitor import reset_health_monitor

    reset_health_monitor()
    yield
    reset_health_monitor()


class TestDiagnosticsReport:
    def test_generate_report_basic_structure(self):
        from core.diagnostics import generate_diagnostics_report

        report = generate_diagnostics_report()
        assert "generated_at" in report
        assert "generated_at_iso" in report
        assert "application" in report
        assert "health" in report
        assert "threads" in report
        assert "error_codes" in report
        assert report["application"]["python_version"] is not None
        assert report["application"]["platform"] is not None

    def test_report_with_crash_manager(self):
        from core.crash_manager import CrashManager
        from core.diagnostics import generate_diagnostics_report

        cm = CrashManager("test")
        report = generate_diagnostics_report(crash_manager=cm)
        assert "crash_manager" in report
        assert report["crash_manager"]["module"] == "test"

    def test_report_with_crash_history(self):
        from core.crash_manager import CrashManager
        from core.diagnostics import generate_diagnostics_report
        from core.error_codes import CORE_0001

        cm = CrashManager("test")
        cm.report_exception(CORE_0001, ValueError("boom"))
        report = generate_diagnostics_report(crash_manager=cm)
        assert len(report["crash_history"]) == 1

    def test_report_with_extra_data(self):
        from core.diagnostics import generate_diagnostics_report

        report = generate_diagnostics_report(extra={"custom_key": "custom_value"})
        assert report["extra"] == {"custom_key": "custom_value"}

    def test_report_with_health_state(self):
        from core.diagnostics import generate_diagnostics_report
        from core.health_monitor import HealthState, get_health_monitor

        hm = get_health_monitor()
        hm.register("svc", HealthState.RUNNING)
        hm.register("db", HealthState.FAILED)
        report = generate_diagnostics_report()
        health = report["health"]
        assert health["total_components"] == 2
        assert health["running"] == 1
        assert health["failed"] == 1
        assert "db" in health["failed_components"]

    def test_thread_stats_present(self):
        from core.diagnostics import generate_diagnostics_report

        report = generate_diagnostics_report()
        assert report["threads"]["active_count"] > 0
        assert len(report["threads"]["threads"]) > 0

    def test_error_codes_count(self):
        from core.diagnostics import generate_diagnostics_report

        report = generate_diagnostics_report()
        assert report["error_codes"]["total"] > 0

    def test_memory_stats_may_be_empty(self):
        from core.diagnostics import generate_diagnostics_report

        report = generate_diagnostics_report()
        assert "memory" in report

    def test_queue_stats_present(self):
        from core.diagnostics import generate_diagnostics_report

        report = generate_diagnostics_report()
        assert "queue_stats" in report


class TestDiagnosticsMarkdown:
    def test_markdown_report_structure(self):
        from core.diagnostics import generate_diagnostics_markdown

        md = generate_diagnostics_markdown()
        assert "# TikTok2Mc Diagnostics Report" in md
        assert "## Health Status" in md
        assert "## Component States" in md
        assert "## Threads" in md

    def test_markdown_with_failed_components(self):
        from core.diagnostics import generate_diagnostics_markdown
        from core.health_monitor import HealthState, get_health_monitor

        hm = get_health_monitor()
        hm.register("broken", HealthState.FAILED)
        md = generate_diagnostics_markdown()
        assert "**Failed**" in md
        assert "broken" in md

    def test_markdown_with_crash_history(self):
        from core.crash_manager import CrashManager
        from core.diagnostics import generate_diagnostics_markdown
        from core.error_codes import CORE_0001

        cm = CrashManager("test")
        cm.report_exception(CORE_0001, ValueError("boom"))
        md = generate_diagnostics_markdown(crash_manager=cm)
        assert "## Crash History" in md

    def test_markdown_with_extra(self):
        from core.diagnostics import generate_diagnostics_markdown

        md = generate_diagnostics_markdown(extra={"test": "value"})
        assert "# TikTok2Mc Diagnostics Report" in md


class TestTimestampHelper:
    def test_timestamp_iso_format(self):
        from core.diagnostics import _timestamp_iso

        ts = _timestamp_iso()
        assert "T" in ts
