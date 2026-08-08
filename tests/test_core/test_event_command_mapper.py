"""Tests for EventCommandMapper.

Tests the mapping logic without relying on a running event bus.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest


class TestEventCommandMapperConfig:
    """Config loading from YAML."""

    def test_load_empty_config(self, tmp_path, monkeypatch):
        from core.event_command_mapper import EventCommandMapper

        monkeypatch.setattr("core.event_command_mapper.get_root_dir", lambda: tmp_path)
        mapper = EventCommandMapper()
        mappings = mapper._load_mappings()
        assert mappings == {}

    def test_load_valid_config(self, tmp_path, monkeypatch):
        from core.event_command_mapper import EventCommandMapper

        data_dir = tmp_path / "data"
        data_dir.mkdir()
        config_file = data_dir / "event_commands.yaml"
        config_file.write_text(
            "event_commands:\n"
            "  minecraft.player_death:\n"
            "    - target: timer\n"
            "      command: pause\n"
            "  timer.zero:\n"
            "    - target: win-counter\n"
            "      command: add_win\n"
            "      args:\n"
            "        amount: 1\n",
            encoding="utf-8",
        )

        monkeypatch.setattr("core.event_command_mapper.get_root_dir", lambda: tmp_path)
        mapper = EventCommandMapper()
        mappings = mapper._load_mappings()

        assert "minecraft.player_death" in mappings
        assert len(mappings["minecraft.player_death"]) == 1
        assert mappings["minecraft.player_death"][0]["target"] == "timer"
        assert mappings["minecraft.player_death"][0]["command"] == "pause"

        assert "timer.zero" in mappings
        assert mappings["timer.zero"][0]["args"]["amount"] == 1


class TestEventCommandMapperDispatch:
    """Command dispatch logic (command_queue mocked)."""

    @pytest.fixture
    def mapper(self, tmp_path, monkeypatch):
        from core.event_command_mapper import EventCommandMapper

        data_dir = tmp_path / "data"
        data_dir.mkdir()
        config_file = data_dir / "event_commands.yaml"
        config_file.write_text(
            "event_commands:\n"
            "  minecraft.player_death:\n"
            "    - target: timer\n"
            "      command: pause\n"
            "    - target: spotify-control\n"
            "      command: pause\n"
            "  timer.zero:\n"
            "    - target: win-counter\n"
            "      command: add_win\n"
            "      args:\n"
            "        amount: 1\n",
            encoding="utf-8",
        )

        monkeypatch.setattr("core.event_command_mapper.get_root_dir", lambda: tmp_path)
        return EventCommandMapper()

    def test_dispatches_matching_event(self, mapper, monkeypatch):
        enqueued = []

        def fake_enqueue(plugin_name, command, **kwargs):
            enqueued.append({"target": plugin_name, "command": command, "args": kwargs})
            return "fake-id"

        monkeypatch.setattr("core.api.plugin_overlay.command_queue", MagicMock(enqueue=fake_enqueue))
        mapper._dispatch("minecraft.player_death", {"player": "Steve"})

        assert len(enqueued) == 2
        assert enqueued[0]["target"] == "timer"
        assert enqueued[0]["command"] == "pause"
        assert enqueued[1]["target"] == "spotify-control"

    def test_dispatches_with_args(self, mapper, monkeypatch):
        enqueued = []

        def fake_enqueue(plugin_name, command, **kwargs):
            enqueued.append({"target": plugin_name, "command": command, "args": kwargs})
            return "fake-id"

        monkeypatch.setattr("core.api.plugin_overlay.command_queue", MagicMock(enqueue=fake_enqueue))
        mapper._dispatch("timer.zero", {})

        assert len(enqueued) == 1
        assert enqueued[0]["target"] == "win-counter"
        assert enqueued[0]["command"] == "add_win"
        assert enqueued[0]["args"]["amount"] == 1

    def test_ignores_unknown_event(self, mapper, monkeypatch):
        enqueued = []

        def fake_enqueue(plugin_name, command, **kwargs):
            enqueued.append({"target": plugin_name, "command": command, "args": kwargs})
            return "fake-id"

        monkeypatch.setattr("core.api.plugin_overlay.command_queue", MagicMock(enqueue=fake_enqueue))
        mapper._dispatch("unknown.event", {})

        assert len(enqueued) == 0

    def test_skips_bad_mapping(self, mapper, monkeypatch):
        """Mappings missing target or command are skipped with a warning."""

        from core.yaml_utils import save_yaml

        # Add a broken mapping directly
        data_dir = Path(mapper._config_path()).parent
        cfg = {"event_commands": {"bad.event": [{"target": "timer"}]}}
        save_yaml(data_dir / "event_commands.yaml", cfg)

        enqueued = []
        def fake_enqueue(plugin_name, command, **kwargs):
            enqueued.append({"target": plugin_name, "command": command, "args": kwargs})
            return "fake-id"

        monkeypatch.setattr("core.api.plugin_overlay.command_queue", MagicMock(enqueue=fake_enqueue))
        mapper._dispatch("bad.event", {})

        assert len(enqueued) == 0  # skipped because command is missing


class TestEventCommandMapperLifecycle:
    """Start / stop lifecycle."""

    def test_start_creates_config_if_missing(self, tmp_path, monkeypatch):
        from core.event_command_mapper import EventCommandMapper

        monkeypatch.setattr("core.event_command_mapper.get_root_dir", lambda: tmp_path)
        mapper = EventCommandMapper()
        # _ensure_config_file should create data/event_commands.yaml
        mapper._ensure_config_file()
        assert (tmp_path / "data" / "event_commands.yaml").exists()

    def test_singleton(self):
        from core.event_command_mapper import get_event_command_mapper

        m1 = get_event_command_mapper()
        m2 = get_event_command_mapper()
        assert m1 is m2
