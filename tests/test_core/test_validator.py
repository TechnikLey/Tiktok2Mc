import pytest

pytestmark = pytest.mark.validator


class TestValidatorBrackets:
    def test_balanced_square_brackets(self):
        from core.validator import validate_text

        diags = validate_text("test:/say [test]")
        errors = [d for d in diags if d.severity.name == "ERROR"]
        assert len(errors) == 0

    def test_unmatched_close_square(self):
        from core.validator import validate_text

        diags = validate_text("test:/say ]")
        errors = [d for d in diags if d.code == "unmatched_close_square"]
        assert len(errors) == 1

    def test_unbalanced_open_square(self):
        from core.validator import validate_text

        diags = validate_text("test:/say [test")
        errors = [d for d in diags if d.code == "unbalanced_square"]
        assert len(errors) == 1

    def test_balanced_curly_brackets(self):
        from core.validator import validate_text

        diags = validate_text("test:/say {nbt}")
        errors = [d for d in diags if d.severity.name == "ERROR"]
        assert len(errors) == 0

    def test_unmatched_close_curly(self):
        from core.validator import validate_text

        diags = validate_text("test:/say }")
        errors = [d for d in diags if d.code == "unmatched_close_curly"]
        assert len(errors) == 1

    def test_unbalanced_open_curly(self):
        from core.validator import validate_text

        diags = validate_text("test:/say {nbt")
        errors = [d for d in diags if d.code == "unbalanced_curly"]
        assert len(errors) == 1

    def test_brackets_inside_quotes(self):
        from core.validator import validate_text

        diags = validate_text('test:/say "hello [world]"')
        errors = [d for d in diags if d.severity.name == "ERROR"]
        assert len(errors) == 0

    def test_brackets_inside_single_quotes(self):
        from core.validator import validate_text

        diags = validate_text("test:/say 'hello [world]'")
        errors = [d for d in diags if d.severity.name == "ERROR"]
        assert len(errors) == 0

    def test_escaped_quotes_inside_brackets(self):
        from core.validator import validate_text

        diags = validate_text(r"test:/say [it\'s ok]")
        errors = [d for d in diags if d.severity.name == "ERROR"]
        assert len(errors) == 0


class TestValidatorColons:
    def test_missing_colon(self):
        from core.validator import validate_text

        diags = validate_text("no colon here")
        errors = [d for d in diags if d.code == "missing_colon"]
        assert len(errors) == 1

    def test_space_after_colon(self):
        from core.validator import validate_text

        diags = validate_text("test: /say hi")
        warnings = [d for d in diags if d.code == "space_after_colon"]
        assert len(warnings) == 1

    def test_no_content_after_colon(self):
        from core.validator import validate_text

        diags = validate_text("test:")
        errors = [d for d in diags if d.code == "no_content_after_colon"]
        assert len(errors) == 1

    def test_trailing_colon(self):
        from core.validator import validate_text

        diags = validate_text("test:/say:")
        errors = [d for d in diags if d.code == "trailing_colons"]
        assert len(errors) == 1

    def test_trailing_semicolon(self):
        from core.validator import validate_text

        diags = validate_text("test:/say;")
        infos = [d for d in diags if d.code == "trailing_semicolon"]
        assert len(infos) == 1


