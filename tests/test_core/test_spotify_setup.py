"""Tests for the Spotify OAuth Flow Helper.

These tests verify the script structure, config loading/saving,
and the OAuth URL construction without making real HTTP calls.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


SPOTIFY_SETUP_PATH = Path(__file__).resolve().parent.parent.parent / "src" / "python" / "spotify_setup.py"


@pytest.fixture(scope="module")
def spotify_setup_module():
    """Import spotify_setup.py with mocked dependencies."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("spotify_setup", SPOTIFY_SETUP_PATH)
    module = importlib.util.module_from_spec(spec)

    # Mock dependencies before executing
    with patch.object(sys, "path", sys.path + [str(SPOTIFY_SETUP_PATH.parent.parent)]):
        spec.loader.exec_module(module)
    return module


class TestScriptStructure:
    """Verify the script exists and has the expected functions."""

    def test_script_exists(self):
        assert SPOTIFY_SETUP_PATH.exists(), f"Script not found at {SPOTIFY_SETUP_PATH}"

    def test_has_main_function(self, spotify_setup_module):
        assert hasattr(spotify_setup_module, "main")
        assert callable(spotify_setup_module.main)

    def test_has_refresh_function(self, spotify_setup_module):
        assert hasattr(spotify_setup_module, "refresh")
        assert callable(spotify_setup_module.refresh)

    def test_has_config_functions(self, spotify_setup_module):
        assert hasattr(spotify_setup_module, "_load_spotify_config")
        assert hasattr(spotify_setup_module, "_save_spotify_config")
        assert hasattr(spotify_setup_module, "_exchange_code")
        assert hasattr(spotify_setup_module, "_refresh_token")


class TestOAuthUrlConstruction:
    """Test that the authorization URL is built correctly."""

    def test_spotify_auth_url_constant(self, spotify_setup_module):
        assert "accounts.spotify.com/authorize" in spotify_setup_module.SPOTIFY_AUTH_URL

    def test_token_url_constant(self, spotify_setup_module):
        assert "accounts.spotify.com/api/token" in spotify_setup_module.SPOTIFY_TOKEN_URL

    def test_default_redirect_uri(self, spotify_setup_module):
        assert spotify_setup_module.DEFAULT_REDIRECT_URI == "http://localhost:8888/callback"


class TestConfigFunctions:
    """Test config loading and saving with mocked filesystem."""

    def test_load_spotify_config_reads_nested_dict(self, tmp_path, spotify_setup_module):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            "config_version: '1.0'\nspotify:\n  enabled: true\n  client_id: abc123\n",
            encoding="utf-8",
        )

        with patch.object(spotify_setup_module, "_get_config_file", return_value=config_file):
            with patch.object(spotify_setup_module, "load_config", return_value={
                "config_version": "1.0",
                "spotify": {"enabled": True, "client_id": "abc123"},
            }):
                result = spotify_setup_module._load_spotify_config()
                assert result["enabled"] is True
                assert result["client_id"] == "abc123"

    def test_load_spotify_config_returns_empty_when_missing(self, spotify_setup_module):
        with patch.object(spotify_setup_module, "load_config", return_value={}):
            result = spotify_setup_module._load_spotify_config()
            assert result == {}

    def test_save_spotify_config_updates_nested(self, tmp_path, spotify_setup_module):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("config_version: '1.0'\n", encoding="utf-8")

        saved = {}
        def mock_save_config(path, data):
            saved["path"] = str(path)
            saved["data"] = data

        with patch.object(spotify_setup_module, "_get_config_file", return_value=config_file):
            with patch.object(spotify_setup_module, "load_config", return_value={"config_version": "1.0"}):
                with patch.object(spotify_setup_module, "save_yaml", side_effect=mock_save_config):
                    spotify_setup_module._save_spotify_config({"enabled": True, "client_id": "xyz"})

        assert saved["data"]["spotify"]["enabled"] is True
        assert saved["data"]["spotify"]["client_id"] == "xyz"


class TestTokenExchange:
    """Test the token exchange and refresh logic."""

    def test_exchange_code_posts_correct_params(self, spotify_setup_module, monkeypatch):
        captured = {}
        def mock_urlopen(req, timeout=None):
            captured["url"] = req.full_url
            captured["data"] = req.data.decode() if req.data else ""
            m = MagicMock()
            m.read.return_value = json.dumps({"access_token": "tok", "refresh_token": "ref", "expires_in": 3600}).encode()
            m.__enter__ = MagicMock(return_value=m)
            m.__exit__ = MagicMock(return_value=None)
            return m

        monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)
        result = spotify_setup_module._exchange_code(
            "my_code", "my_id", "my_secret", "http://localhost:8888/callback"
        )
        assert result is not None
        assert "grant_type=authorization_code" in captured["data"]
        assert "code=my_code" in captured["data"]
        assert "client_id=my_id" in captured["data"]

    def test_refresh_token_posts_correct_params(self, spotify_setup_module, monkeypatch):
        captured = {}
        def mock_urlopen(req, timeout=None):
            captured["data"] = req.data.decode() if req.data else ""
            m = MagicMock()
            m.read.return_value = json.dumps({"access_token": "new_tok", "expires_in": 3600}).encode()
            m.__enter__ = MagicMock(return_value=m)
            m.__exit__ = MagicMock(return_value=None)
            return m

        monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)
        result = spotify_setup_module._refresh_token(
            "old_refresh", "my_id", "my_secret"
        )
        assert result is not None
        assert "grant_type=refresh_token" in captured["data"]
        assert "refresh_token=old_refresh" in captured["data"]


class TestPromptInput:
    """Test the CLI prompt helper."""

    def test_prompt_input_returns_value(self, spotify_setup_module, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda _: "test_value")
        assert spotify_setup_module._prompt_input("Label") == "test_value"

    def test_prompt_input_strips_whitespace(self, spotify_setup_module, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda _: "  value  ")
        assert spotify_setup_module._prompt_input("Label") == "value"

    def test_prompt_input_retries_on_empty(self, spotify_setup_module, monkeypatch):
        calls = iter(["", "", "valid"])
        monkeypatch.setattr("builtins.input", lambda _: next(calls))
        assert spotify_setup_module._prompt_input("Label") == "valid"

    def test_prompt_input_optional_returns_empty(self, spotify_setup_module, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda _: "")
        assert spotify_setup_module._prompt_input("Label", required=False) == ""
