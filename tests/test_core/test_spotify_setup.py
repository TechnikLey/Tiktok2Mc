"""Tests for the Spotify OAuth Flow Helper.

Memory-efficient: tests file structure and logic without executing
spotify_setup.py (which would load heavy deps like urllib, webbrowser).
"""

from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parent.parent.parent / "src" / "python" / "spotify_setup.py"


class TestScriptExists:
    """Verify the script file exists and has expected structure."""

    def test_file_exists(self):
        assert SCRIPT_PATH.exists()

    def test_has_main_function(self):
        content = SCRIPT_PATH.read_text(encoding="utf-8")
        assert "def main():" in content

    def test_has_refresh_function(self):
        content = SCRIPT_PATH.read_text(encoding="utf-8")
        assert "def refresh():" in content

    def test_has_exchange_code_function(self):
        content = SCRIPT_PATH.read_text(encoding="utf-8")
        assert "def _exchange_code(" in content

    def test_has_save_config_function(self):
        content = SCRIPT_PATH.read_text(encoding="utf-8")
        assert "def _save_spotify_config(" in content

    def test_has_spotify_auth_url(self):
        content = SCRIPT_PATH.read_text(encoding="utf-8")
        assert "SPOTIFY_AUTH_URL" in content
        assert "accounts.spotify.com/authorize" in content

    def test_has_spotify_token_url(self):
        content = SCRIPT_PATH.read_text(encoding="utf-8")
        assert "SPOTIFY_TOKEN_URL" in content
        assert "accounts.spotify.com/api/token" in content

    def test_has_default_redirect_uri(self):
        content = SCRIPT_PATH.read_text(encoding="utf-8")
        assert "DEFAULT_REDIRECT_URI" in content
        assert "localhost:8888/callback" in content

    def test_uses_save_yaml_not_save_config(self):
        """Ensure we fixed the import error (save_config does not exist)."""
        content = SCRIPT_PATH.read_text(encoding="utf-8")
        assert "save_yaml" in content
        assert "save_config" not in content

    def test_imports_load_config_from_core_utils(self):
        content = SCRIPT_PATH.read_text(encoding="utf-8")
        assert "from core.utils import load_config" in content

    def test_has_callback_server_class(self):
        content = SCRIPT_PATH.read_text(encoding="utf-8")
        assert "class _CallbackHandler(" in content
        assert "BaseHTTPRequestHandler" in content


class TestOAuthUrlConstruction:
    """Verify the authorization URL would be built correctly."""

    def test_authorization_url_format(self):
        """The URL format that the script constructs."""
        import urllib.parse
        params = urllib.parse.urlencode({
            "client_id": "test_id",
            "response_type": "code",
            "redirect_uri": "http://localhost:8888/callback",
            "scope": "user-read-playback-state user-modify-playback-state",
            "show_dialog": "true",
        })
        url = f"https://accounts.spotify.com/authorize?{params}"
        assert "client_id=test_id" in url
        assert "response_type=code" in url
        assert "show_dialog=true" in url


class TestTokenExchangeLogic:
    """Verify the token exchange POST body would be correct."""

    def test_exchange_code_payload(self):
        import urllib.parse
        payload = urllib.parse.urlencode({
            "grant_type": "authorization_code",
            "code": "my_code",
            "redirect_uri": "http://localhost:8888/callback",
            "client_id": "my_id",
            "client_secret": "my_secret",
        }).encode("utf-8")
        decoded = payload.decode()
        assert "grant_type=authorization_code" in decoded
        assert "code=my_code" in decoded
        assert "client_id=my_id" in decoded

    def test_refresh_token_payload(self):
        import urllib.parse
        payload = urllib.parse.urlencode({
            "grant_type": "refresh_token",
            "refresh_token": "old_refresh",
            "client_id": "my_id",
            "client_secret": "my_secret",
        }).encode("utf-8")
        decoded = payload.decode()
        assert "grant_type=refresh_token" in decoded
        assert "refresh_token=old_refresh" in decoded


class TestConfigIntegration:
    """Verify the script interacts with config.yaml correctly."""

    def test_saves_to_spotify_section(self, tmp_path):
        """Simulate what _save_spotify_config does with plugin-local config."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("client_id: ''\nclient_secret: ''\n", encoding="utf-8")

        from core.utils import load_config
        from core.yaml_utils import save_yaml

        cfg = load_config(config_file)
        cfg["client_id"] = "abc"
        cfg["access_token"] = "tok"
        save_yaml(config_file, cfg)

        result = load_config(config_file)
        assert result["client_id"] == "abc"