class TestValidatorTriggerNames:
    def test_valid_trigger(self):
        from core.validator import validate_text

        diags = validate_text("like:/say Thanks!")
        errors = [d for d in diags if d.severity.name == "ERROR"]
        assert len(errors) == 0

    def test_valid_quoted_trigger(self):
        from core.validator import validate_text

        diags = validate_text("'my trigger':/say hi")
        errors = [d for d in diags if d.severity.name == "ERROR"]
        assert len(errors) == 0

    def test_invalid_trigger_special_chars(self):
        from core.validator import validate_text

        diags = validate_text("bad-trigger!:x")
        errors = [d for d in diags if d.code == "invalid_trigger_name"]
        assert len(errors) == 1

    def test_invalid_quoted_trigger(self):
        from core.validator import validate_text

        diags = validate_text("'bad-trigger!':x")
        errors = [d for d in diags if d.code == "invalid_trigger_name"]
        assert len(errors) == 1

    def test_duplicate_trigger(self):
        from core.validator import validate_text

        diags = validate_text("dup:/a\ndup:/b")
        errors = [d for d in diags if d.code == "duplicate_trigger"]
        assert len(errors) == 1

    def test_disabled_trigger_not_counted_as_duplicate(self):
        from core.validator import validate_text

        diags = validate_text("##dup:/a\ndup:/b")
        errors = [d for d in diags if d.code == "duplicate_trigger"]
        assert len(errors) == 0

    def test_disabled_trigger_colliding_with_active_warns(self):
        from core.validator import validate_text

        diags = validate_text("like_2:/kill @a\n##like_2:/kill @a")
        errors = [d for d in diags if d.code == "duplicate_trigger"]
        assert len(errors) == 0
        warnings = [d for d in diags if d.code == "duplicate_trigger_disabled"]
        assert len(warnings) == 1
        assert warnings[0].severity.name == "WARNING"
        assert warnings[0].line == 1

    def test_active_trigger_colliding_with_earlier_disabled_warns(self):
        from core.validator import validate_text

        diags = validate_text("##dup:/a\ndup:/b")
        errors = [d for d in diags if d.code == "duplicate_trigger"]
        assert len(errors) == 0
        warnings = [d for d in diags if d.code == "duplicate_trigger_disabled"]
        assert len(warnings) == 1


class TestValidatorDisabledTriggers:
    def test_disabled_duplicate_pair_not_flagged(self):
        """Two disabled (##) triggers with the same name are OFF and must
        not count as duplicates."""
        from core.validator import validate_text

        diags = validate_text("##dup:/a\n##dup:/b")
        errors = [d for d in diags if d.code == "duplicate_trigger"]
        assert len(errors) == 0

    def test_disabled_trigger_does_not_duplicate_active(self):
        """A disabled (##) trigger sharing a name with an active trigger is
        OFF and must not be reported as a duplicate."""
        from core.validator import validate_text

        diags = validate_text("dup:/a\n##dup:/b")
        errors = [d for d in diags if d.code == "duplicate_trigger"]
        assert len(errors) == 0

    def test_active_duplicate_still_flagged(self):
        """Two active triggers with the same name are still errors."""
        from core.validator import validate_text

        diags = validate_text("dup:/a\ndup:/b")
        errors = [d for d in diags if d.code == "duplicate_trigger"]
        assert len(errors) == 1

    def test_disabled_trigger_still_syntax_validated(self):
        """Disabled triggers are kept as templates; their content is still
        validated for syntax errors."""
        from core.validator import validate_text

        diags = validate_text("##nocolonhere")
        errors = [d for d in diags if d.code == "missing_colon"]
        assert len(errors) == 1


class TestValidatorCommandPrefixes:
    def test_valid_slash(self):
        from core.validator import validate_text

        diags = validate_text("test:/say hi")
        errors = [d for d in diags if d.severity.name == "ERROR"]
        assert len(errors) == 0

    def test_valid_dollar(self):
        from core.validator import validate_text

        diags = validate_text("test:$script")
        errors = [d for d in diags if d.severity.name == "ERROR"]
        assert len(errors) == 0

    def test_valid_bang(self):
        from core.validator import validate_text

        diags = validate_text("test:!rcon cmd")
        errors = [d for d in diags if d.severity.name == "ERROR"]
        assert len(errors) == 0

    def test_valid_overlay_arrow(self):
        from core.validator import validate_text

        diags = validate_text("test:>>overlay")
        errors = [d for d in diags if d.severity.name == "ERROR"]
        assert len(errors) == 0

    def test_valid_overlay_named(self):
        from core.validator import validate_text

        diags = validate_text("test:@name>>overlay")
        errors = [d for d in diags if d.severity.name == "ERROR"]
        assert len(errors) == 0

    def test_valid_ampersand(self):
        from core.validator import validate_text

        diags = validate_text("test:&curl http://localhost")
        errors = [d for d in diags if d.severity.name == "ERROR"]
        assert len(errors) == 0

    def test_invalid_prefix(self):
        from core.validator import validate_text

        diags = validate_text("test:%bad")
        errors = [d for d in diags if d.code == "invalid_prefix"]
        assert len(errors) == 1


class TestValidatorPlaceholder:
    def test_comment_placeholder_on_comment_trigger(self):
        from core.validator import validate_text

        diags = validate_text("comment:>>say {comment}")
        errors = [d for d in diags if d.severity.name == "ERROR"]
        assert len(errors) == 0

    def test_comment_placeholder_wrong_trigger(self):
        from core.validator import validate_text

        diags = validate_text("like:>>say {comment}")
        errors = [d for d in diags if d.code == "comment_placeholder_wrong_trigger"]
        assert len(errors) == 1


