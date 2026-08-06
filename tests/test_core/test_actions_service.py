"""Tests for the ActionsService parser and serializer."""

import pytest
from core.api.services.actions import ActionsService, _detect_prefix, _strip_prefix


class TestDetectPrefix:
    def test_vanilla(self):
        assert _detect_prefix("/say hi") == ("vanilla", {})

    def test_rcon(self):
        assert _detect_prefix("!cmd") == ("rcon", {})

    def test_script(self):
        assert _detect_prefix("$script") == ("script", {})

    def test_overlay(self):
        assert _detect_prefix(">>text") == ("overlay", {})

    def test_named_overlay(self):
        assert _detect_prefix("@name>>text") == ("named_overlay", {"overlay_name": "name"})

    def test_shell(self):
        assert _detect_prefix("&curl http://localhost") == ("shell", {})


class TestStripPrefix:
    def test_shell(self):
        assert _strip_prefix("&curl http://localhost", "shell", {}) == "curl http://localhost"


class TestParse:
    def test_parses_shell_command(self):
        svc = ActionsService()
        triggers = svc.parse(text="12345:&curl http://localhost:29191/add")
        assert len(triggers) == 1
        assert triggers[0]["commands"][0]["type"] == "shell"
        assert triggers[0]["commands"][0]["command"] == "curl http://localhost:29191/add"

    def test_parses_shell_multiplier(self):
        svc = ActionsService()
        triggers = svc.parse(text="12345:&echo hi x3")
        assert triggers[0]["commands"][0]["type"] == "shell"
        assert triggers[0]["commands"][0]["command"] == "echo hi"
        assert triggers[0]["commands"][0]["multiplier"] == 3

    def test_parses_chained_shell_commands(self):
        svc = ActionsService()
        triggers = svc.parse(text="12345:&echo hello ; &echo world")
        assert len(triggers[0]["commands"]) == 2
        assert triggers[0]["commands"][0]["type"] == "shell"
        assert triggers[0]["commands"][0]["command"] == "echo hello"
        assert triggers[0]["commands"][1]["command"] == "echo world"


class TestValidateTriggers:
    def test_duplicate_enabled_triggers_returns_error(self):
        svc = ActionsService()
        triggers = [
            {"name": "like_2", "enabled": True, "type": "Event", "commands": []},
            {"name": "like_2", "enabled": True, "type": "Event", "commands": []},
        ]
        diags = svc.validate_triggers(triggers)
        assert any(d["code"] == "DUPLICATE_TRIGGER" for d in diags)

    def test_duplicate_disabled_trigger_allowed(self):
        svc = ActionsService()
        triggers = [
            {"name": "like_2", "enabled": True, "type": "Event", "commands": []},
            {"name": "like_2", "enabled": False, "type": "Event", "commands": []},
        ]
        diags = svc.validate_triggers(triggers)
        assert not any(d["code"] == "DUPLICATE_TRIGGER" for d in diags)

    def test_case_insensitive_duplicate_detection(self):
        svc = ActionsService()
        triggers = [
            {"name": "like_2", "enabled": True, "type": "Event", "commands": []},
            {"name": "LIKE_2", "enabled": True, "type": "Event", "commands": []},
        ]
        diags = svc.validate_triggers(triggers)
        assert any(d["code"] == "DUPLICATE_TRIGGER" for d in diags)

    def test_different_names_allowed(self):
        svc = ActionsService()
        triggers = [
            {"name": "like_2", "enabled": True, "type": "Event", "commands": []},
            {"name": "like_3", "enabled": True, "type": "Event", "commands": []},
        ]
        diags = svc.validate_triggers(triggers)
        assert not any(d["code"] == "DUPLICATE_TRIGGER" for d in diags)
    def test_serializes_shell_command(self):
        svc = ActionsService()
        raw = svc.serialize([{
            "name": "12345",
            "enabled": True,
            "type": "Gift",
            "commands": [{
                "type": "shell",
                "command": "curl http://localhost",
                "multiplier": 1,
                "title": "",
                "subtitle": "",
                "duration": 3,
                "overlay_name": "default",
            }],
        }])
        assert "12345:&curl http://localhost" in raw

    def test_serializes_shell_with_multiplier(self):
        svc = ActionsService()
        raw = svc.serialize([{
            "name": "12345",
            "enabled": True,
            "type": "Gift",
            "commands": [{
                "type": "shell",
                "command": "echo hi",
                "multiplier": 3,
                "title": "",
                "subtitle": "",
                "duration": 3,
                "overlay_name": "default",
            }],
        }])
        assert "12345:&echo hi x3" in raw
