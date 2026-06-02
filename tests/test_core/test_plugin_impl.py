"""Tests for WinCounterPlugin, DeathCounterPlugin, LikeGoalPlugin, SpotifyControlPlugin.

All plugins have been refactored to BasePlugin — these tests verify
command handlers, state logic, and overlay HTML without HTTP calls.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _patch_argv(monkeypatch):
    monkeypatch.setattr(sys, "argv", [""])


class FakeArgs:
    gui_hidden = True


# =========================================================================
# WinCounterPlugin
# =========================================================================

class TestWinCounterPlugin:
    """WinCounter logic without HTTP."""

    def _make_plugin(self, tmp_path, monkeypatch, **cfg_override):
        from plugins.wincounter.main import WinCounterPlugin

        monkeypatch.setattr("core.base_plugin.parse_args", lambda: FakeArgs())
        monkeypatch.setattr(
            "core.base_plugin.load_plugin_config",
            lambda d: {"initial_needed": 10, **cfg_override},
        )
        monkeypatch.setattr("core.base_plugin.get_base_dir", lambda: tmp_path)
        p = WinCounterPlugin()
        p._data_dir = tmp_path / "data"
        p._data_dir.mkdir(parents=True, exist_ok=True)
        p._stats_file = p._data_dir / "stats.json"
        p._manager._stats_path = p._stats_file
        return p

    def test_initial_state(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)
        assert p._manager.wins == 0
        assert p._manager.needed == 10

    def test_add_win(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)
        p._on_add_win({"amount": 3})
        assert p._manager.wins == 3

    def test_milestone_rollover(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)
        p._manager.wins = 9
        p._on_add_win({"amount": 3})
        assert p._manager.wins == 2  # 12 - 10 = 2
        assert p._manager.needed == 20  # next milestone

    def test_remove_win(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)
        p._on_add_win({"amount": 5})
        p._on_remove_win({"amount": 2})
        assert p._manager.wins == 3

    def test_remove_win_record_low(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)
        p._manager.wins = 2
        p._on_remove_win({"amount": 5})
        assert p._manager.record_low == -3

    def test_save_dims(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)
        saved = {}
        monkeypatch.setattr(p, "save_window_state", lambda w, h: saved.update({"w": w, "h": h}))
        p._on_save_dims({"width": 800, "height": 600})
        assert saved["w"] == 800
        assert saved["h"] == 600

    def test_stats_persist(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)
        p._manager.add(5)
        assert p._stats_file.exists()

    def test_overlay_html_contains_plugin_name(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)
        html = p.get_overlay_html()
        assert "win-counter" in html

    def test_add_win_no_milestone_signal(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)
        p._manager.wins = 3
        signals = []
        monkeypatch.setattr(p, "api_post", lambda path, data: signals.append(data))
        p._on_add_win({"amount": 1})
        assert p._manager.wins == 4
        assert not any(s.get("type") == "win.milestone" for s in signals)

    def test_add_win_triggers_milestone_signal(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)
        p._manager.wins = 9
        signals = []
        monkeypatch.setattr(p, "api_post", lambda path, data: signals.append(data))
        p._on_add_win({"amount": 3})
        assert p._manager.wins == 2
        assert p._manager.needed == 20
        assert any(s.get("type") == "win.milestone" for s in signals)

    def test_remove_win_no_record_low_signal(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)
        p._manager.record_low = -10
        p._manager.wins = 0
        signals = []
        monkeypatch.setattr(p, "api_post", lambda path, data: signals.append(data))
        p._on_remove_win({"amount": 1})
        assert not any(s.get("type") == "win.record_low" for s in signals)

    def test_remove_win_triggers_record_low(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)
        p._manager.record_low = 0
        signals = []
        monkeypatch.setattr(p, "api_post", lambda path, data: signals.append(data))
        p._on_remove_win({"amount": 5})
        assert p._manager.record_low == -5
        assert any(s.get("type") == "win.record_low" for s in signals)

    def test_negative_wins(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)
        p._on_remove_win({"amount": 3})
        data = p._manager.get_data()
        assert data["wins"] == -3
        assert data["record_low"] == -3

    def test_save_dims_partial_args(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)
        saved = {}
        monkeypatch.setattr(p, "save_window_state", lambda w, h: saved.update({"w": w, "h": h}))
        p._on_save_dims({})
        assert saved["w"] == 600
        assert saved["h"] == 300

    def test_state_contains_all_fields(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)
        state = p.get_state()
        assert "wins" in state
        assert "needed" in state
        assert "record_low" in state
        assert "win_color" in state


# =========================================================================
# DeathCounterPlugin
# =========================================================================

class TestDeathCounterPlugin:
    """DeathCounter logic without HTTP."""

    def _make_plugin(self, tmp_path, monkeypatch):
        from plugins.deathcounter.main import DeathCounterPlugin

        monkeypatch.setattr("core.base_plugin.parse_args", lambda: FakeArgs())
        monkeypatch.setattr("core.base_plugin.load_plugin_config", lambda d: {})
        monkeypatch.setattr("core.base_plugin.get_base_dir", lambda: tmp_path)
        p = DeathCounterPlugin()
        p._data_dir = tmp_path / "data"
        p._data_dir.mkdir(parents=True, exist_ok=True)
        p._manager._stats_path = p._data_dir / "deaths.json"
        return p

    def test_initial_state(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)
        assert p._manager.get_data()["deaths"] == 0

    def test_player_death(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)
        p._on_death({})
        assert p._manager.get_data()["deaths"] == 1

    def test_multiple_deaths(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)
        for _ in range(5):
            p._on_death({})
        assert p._manager.get_data()["deaths"] == 5

    def test_save_dims(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)
        saved = {}
        monkeypatch.setattr(p, "save_window_state", lambda w, h: saved.update({"w": w, "h": h}))
        p._on_save_dims({"width": 800, "height": 600})
        assert saved["w"] == 800
        assert saved["h"] == 600

    def test_overlay_html_contains_plugin_name(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)
        html = p.get_overlay_html()
        assert "death-counter" in html

    def test_add_death_handler(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)
        assert "add_death" in p._handlers
        p._on_add_death({"amount": 3})
        assert p._manager._count == 3

    def test_reset_handler(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)
        p._manager._count = 10
        p._milestones_sent.add(5)
        p._on_reset({})
        assert p._manager._count == 0
        assert len(p._milestones_sent) == 0

    def test_milestone_fires_signal(self, tmp_path, monkeypatch):
        from plugins.deathcounter.main import DeathCounterPlugin
        monkeypatch.setattr("core.base_plugin.parse_args", lambda: FakeArgs())
        monkeypatch.setattr(
            "core.base_plugin.load_plugin_config",
            lambda d: {"milestones": [5, 10], "signal_on": ["milestone"]},
        )
        monkeypatch.setattr("core.base_plugin.get_base_dir", lambda: tmp_path)
        p = DeathCounterPlugin()
        p._data_dir = tmp_path / "data"
        p._data_dir.mkdir(parents=True, exist_ok=True)
        p._manager._stats_path = p._data_dir / "deaths.json"
        signals = []
        monkeypatch.setattr(p, "api_post", lambda path, data: signals.append(data))
        p._on_death({"amount": 5})
        assert p._manager._count == 5
        assert any(s.get("type") == "death.milestone" for s in signals)

    def test_duplicate_milestone_suppressed(self, tmp_path, monkeypatch):
        from plugins.deathcounter.main import DeathCounterPlugin
        monkeypatch.setattr("core.base_plugin.parse_args", lambda: FakeArgs())
        monkeypatch.setattr(
            "core.base_plugin.load_plugin_config",
            lambda d: {"milestones": [5], "signal_on": ["milestone"]},
        )
        monkeypatch.setattr("core.base_plugin.get_base_dir", lambda: tmp_path)
        p = DeathCounterPlugin()
        p._data_dir = tmp_path / "data"
        p._data_dir.mkdir(parents=True, exist_ok=True)
        p._manager._stats_path = p._data_dir / "deaths.json"
        p._milestones_sent.add(5)
        signals = []
        monkeypatch.setattr(p, "api_post", lambda path, data: signals.append(data))
        p._on_death({"amount": 10})
        assert not any(s.get("type") == "death.milestone" for s in signals)

    def test_save_dims_partial_args(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)
        saved = {}
        monkeypatch.setattr(p, "save_window_state", lambda w, h: saved.update({"w": w, "h": h}))
        p._on_save_dims({})
        assert saved["w"] == 500
        assert saved["h"] == 400

    def test_state_after_death(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)
        p._on_death({"amount": 3})
        state = p.get_state()
        assert state["deaths"] == 3


# =========================================================================
# LikeGoalPlugin
# =========================================================================

class TestLikeGoalPlugin:
    """LikeGoal logic without HTTP."""

    def _make_plugin(self, tmp_path, monkeypatch, **cfg_override):
        from plugins.likegoal.main import LikeGoalPlugin

        monkeypatch.setattr("core.base_plugin.parse_args", lambda: FakeArgs())
        monkeypatch.setattr(
            "core.base_plugin.load_plugin_config",
            lambda d: {"initial_goal": 100, "goal_multiplier": 2, **cfg_override},
        )
        monkeypatch.setattr("core.base_plugin.get_base_dir", lambda: tmp_path)
        p = LikeGoalPlugin()
        p._data_dir = tmp_path / "data"
        p._data_dir.mkdir(parents=True, exist_ok=True)
        return p

    def test_initial_state(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)
        data = p._manager.get_data()
        assert data["likes"] == 0
        assert data["goal"] == 100

    def test_add_likes(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)
        p._on_add_likes({"amount": 50})
        assert p._manager.get_data()["likes"] == 50

    def test_milestone_rollover(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)
        p._manager.add(150)
        data = p._manager.get_data()
        assert data["likes"] == 50  # 150 - 100 = 50
        assert data["goal"] == 200  # 100 * 2 = 200

    def test_percent(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)
        p._manager.add(25)
        data = p._manager.get_data()
        assert data["percent"] == 25.0

    def test_overlay_html_contains_plugin_name(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)
        html = p.get_overlay_html()
        assert "like-goal" in html

    def test_reset_handler(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)
        p._manager.likes = 150
        p._on_reset({})
        data = p._manager.get_data()
        assert data["likes"] == 0
        assert data["goal"] == 100

    def test_add_likes_zero_delta(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)
        signals = []
        monkeypatch.setattr(p, "api_post", lambda path, data: signals.append(data))
        p._on_add_likes({"amount": 0})
        assert p._manager.get_data()["likes"] == 0
        assert not any(s.get("type") == "likegoal.progress" for s in signals)
        assert not any(s.get("type") == "likegoal.milestone" for s in signals)

    def test_progress_signal_no_milestone(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)
        signals = []
        monkeypatch.setattr(p, "api_post", lambda path, data: signals.append(data))
        p._on_add_likes({"amount": 25})
        assert p._manager.get_data()["likes"] == 25
        assert any(s.get("type") == "likegoal.progress" for s in signals)
        assert not any(s.get("type") == "likegoal.milestone" for s in signals)

    def test_milestone_signal_on_rollover(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)
        signals = []
        monkeypatch.setattr(p, "api_post", lambda path, data: signals.append(data))
        p._on_add_likes({"amount": 150})
        data = p._manager.get_data()
        assert data["likes"] == 50
        assert data["goal"] == 200
        assert any(s.get("type") == "likegoal.milestone" for s in signals)

    def test_multiplier_zero(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch, goal_multiplier=0)
        p._on_add_likes({"amount": 250})
        data = p._manager.get_data()
        assert data["likes"] == 0
        assert data["goal"] == 100

    def test_multiplier_one(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch, goal_multiplier=1, initial_goal=100)
        p._on_add_likes({"amount": 250})
        data = p._manager.get_data()
        assert data["likes"] == 150  # 250 - 100 = 150, then 150 < 200 so stops
        assert data["goal"] == 200  # 100 + 100 = 200

    def test_save_dims(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)
        saved = {}
        monkeypatch.setattr(p, "save_window_state", lambda w, h: saved.update({"w": w, "h": h}))
        p._on_save_dims({"width": 1920, "height": 1080})
        assert saved["w"] == 1920
        assert saved["h"] == 1080

    def test_initial_goal_zero_clamped(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch, initial_goal=0)
        assert p._initial_goal == 1
        assert p._manager.initial_goal == 1
        assert p._manager.goal == 1


# =========================================================================
# SpotifyControlPlugin
# =========================================================================

class TestSpotifyControlPlugin:
    """Spotify plugin command handlers without real HTTP."""

    def _make_plugin(self, tmp_path, monkeypatch, **cfg_override):
        from plugins.spotify.main import SpotifyControlPlugin

        monkeypatch.setattr("core.base_plugin.parse_args", lambda: FakeArgs())
        monkeypatch.setattr(
            "core.base_plugin.load_plugin_config",
            lambda d: {"client_id": "", "client_secret": "", **cfg_override},
        )
        monkeypatch.setattr("core.base_plugin.get_base_dir", lambda: tmp_path)
        return SpotifyControlPlugin()

    def test_initial_state(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)
        assert not p._client.is_authenticated

    def test_overlay_html_contains_plugin_name(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)
        html = p.get_overlay_html()
        assert "spotify-control" in html

    def test_state_returns_none_when_no_track(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)
        # _get_current_track_data returns None when not authenticated
        assert p._get_current_track_data() is None

    def test_search_and_play_parsing(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)
        # Just verify the parsing logic doesn't crash
        result = p._search_and_play("artist:Test - song:Song")
        assert result["status"] == "not_found"

    def test_command_handlers_registered(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)
        handlers = [
            "start_oauth", "oauth_callback", "play", "pause",
            "next", "previous", "volume", "volume_up", "volume_down",
            "shuffle", "repeat", "save", "playtrack", "comment",
        ]
        for cmd in handlers:
            assert cmd in p._handlers, f"Handler '{cmd}' not registered"

    def test_on_volume_no_level(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)
        prev = getattr(p._client, "set_volume", None)
        calls = []
        if prev:
            monkeypatch.setattr(p._client, "set_volume", lambda v: calls.append(v))
        p._on_volume({})
        assert len(calls) == 0

    def test_on_comment_empty_text(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)
        p._on_comment({})  # should not raise

    def test_on_comment_no_command(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)
        p._on_comment({"text": "   "})  # whitespace only, should not raise

    def test_search_and_play_empty(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)
        result = p._search_and_play("")
        assert result["status"] == "not_found"

    def test_search_and_play_artist_only(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)
        result = p._search_and_play("TestArtist - ")
        assert result["status"] == "not_found"

    def test_volume_up_down_registered(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)
        assert "volume_up" in p._handlers
        assert "volume_down" in p._handlers