class TestValidatorMultipliers:
    def test_valid_multiplier(self):
        from core.validator import validate_text

        diags = validate_text("test:/cmd x5")
        errors = [d for d in diags if d.severity.name == "ERROR"]
        assert len(errors) == 0

    def test_high_multiplier_warning(self):
        from core.validator import validate_text

        diags = validate_text("test:/cmd x100")
        warnings = [d for d in diags if d.code == "high_multi"]
        assert len(warnings) == 1

    def test_high_multiplier_suppressed_with_ignore_lag(self):
        from core.validator import validate_text

        diags = validate_text("test:/cmd x100 # ignore-lag")
        warnings = [d for d in diags if d.code == "high_multi"]
        assert len(warnings) == 0

    def test_invalid_multiplier(self):
        from core.validator import validate_text

        diags = validate_text("test:/cmd xabc")
        errors = [d for d in diags if d.code == "invalid_multiplier"]
        assert len(errors) == 1

    def test_overlay_multiplier_not_allowed(self):
        from core.validator import validate_text

        diags = validate_text("test:>>overlay x5")
        errors = [d for d in diags if d.code == "overlay_multiplier"]
        assert len(errors) == 1


class TestValidatorEmptyAndComments:
    def test_empty_line_skipped(self):
        from core.validator import validate_text

        diags = validate_text("\n\n")
        assert len(diags) == 0

    def test_comment_line_skipped(self):
        from core.validator import validate_text

        diags = validate_text("# this is a comment")
        assert len(diags) == 0

    def test_inline_comment(self):
        from core.validator import validate_text

        diags = validate_text("test:/say hi # inline comment")
        errors = [d for d in diags if d.severity.name == "ERROR"]
        assert len(errors) == 0


class TestValidatorSemicolonSeparatedCommands:
    def test_multiple_commands(self):
        from core.validator import validate_text

        diags = validate_text("test:/first;/second")
        errors = [d for d in diags if d.severity.name == "ERROR"]
        assert len(errors) == 0

    def test_empty_command_block(self):
        from core.validator import validate_text

        diags = validate_text("test:/first;;/third")
        warnings = [d for d in diags if d.code == "empty_command_block"]
        assert len(warnings) == 1

    def test_trailing_semicolon_after_multiple(self):
        from core.validator import validate_text

        diags = validate_text("test:/first;/second;")
        infos = [d for d in diags if d.code == "trailing_semicolon"]
        assert len(infos) == 1


class TestValidatorFileLevel:
    def test_validate_file_not_found(self):
        from core.validator import validate_file

        with pytest.raises(FileNotFoundError):
            validate_file("/nonexistent/path.mca")

    def test_validate_file_valid(self, tmp_path):
        from core.validator import validate_file

        f = tmp_path / "valid.mca"
        f.write_text("test:/say hi", encoding="utf-8")
        diags = validate_file(f, raise_on_error=False)
        assert len(diags) == 0

    def test_validate_file_raises_on_error(self, tmp_path):
        from core.validator import validate_file

        f = tmp_path / "bad.mca"
        f.write_text("no colon", encoding="utf-8")
        with pytest.raises(ValueError, match="Validation failed"):
            validate_file(f, raise_on_error=True)

    def test_validate_file_no_raise(self, tmp_path):
        from core.validator import validate_file

        f = tmp_path / "bad.mca"
        f.write_text("no colon", encoding="utf-8")
        diags = validate_file(f, raise_on_error=False)
        assert len(diags) == 1
        assert diags[0].code == "missing_colon"


class TestValidatorSeverity:
    def test_error_severity(self):
        from core.validator import Severity

        assert Severity.ERROR.value == "ERROR"
        assert Severity.WARNING.value == "WARNING"
        assert Severity.INFO.value == "INFO"

    def test_diagnostic_fields(self):
        from core.validator import Diagnostic, Severity

        d = Diagnostic(
            line=0,
            start_char=0,
            end_char=5,
            message="test",
            severity=Severity.ERROR,
            code="test_code",
        )
        assert d.line == 0
        assert d.start_char == 0
        assert d.end_char == 5
        assert d.message == "test"
        assert d.severity == Severity.ERROR
        assert d.code == "test_code"
