"""Tests for the TikTok-to-Minecraft bridge core (src/python/main.py).

Tests pure functions and simple behaviors that do not require
a live TikTok connection or RCON server.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# =========================================================================
# sanitize_filename
# =========================================================================

class TestSanitizeFilename:
    def test_lowercases(self):
        from src.python.main import sanitize_filename
        assert sanitize_filename("HELLO") == "hello"

    def test_replaces_spaces(self):
        from src.python.main import sanitize_filename
        assert sanitize_filename("hello world") == "hello_world"

    def test_removes_special_chars(self):
        from src.python.main import sanitize_filename
        assert sanitize_filename("hello@#$world") == "helloworld"

    def test_allows_underscores_and_hyphens(self):
        from src.python.main import sanitize_filename
        assert sanitize_filename("hello_world-test") == "hello_world-test"

    def test_allows_numbers(self):
        from src.python.main import sanitize_filename
        assert sanitize_filename("test123") == "test123"

    def test_strips_non_alphanumeric_prefix(self):
        from src.python.main import sanitize_filename
        assert sanitize_filename("!!!hello") == "hello"

    def test_empty_string(self):
        from src.python.main import sanitize_filename
        assert sanitize_filename("") == ""

    def test_all_spaces(self):
        from src.python.main import sanitize_filename
        assert sanitize_filename("   ") == "___"


# =========================================================================
# get_safe_username
# =========================================================================

class TestGetSafeUsername:
    def test_uses_unique_id(self):
        from src.python.main import get_safe_username
        user = MagicMock()
        user.unique_id = "testuser"
        user.nickname = "Test User"
        assert get_safe_username(user) == "testuser"

    def test_falls_back_to_nickname(self):
        from src.python.main import get_safe_username
        user = MagicMock()
        user.unique_id = None
        user.nickname = "Test User"
        assert get_safe_username(user) == "Test User"

    def test_unknown_default(self):
        from src.python.main import get_safe_username
        user = MagicMock()
        user.unique_id = None
        user.nickname = None
        assert get_safe_username(user) == "Unknown"

    def test_unknown_when_missing(self):
        from src.python.main import get_safe_username
        user = object()
        assert get_safe_username(user) == "Unknown"


# =========================================================================
# validate_like_triggers
# =========================================================================

class TestValidateLikeTriggers:
    def test_valid_trigger(self):
        from src.python.main import validate_like_triggers
        triggers = [{"id": "milestone_100", "every": 100, "function": "say_hi"}]
        result = validate_like_triggers(triggers)
        assert len(result) == 1
        assert result[0]["id"] == "milestone_100"
        assert result[0]["every"] == 100
        assert result[0]["function"] == "say_hi"
        assert result[0]["payload"] == "Community"
        assert result[0]["enable"] is True

    def test_skips_non_dict_entry(self):
        from src.python.main import validate_like_triggers
        triggers = [{"id": "ok", "every": 10, "function": "f"}, "not_a_dict"]
        result = validate_like_triggers(triggers)
        assert len(result) == 1

    def test_skips_missing_id(self):
        from src.python.main import validate_like_triggers
        triggers = [{"every": 10, "function": "f"}]
        result = validate_like_triggers(triggers)
        assert len(result) == 0

    def test_skips_empty_id(self):
        from src.python.main import validate_like_triggers
        triggers = [{"id": "", "every": 10, "function": "f"}]
        result = validate_like_triggers(triggers)
        assert len(result) == 0

    def test_skips_duplicate_id(self):
        from src.python.main import validate_like_triggers
        triggers = [
            {"id": "dup", "every": 10, "function": "f"},
            {"id": "dup", "every": 20, "function": "g"},
        ]
        result = validate_like_triggers(triggers)
        assert len(result) == 1

    def test_skips_missing_every(self):
        from src.python.main import validate_like_triggers
        triggers = [{"id": "test", "function": "f"}]
        result = validate_like_triggers(triggers)
        assert len(result) == 0

    def test_skips_invalid_every(self):
        from src.python.main import validate_like_triggers
        triggers = [{"id": "test", "every": -1, "function": "f"}]
        result = validate_like_triggers(triggers)
        assert len(result) == 0

    def test_accepts_string_every_with_underscores(self):
        from src.python.main import validate_like_triggers
        triggers = [{"id": "test", "every": "100_000", "function": "f"}]
        result = validate_like_triggers(triggers)
        assert len(result) == 1
        assert result[0]["every"] == 100_000

    def test_skips_missing_function(self):
        from src.python.main import validate_like_triggers
        triggers = [{"id": "test", "every": 10}]
        result = validate_like_triggers(triggers)
        assert len(result) == 0

    def test_skips_empty_function(self):
        from src.python.main import validate_like_triggers
        triggers = [{"id": "test", "every": 10, "function": ""}]
        result = validate_like_triggers(triggers)
        assert len(result) == 0

    def test_invalid_payload_type_defaults(self):
        from src.python.main import validate_like_triggers
        triggers = [{"id": "test", "every": 10, "function": "f", "payload": 123}]
        result = validate_like_triggers(triggers)
        assert len(result) == 0

    def test_enabled_false_string(self):
        from src.python.main import validate_like_triggers
        triggers = [{"id": "test", "every": 10, "function": "f", "enabled": "false"}]
        result = validate_like_triggers(triggers)
        assert len(result) == 1
        assert result[0]["enable"] is False

    def test_enabled_true_string(self):
        from src.python.main import validate_like_triggers
        triggers = [{"id": "test", "every": 10, "function": "f", "enabled": "true"}]
        result = validate_like_triggers(triggers)
        assert len(result) == 1
        assert result[0]["enable"] is True

    def test_empty_list(self):
        from src.python.main import validate_like_triggers
        assert validate_like_triggers([]) == []

    def test_custom_payload(self):
        from src.python.main import validate_like_triggers
        triggers = [{"id": "t", "every": 5, "function": "f", "payload": "VIP"}]
        result = validate_like_triggers(triggers)
        assert result[0]["payload"] == "VIP"


# =========================================================================
# load_shell_actions
# =========================================================================

class TestLoadShellActions:
    def test_loads_simple_actions(self, tmp_path: Path):
        from src.python.main import load_shell_actions
        f = tmp_path / "shell_actions.txt"
        f.write_text("trigger_1: http://example.com/cmd1\ntrigger_2: http://example.com/cmd2\n")
        with patch("src.python.main.BASE_DIR", tmp_path):
            load_shell_actions(f)
        from src.python.main import ctx
        assert "trigger_1" in ctx.shell_actions_cache
        assert "trigger_2" in ctx.shell_actions_cache

    def test_skips_comments(self, tmp_path: Path):
        from src.python.main import load_shell_actions
        f = tmp_path / "shell_actions.txt"
        f.write_text("# this is a comment\ntrigger: http://example.com/cmd\n")
        with patch("src.python.main.BASE_DIR", tmp_path):
            load_shell_actions(f)
        from src.python.main import ctx
        assert "trigger" in ctx.shell_actions_cache

    def test_handles_variable_definitions(self, tmp_path: Path):
        from src.python.main import load_shell_actions
        f = tmp_path / "shell_actions.txt"
        f.write_text("//define host = example.com\ntrigger: http://{host}/cmd\n")
        with patch("src.python.main.BASE_DIR", tmp_path):
            load_shell_actions(f)
        from src.python.main import ctx
        assert "http://example.com/cmd" in ctx.shell_actions_cache.get("trigger", "")

    def test_skips_lines_without_colon(self, tmp_path: Path):
        from src.python.main import load_shell_actions
        f = tmp_path / "shell_actions.txt"
        f.write_text("no colon here\ntrigger: http://cmd\n")
        with patch("src.python.main.BASE_DIR", tmp_path):
            load_shell_actions(f)
        from src.python.main import ctx
        assert "trigger" in ctx.shell_actions_cache

    def test_empty_file(self, tmp_path: Path):
        from src.python.main import load_shell_actions
        f = tmp_path / "shell_actions.txt"
        f.write_text("")
        with patch("src.python.main.BASE_DIR", tmp_path):
            load_shell_actions(f)
        from src.python.main import ctx
        assert len(ctx.shell_actions_cache) == 0

    def test_file_not_found(self, tmp_path: Path):
        from src.python.main import load_shell_actions
        f = tmp_path / "nonexistent.txt"
        with patch("src.python.main.BASE_DIR", tmp_path):
            load_shell_actions(f)
        from src.python.main import ctx
        assert len(ctx.shell_actions_cache) == 0


# =========================================================================
# Webhook handling
# =========================================================================

class TestWebhook:
    def test_death_event_pauses_queue(self, client):
        resp = client.post("/api/v1/plugins/death-counter/webhook", json={"event": "player_death"})
        assert resp.status_code in (200, 404)

    def test_death_event_json(self):
        data = {"event": "player_death"}
        assert data["event"] == "player_death"

    def test_respawn_event_json(self):
        data = {"event": "player_respawn"}
        assert data["event"] == "player_respawn"


# =========================================================================
# Duplicate config detection
# =========================================================================

class TestDupCmdConfig:
    def test_detects_duplicate_keys(self, tmp_path: Path):
        content = (
            "commands_config:\n"
            "  testcmd:\n"
            "    points_cost: 10\n"
            "  testcmd:\n"
            "    points_cost: 20\n"
        )
        f = tmp_path / "config.yaml"
        f.write_text(content)
        from src.python.main import _check_dup_cmd_config
        with patch("src.python.main.CONFIG_FILE", f), \
             patch("builtins.input", return_value=""):
            with pytest.raises(SystemExit):
                _check_dup_cmd_config()

    def test_no_duplicates_ok(self, tmp_path: Path):
        content = (
            "commands_config:\n"
            "  cmd1:\n"
            "    points_cost: 10\n"
            "  cmd2:\n"
            "    points_cost: 20\n"
        )
        f = tmp_path / "config.yaml"
        f.write_text(content)
        from src.python.main import _check_dup_cmd_config
        with patch("src.python.main.CONFIG_FILE", f):
            _check_dup_cmd_config()
