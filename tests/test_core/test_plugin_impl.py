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
            lambda d: {"decrement_on_death": False, **cfg_override},
        )
        monkeypatch.setattr("core.base_plugin.get_base_dir", lambda: tmp_path)
        return WinCounterPlugin()

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

    def test_death_decrement_when_enabled(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch, decrement_on_death=True)
        p._manager.wins = 5
        p._on_death({})
        assert p._manager.wins == 4

    def test_death_no_decrement_when_disabled(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch, decrement_on_death=False)
        p._manager.wins = 5
        p._on_death({})
        assert p._manager.wins == 5

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
        return DeathCounterPlugin()

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
        return LikeGoalPlugin()

    def test_initial_state(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)
        data = p._manager.get_data()
        assert data["likes"] == 0
        assert data["goal"] == 100

    def test_add_likes(self, tmp_path, monkeypatch):
        p = self._make_plugin(tmp_path, monkeypatch)
        p._on_tiktok_event({"event_type": "tiktok.like", "data": {"delta": 50}})
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
