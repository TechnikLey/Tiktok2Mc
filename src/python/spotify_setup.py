#!/usr/bin/env python3
# ============================================================
# spotify_setup.py — Spotify OAuth Flow Helper
# ============================================================
# Walks users through Spotify Developer app creation, redirect
# URI setup, and token exchange. Saves tokens to config.yaml.
#
# Usage:
#     python src/python/spotify_setup.py
#
# After setup, enable the Spotify plugin and restart the tool.
# ============================================================

import sys
import time
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

# Ensure src/ is on sys.path so `import core.*` works
_src = Path(__file__).resolve().parent.parent
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from core.logger import (
    handle_unhandled_exception,
    initialize_logging,
    install_global_exception_hook,
)
from core.paths import get_root_dir
from core.secure_storage import secure_storage
from core.utils import load_config
from core.yaml_utils import save_yaml

log = initialize_logging(__name__)

SPOTIFY_AUTH_URL = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
DEFAULT_REDIRECT_URI = "http://localhost:8888/callback"


def _print_banner():
    print("=" * 60)
    print("  Spotify OAuth Setup Helper")
    print("  TikTok2MC")
    print("=" * 60)
    print()


def _print_instructions():
    print("""Step 1: Create a Spotify Developer App
1. Visit  https://developer.spotify.com/dashboard
2. Log in with your Spotify account
3. Click "Create app"
4. Fill in:
   - App name: TikTok2MC (or whatever you like)
   - Redirect URI: http://localhost:8888/callback
   - Which API/SDKs are you planning to use?  Web API
5. Click "Settings" → copy "Client ID" and "Client Secret"
""")


def _prompt_input(label: str, required: bool = True) -> str:
    while True:
        val = input(f"{label}: ").strip()
        if val:
            return val
        if not required:
            return ""
        print("  (required — please enter a value)")


def _get_config_file() -> Path:
    root = get_root_dir()
    return root / "src" / "plugins" / "spotify" / "config.yaml"


def _load_spotify_config() -> dict[str, Any]:
    cfg = load_config(_get_config_file())
    return cfg


def _save_spotify_config(data: dict[str, Any]) -> None:
    cfg_file = _get_config_file()
    # Encrypt sensitive fields before persisting
    for key in ("client_secret", "access_token", "refresh_token"):
        if data.get(key):
            data[key] = secure_storage.encrypt(data[key])
    save_yaml(cfg_file, data)
    log.info("Spotify config saved to %s", cfg_file)


# ── Local callback server ──────────────────────────────────────────────

_auth_code: str | None = None


class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global _auth_code
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if "code" in params:
            _auth_code = params["code"][0]
            self._send_response(200, "Authorization successful! You can close this tab.")
        elif "error" in params:
            self._send_response(400, f"Authorization failed: {params['error'][0]}")
        else:
            self._send_response(400, "Missing authorization code.")

    def _send_response(self, status: int, message: str):
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        body = f"""<!DOCTYPE html>
<html>
<head><title>Spotify Auth</title></head>
<body style="font-family:sans-serif; text-align:center; padding:40px;">
<h1>{'✅ Success' if status == 200 else '❌ Error'}</h1>
<p>{message}</p>
</body>
</html>"""
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, format, *args):
        # Suppress default HTTP server logging
        pass


def _run_callback_server(port: int) -> str | None:
    """Start a local HTTP server to catch the OAuth redirect."""
    global _auth_code
    _auth_code = None
    server = HTTPServer(("127.0.0.1", port), _CallbackHandler)
    server.timeout = 120  # Wait up to 2 minutes for the callback
    log.info("Waiting for callback on http://127.0.0.1:%s/callback ...", port)
    server.handle_request()
    return _auth_code


# ── Token exchange ─────────────────────────────────────────────────────

