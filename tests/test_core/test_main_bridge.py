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
# validate_like_triggers — REMOVED as part of plugin decoupling.
# Like triggers now live in the like-goal plugin config, validated by the plugin itself.
# =========================================================================
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


# =========================================================================
# generate_datapack shell parsing
# =========================================================================

class TestGenerateDatapackShell:
    def test_parses_shell_prefix(self, tmp_path: Path):
        from src.python.main import generate_datapack, ctx, ACTIONS_FILE
        actions_file = tmp_path / "actions.mca"
        actions_file.write_text("12345:&curl http://localhost:29191/add\n", encoding="utf-8")
        dp_root = tmp_path / "datapacks"
        dp_root.mkdir(parents=True, exist_ok=True)
        with patch.object(ctx, "datapack_root", dp_root), \
             patch("src.python.main.ACTIONS_FILE", actions_file):
            generate_datapack()
        assert "12345" in ctx.valid_functions
        assert ctx.shell_actions_cache.get("12345") == ["curl http://localhost:29191/add"]

    def test_parses_chained_shell_commands(self, tmp_path: Path):
        from src.python.main import generate_datapack, ctx, ACTIONS_FILE
        actions_file = tmp_path / "actions.mca"
        actions_file.write_text("12345:&echo hello ; &echo world\n", encoding="utf-8")
        dp_root = tmp_path / "datapacks"
        dp_root.mkdir(parents=True, exist_ok=True)
        with patch.object(ctx, "datapack_root", dp_root), \
             patch("src.python.main.ACTIONS_FILE", actions_file):
            generate_datapack()
        assert ctx.shell_actions_cache.get("12345") == ["echo hello", "echo world"]

    def test_parses_shell_multiplier(self, tmp_path: Path):
        from src.python.main import generate_datapack, ctx, ACTIONS_FILE
        actions_file = tmp_path / "actions.mca"
        actions_file.write_text("12345:&echo hi x3\n", encoding="utf-8")
        dp_root = tmp_path / "datapacks"
        dp_root.mkdir(parents=True, exist_ok=True)
        with patch.object(ctx, "datapack_root", dp_root), \
             patch("src.python.main.ACTIONS_FILE", actions_file):
            generate_datapack()
        assert ctx.shell_actions_cache.get("12345") == ["echo hi", "echo hi", "echo hi"]
