"""Tests for the central startup configuration gate (``core.config_gate``)."""

import logging


class TestConfigGateResult:
    def test_missing_file_is_fatal_config_0001(self, tmp_path):
        """A missing config file yields a fatal CONFIG-0001 result."""
        from core.config_gate import load_and_validate_config

        result = load_and_validate_config(tmp_path / "config.yaml")

        assert result.ok is False
        assert result.fatal is True
        assert result.config is None
        codes = [i.error_code for i in result.issues]
        assert "CONFIG-0001" in codes
        assert any(i.fatal for i in result.issues)

    def test_yaml_syntax_error_is_fatal_config_0002(self, tmp_path):
        """A YAML syntax error yields a fatal CONFIG-0002 with a mark."""
        from core.config_gate import load_and_validate_config

        path = tmp_path / "config.yaml"
        path.write_text("console: {broken: [", encoding="utf-8")

        result = load_and_validate_config(path)

        assert result.ok is False
        assert result.fatal is True
        assert result.config is None
        codes = [i.error_code for i in result.issues]
        assert "CONFIG-0002" in codes
        issue = next(i for i in result.issues if i.error_code == "CONFIG-0002")
        assert issue.path == str(path)
        assert issue.line is not None  # ruamel provides a problem mark
        text = issue.format()
        assert "CONFIG-0002" in text
        assert f":{issue.line}" in text

    def test_valid_file_is_ok(self, tmp_path):
        """A valid config maps cleanly with ok=True and no issues."""
        from core.config_gate import load_and_validate_config

        path = tmp_path / "config.yaml"
        path.write_text(
            'config_version: "1.0"\nconsole:\n  visible: true\n',
            encoding="utf-8",
        )

        result = load_and_validate_config(path)

        assert result.ok is True
        assert result.fatal is False
        assert result.issues == []
        assert result.config == {"config_version": "1.0", "console": {"visible": True}}

    def test_empty_file_is_ok(self, tmp_path):
        """An empty YAML document is treated as an empty mapping (non-fatal)."""
        from core.config_gate import load_and_validate_config

        path = tmp_path / "config.yaml"
        path.write_text("", encoding="utf-8")

        result = load_and_validate_config(path)

        assert result.config == {}
        assert result.fatal is False
        # No config_version → a CONFIG-0004 warning is surfaced, but the
        # document still loads and startup may proceed.
        assert all(not i.fatal for i in result.issues)

    def test_non_mapping_document_is_fatal(self, tmp_path):
        """A top-level scalar/list cannot be used and is escalated to fatal."""
        from core.config_gate import load_and_validate_config

        path = tmp_path / "config.yaml"
        path.write_text("- just\n- a\n- list\n", encoding="utf-8")

        result = load_and_validate_config(path)

        assert result.fatal is True
        assert result.config is None
        assert result.issues[0].error_code == "CONFIG-0004"

    def test_schema_type_mismatch_is_non_fatal_warning(self, tmp_path):
        """A schema type violation produces a non-fatal CONFIG-0004 warning."""
        from core.config_gate import load_and_validate_config

        path = tmp_path / "config.yaml"
        path.write_text("config_version: 1.0\nserver_host: 127\n", encoding="utf-8")

        result = load_and_validate_config(path)

        assert result.fatal is False
        assert result.ok is False  # issues exist, but non-fatal
        assert result.config is not None
        assert result.issues[0].error_code == "CONFIG-0004"
        assert result.issues[0].fatal is False

    def test_reports_via_crash_manager(self, tmp_path, caplog):
        """When a crash manager is passed, each issue is reported via it."""
        from core.config_gate import load_and_validate_config

        class FakeCrashManager:
            def __init__(self):
                self.reports = []

            def report_error(self, error_code, detail="", context_info=None):
                """Record one structured report; signature matches CrashManager."""
                self.reports.append((error_code, detail, context_info))
                return None

        cm = FakeCrashManager()
        with caplog.at_level(logging.DEBUG):
            result = load_and_validate_config(tmp_path / "missing.yaml", cm)

        assert result.fatal is True
        assert len(cm.reports) == 1
        error_code, detail, ctx = cm.reports[0]
        assert error_code.code == "CONFIG-0001"
        assert ctx["path"] == str(tmp_path / "missing.yaml")
        assert ctx["fatal"] is True
        assert "CONFIG-0001" in detail