def _exchange_code(code: str, client_id: str, client_secret: str, redirect_uri: str) -> dict[str, Any] | None:
    payload = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "client_secret": client_secret,
    }).encode("utf-8")

    req = urllib.request.Request(
        SPOTIFY_TOKEN_URL,
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        log.error("Token exchange failed: %s %s", e.code, e.reason)
        try:
            log.error(e.read().decode("utf-8"))
        except (OSError, UnicodeDecodeError):
            pass
        return None
    except OSError as e:
        log.error("Token exchange failed: %s", e)
        return None


def _refresh_token(refresh_token: str, client_id: str, client_secret: str) -> dict[str, Any] | None:
    payload = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
    }).encode("utf-8")

    req = urllib.request.Request(
        SPOTIFY_TOKEN_URL,
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8")
    except OSError as e:
        log.error("Token refresh failed: %s", e)
        return None


# ── Main wizard ──────────────────────────────────────────────────────────

def main():
    _print_banner()

    # Check existing config
    spotify_cfg = _load_spotify_config()
    if spotify_cfg.get("refresh_token") and spotify_cfg.get("client_id"):
        print("Spotify tokens already configured.")
        choice = input("Do you want to re-run setup? [y/N]: ").strip().lower()
        if choice != "y":
            log.info("Aborted.")
            return

    _print_instructions()

    client_id = _prompt_input("Client ID")
    client_secret = _prompt_input("Client Secret")
    redirect_uri = _prompt_input(
        f"Redirect URI (default: {DEFAULT_REDIRECT_URI})", required=False
    ) or DEFAULT_REDIRECT_URI

    # Parse port from redirect URI
    parsed = urllib.parse.urlparse(redirect_uri)
    port = parsed.port or 8888

    # Build authorization URL
    scopes = "user-read-playback-state user-modify-playback-state user-read-currently-playing"
    auth_params = urllib.parse.urlencode({
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": scopes,
        "show_dialog": "true",
    })
    auth_url = f"{SPOTIFY_AUTH_URL}?{auth_params}"

    print("\n[OK] Opening browser for authorization...")
    print(f"    URL: {auth_url[:80]}...")
    webbrowser.open(auth_url)

    # Run local callback server
    auth_code = _run_callback_server(port)
    if not auth_code:
        log.error("No authorization code received. Did you approve the app in your browser?")
        return

    log.info("Authorization code received.")

    # Exchange code for tokens
    log.info("Exchanging code for tokens...")
    raw_response = _exchange_code(auth_code, client_id, client_secret, redirect_uri)
    if not raw_response:
        return

    import json
    token_data = json.loads(raw_response)
    access_token = token_data.get("access_token", "")
    refresh_token = token_data.get("refresh_token", "")
    expires_in = token_data.get("expires_in", 3600)

    if not access_token or not refresh_token:
        log.error("Token response missing required fields:")
        log.error(json.dumps(token_data, indent=2))
        return

    # Save to config
    spotify_cfg = {
        "enabled": True,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_expires_at": int(time.time()) + expires_in,
    }
    _save_spotify_config(spotify_cfg)

    print("\n" + "=" * 60)
    print("  Spotify setup complete!")
    print("=" * 60)
    log.info("Next steps:")
    log.info("  1. Restart TikTok2MC to load the new Spotify tokens")
    log.info("  2. Enable the Spotify plugin in the dashboard")
    log.info("  3. Viewers can now use $play, $pause, $skip, $volume, etc.")


def refresh():
    """Refresh an existing access token using the saved refresh token."""
    _print_banner()
    spotify_cfg = _load_spotify_config()

    client_id = spotify_cfg.get("client_id", "")
    raw_secret = spotify_cfg.get("client_secret", "")
    client_secret = secure_storage.decrypt(raw_secret) or raw_secret
    refresh_token_val = secure_storage.decrypt(spotify_cfg.get("refresh_token")) or spotify_cfg.get("refresh_token", "")

    if not all([client_id, client_secret, refresh_token_val]):
        log.error("Missing credentials. Run setup first.")
        return

    log.info("Refreshing access token...")
    raw = _refresh_token(refresh_token_val, client_id, client_secret)
    if not raw:
        return

    import json
    data = json.loads(raw)
    access_token = data.get("access_token", "")
    expires_in = data.get("expires_in", 3600)

    if not access_token:
        log.error("No access token in refresh response.")
        return

    spotify_cfg["access_token"] = access_token
    spotify_cfg["token_expires_at"] = int(time.time()) + expires_in
    _save_spotify_config(spotify_cfg)
    log.info("Access token refreshed.")


if __name__ == "__main__":
    install_global_exception_hook("spotify_setup")
    try:
        if len(sys.argv) > 1 and sys.argv[1] == "--refresh":
            refresh()
        else:
            main()
    except KeyboardInterrupt:
        log.info("Spotify setup interrupted by user.")
    except Exception:  # top-level boundary: report and exit non-zero
        handle_unhandled_exception("spotify_setup")
        sys.exit(1)
