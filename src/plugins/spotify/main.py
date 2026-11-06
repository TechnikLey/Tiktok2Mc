"""Spotify plugin: OAuth, playback control and trigger actions."""

import hashlib
import logging
import os
import threading
import time
import webbrowser
from pathlib import Path
from urllib.parse import urlencode

import requests

from core.base_plugin import BasePlugin
from core.secure_storage import secure_storage
from core.yaml_utils import load_yaml, save_yaml

log = logging.getLogger(__name__)

SPOTIFY_API = "https://api.spotify.com/v1"
SPOTIFY_AUTH = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN = "https://accounts.spotify.com/api/token"
SCOPES = "user-read-playback-state user-modify-playback-state user-library-modify user-read-currently-playing"


def validate_spotify_client_secret(secret: str) -> tuple[bool, str]:
    """Validate a Spotify client secret.

    Returns ``(is_valid, message)``.  Spotify client secrets are
    conventionally 32-character hexadecimal strings, but the check is
    lenient enough to accept longer or non-hex secrets in case Spotify
    changes their format.
    """
    if not secret:
        return False, "client_secret is empty"
    if len(secret) < 20:
        return (
            False,
            f"client_secret is too short ({len(secret)} chars, expected >= 20)",
        )
    if len(secret) == 32:
        try:
            int(secret, 16)
            return True, "client_secret looks valid (32 hex chars)"
        except ValueError:
            return True, "client_secret is 32 chars but not hex — accepted anyway"
    return True, f"client_secret accepted ({len(secret)} chars)"


class SpotifyClient:
    """Minimal Spotify Web API client with OAuth token persistence."""
    def __init__(self, client_id, client_secret, redirect_uri, config_path=None):
        """Create a client and load any previously stored tokens.

Args:
    client_id: Spotify application client ID.
    client_secret: Spotify application client secret.
    redirect_uri: OAuth redirect URI registered with Spotify.
    config_path: Optional config file; defaults to ``config.yaml`` next to
        this module."""

        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.config_path = (
            Path(config_path)
            if config_path
            else Path(__file__).resolve().parent / "config.yaml"
        )
        self.access_token = None
        self.refresh_token = None
        self.expires_at = 0
        self._token_lock = threading.Lock()
        self._load_tokens()

    def _load_tokens(self):
        """Load and decrypt stored tokens and their expiry, ignoring failures."""
        with self._token_lock:
            try:
                cfg = load_yaml(self.config_path)
                self.access_token = (
                    secure_storage.decrypt(cfg.get("access_token")) or None
                )
                self.refresh_token = (
                    secure_storage.decrypt(cfg.get("refresh_token")) or None
                )
                self.expires_at = cfg.get("token_expires_at", 0)
            except (
                Exception
            ) as e:  # token load is best-effort; plugin starts without auth
                log.info(f"[SPOTIFY] Failed to load tokens: {e}")

    def _save_tokens(self):
        """Encrypt and persist the current tokens, ignoring write failures."""
        with self._token_lock:
            try:
                cfg = load_yaml(self.config_path)
                cfg["access_token"] = secure_storage.encrypt(self.access_token) or ""
                cfg["refresh_token"] = secure_storage.encrypt(self.refresh_token) or ""
                cfg["token_expires_at"] = int(self.expires_at) if self.expires_at else 0
                save_yaml(self.config_path, cfg)
            except Exception as e:  # token persistence is best-effort
                log.info(f"[SPOTIFY] Failed to save tokens: {e}")

    @property
    def is_authenticated(self):
        """Return whether an access token is available."""
        return bool(self.access_token)

    def get_auth_url(self):
        """Build the authorization URL and a random state value.

Returns:
    A ``(url, state)`` tuple; callers should verify ``state`` on callback."""

        state = hashlib.sha256(os.urandom(32)).hexdigest()[:16]
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "scope": SCOPES,
            "state": state,
            "show_dialog": "false",
        }
        return f"{SPOTIFY_AUTH}?{urlencode(params)}", state

    def exchange_code(self, code):
        """Exchange an authorization code for tokens and persist them.

Args:
    code: Authorization code received on the OAuth callback.

Returns:
    ``True`` on success, ``False`` for an HTTP or JSON error."""

        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        resp = requests.post(SPOTIFY_TOKEN, data=data, timeout=10)
        if resp.status_code != 200:
            log.info(f"[SPOTIFY] Token exchange failed: {resp.text}")
            return False
        try:
            token_data = resp.json()
        except ValueError as e:
            log.info(f"[SPOTIFY] Invalid JSON in token response: {e}")
            return False
        self.access_token = token_data["access_token"]
        self.refresh_token = token_data.get("refresh_token", self.refresh_token)
        self.expires_at = time.time() + token_data["expires_in"]
        self._save_tokens()
        log.info("[SPOTIFY] Authentication successful")
        return True

    def refresh_access_token(self):
        """Refresh the access token using the stored refresh token.

Returns:
    ``True`` on success, ``False`` when no refresh token exists or the
    request fails."""

        if not self.refresh_token:
            return False
        data = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        try:
            resp = requests.post(SPOTIFY_TOKEN, data=data, timeout=10)
            if resp.status_code != 200:
                log.info(f"[SPOTIFY] Token refresh failed: {resp.text}")
                return False
            token_data = resp.json()
            self.access_token = token_data["access_token"]
            if token_data.get("refresh_token"):
                self.refresh_token = token_data["refresh_token"]
            self.expires_at = time.time() + token_data["expires_in"]
            self._save_tokens()
            return True
        except requests.RequestException as e:
            log.info(f"[SPOTIFY] Token refresh error: {e}")
            return False

    def _ensure_token(self):
        """Return whether a usable access token is available, refreshing if needed."""
        if not self.access_token:
            return False
        return time.time() < self.expires_at - 60 or self.refresh_access_token()

    def _headers(self):
        """Return the authorization header for the current access token."""
        return {"Authorization": f"Bearer {self.access_token}"}

    def _request(self, method, path, **kwargs):
        """Send an authenticated request to the Spotify API.

A 401 triggers one token refresh and a retry. Empty successful responses
(204) become ``{}``; missing resources and errors become ``None``.

Args:
    method: HTTP method.
    path: API path beginning with ``/``.
    **kwargs: Extra arguments for ``requests.request``.

Returns:
    Parsed JSON, ``{}`` for an empty response, or ``None`` on failure."""

        if not self._ensure_token():
            return None
        url = f"{SPOTIFY_API}{path}"
        try:
            resp = requests.request(
                method, url, headers=self._headers(), timeout=10, **kwargs
            )
            if resp.status_code == 401:
                if self.refresh_access_token():
                    resp = requests.request(
                        method, url, headers=self._headers(), timeout=10, **kwargs
                    )
                else:
                    return None
            if resp.status_code == 204:
                return {}
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 404:
                return None
            log.info(f"[SPOTIFY] API error {resp.status_code}: {resp.text[:200]}")
            return None
        except requests.RequestException as e:
            log.info(f"[SPOTIFY] Request error: {e}")
            return None

    def get_playback(self):
        """Return the current playback state, or ``None`` when unavailable."""
        return self._request("GET", "/me/player")

    def get_current_track(self):
        """Return the currently playing track payload, or ``None``."""
        return self._request("GET", "/me/player/currently-playing")

    def play(self, device_id=None):
        """Start or resume playback, optionally on a specific device.

Args:
    device_id: Spotify device to target; the active device is used when omitted."""

        kwargs = {}
        if device_id:
            kwargs["json"] = {"device_ids": [device_id]}
        return self._request("PUT", "/me/player/play", **kwargs)

    def pause(self, device_id=None):
        """Pause playback, optionally on a specific device.

Args:
    device_id: Spotify device to target; the active device is used when omitted."""

        kwargs = {}
        if device_id:
            kwargs["json"] = {"device_ids": [device_id]}
        return self._request("PUT", "/me/player/pause", **kwargs)

    def next_track(self):
        """Skip to the next track."""
        return self._request("POST", "/me/player/next")

    def previous_track(self):
        """Skip to the previous track."""
        return self._request("POST", "/me/player/previous")

    def set_volume(self, percent):
        """Set the playback volume, clamped to the 0-100 range.

Args:
    percent: Requested volume percentage."""

        return self._request(
            "PUT", f"/me/player/volume?volume_percent={max(0, min(100, percent))}"
        )

    def toggle_shuffle(self, state):
        """Enable or disable shuffle playback.

Args:
    state: Truthy value for on; it is lowercased for the API query."""

        return self._request("PUT", f"/me/player/shuffle?state={str(state).lower()}")

    def set_repeat(self, state):
        """Set the repeat mode.

Args:
    state: One of ``off``, ``context`` or ``track``; other values are ignored."""

        if state not in ("off", "context", "track"):
            return None
        return self._request("PUT", f"/me/player/repeat?state={state}")

    def save_current(self):
        """Save the currently playing track to the user's library.

Returns:
    The API response, or ``None`` when no track is playing."""

        track = self._get_current_track_item()
        if not track:
            return None
        return self._request("PUT", "/me/tracks", json={"ids": [track["id"]]})

    def _get_current_track_item(self):
        """Return the current track item, falling back to the playback state."""
        data = self.get_current_track()
        if data and data.get("item"):
            return data["item"]
        playback = self.get_playback()
        if playback and playback.get("item"):
            return playback["item"]
        return None

    def transfer_playback(self, device_id=None):
        """Move playback to a device.

Without ``device_id`` the first available device is used. Returns ``None``
when no device can be found."""

        if not device_id:
            devices = self._request("GET", "/me/player/devices")
            if devices and devices.get("devices"):
                did = devices["devices"][0]["id"]
                return self._request("PUT", "/me/player", json={"device_ids": [did]})
            return None
        return self._request("PUT", "/me/player", json={"device_ids": [device_id]})

    def search_track(self, query):
        """Search for a single matching track.

Args:
    query: Spotify search query.

Returns:
    The raw search payload, or ``None`` on error."""

        params = {"q": query, "type": "track", "limit": 1}
        url = f"{SPOTIFY_API}/search"
        if not self._ensure_token():
            return None
        try:
            resp = requests.get(url, headers=self._headers(), params=params, timeout=10)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 401 and self.refresh_access_token():
                resp = requests.get(
                    url, headers=self._headers(), params=params, timeout=10
                )
                if resp.status_code == 200:
                    return resp.json()
            log.info(
                f"[SPOTIFY] Search API error {resp.status_code}: {resp.text[:200]}"
            )
            return None
        except requests.RequestException as e:
            log.info(f"[SPOTIFY] Search error: {e}")
            return None

    def play_specific(self, track_uri, device_id=None):
        """Play a specific track URI, optionally on a device.

Args:
    track_uri: Spotify track URI.
    device_id: Optional target device."""

        kwargs = {"json": {"uris": [track_uri]}}
        if device_id:
            kwargs["json"]["device_ids"] = [device_id]
        return self._request("PUT", "/me/player/play", **kwargs)

    def queue_track(self, track_uri, device_id=None):
        """Append a track URI to the playback queue.

Args:
    track_uri: Spotify track URI.
    device_id: Optional target device."""

        import urllib.parse as up

        params = f"uri={up.quote(track_uri, safe='')}"
        if device_id:
            params += f"&device_id={up.quote(device_id, safe='')}"
        return self._request("POST", f"/me/player/queue?{params}")


def _format_track(data):
    """Flatten a Spotify playback payload into the overlay/state fields.

Missing fields fall back to empty values, ``Unknown`` for the title and
zero for durations."""

    item = data.get("item", {})
    progress = data.get("progress_ms", 0)
    is_playing = data.get("is_playing", False)
    return {
        "id": item.get("id", ""),
        "name": item.get("name", "Unknown"),
        "artists": ", ".join(a.get("name", "") for a in item.get("artists", [])),
        "album": item.get("album", {}).get("name", ""),
        "image": item["album"]["images"][0]["url"]
        if item.get("album", {}).get("images")
        else "",
        "duration_ms": item.get("duration_ms", 0),
        "progress_ms": progress,
        "is_playing": is_playing,
        "progress_sec": progress // 1000,
        "duration_sec": item.get("duration_ms", 0) // 1000,
    }


class SpotifyControlPlugin(BasePlugin):
    """Plugin providing Spotify OAuth, playback control and overlay state."""
    PLUGIN_NAME = "spotify-control"

    def __init__(self):
        """Load credentials and playback settings, then register command handlers.

The client secret is decrypted when stored encrypted and validated with a
warning when it looks suspicious."""

        super().__init__()
        cfg = self.config
        self._client_id = cfg.get("client_id", "")
        raw_secret = cfg.get("client_secret", "")
        self._client_secret = secure_storage.decrypt(raw_secret) or raw_secret
        # Validate and warn if the secret looks suspicious
        valid, msg = validate_spotify_client_secret(self._client_secret)
        if not valid:
            log.warning("[SPOTIFY] %s", msg)
        else:
            log.debug("[SPOTIFY] %s", msg)
        self._redirect_uri = cfg.get(
            "redirect_uri",
            "http://127.0.0.1:29185/api/v1/plugins/oauth/callback?name=spotify-control",
        )
        self._device_id = cfg.get("device_id", "")
        self._volume_step = cfg.get("volume_step", 10)
        self._playtrack_mode = cfg.get("playtrack_mode", "replace")
        self._signal_on = set(cfg.get("signal_on", ["track_changed", "play", "pause"]))

        self._client = SpotifyClient(
            self._client_id,
            self._client_secret,
            self._redirect_uri,
        )
        self._auth_state = None
        self._last_track_id = None
        self._last_track_lock = threading.Lock()

        # Handlers for plugin commands
        self.register_handler("start_oauth", self._on_start_oauth)
        self.register_handler("oauth_callback", self._on_oauth_callback)
        self.register_handler("play", self._on_play)
        self.register_handler("pause", self._on_pause)
        self.register_handler("next", self._on_next)
        self.register_handler("previous", self._on_previous)
        self.register_handler("volume", self._on_volume)
        self.register_handler("volume_up", self._on_volume_up)
        self.register_handler("volume_down", self._on_volume_down)
        self.register_handler("shuffle", self._on_shuffle)
        self.register_handler("repeat", self._on_repeat)
        self.register_handler("save", self._on_save)
        self.register_handler("playtrack", self._on_playtrack)
        self.register_handler("comment", self._on_comment)

    # -- event publishing ------------------------------------------------

    def _maybe_signal(self, event_type: str, extra: dict | None = None):
        """Publish ``spotify.<event_type>`` when that signal is enabled.

Args:
    event_type: Signal name such as ``play`` or ``track_changed``.
    extra: Optional fields included in the event payload."""

        if event_type in self._signal_on:
            data = {}
            if extra:
                data.update(extra)
            self.publish_event(f"spotify.{event_type}", data)

    # -- tick (overlay polling) -------------------------------------------

    def on_tick(self):
        """Poll playback while authenticated and refresh the overlay state.

Errors are logged so a failed poll never terminates the plugin thread."""

        try:
            if self._client.is_authenticated:
                self._notify_overlay()
        except Exception as e:  # tick polling must never kill the plugin thread
            log.info(f"[SPOTIFY-POLL] Error: {e}")

    # -- command handlers ---------------------------------------------------

    def _on_start_oauth(self, _):
        """Open the Spotify authorization page and remember the state value.

Does nothing when the client ID or secret is missing."""

        if not self._client_id or not self._client_secret:
            log.info("[SPOTIFY] Cannot start OAuth: missing client_id or client_secret")
            return
        url, state = self._client.get_auth_url()
        self._auth_state = state
        webbrowser.open(url)
        log.info("[SPOTIFY] OAuth URL opened in browser")

    def _on_oauth_callback(self, args):
        """Validate the OAuth state and exchange the authorization code.

A mismatching state is logged and ignored; without a code no exchange is
attempted."""

        code = args.get("code", "")
        state = args.get("state", "")
        if state and self._auth_state is not None and state != self._auth_state:
            log.info("[SPOTIFY] State mismatch in OAuth callback")
        elif code:
            self._client.exchange_code(code)
            self._notify_overlay()

    def _on_play(self, _):
        """Resume playback, publish ``spotify.play`` and refresh the overlay."""
        if self._client.is_authenticated:
            self._client.play(self._device_id or None)
            self._maybe_signal("play")
            self._notify_overlay()

    def _on_pause(self, _):
        """Pause playback, publish ``spotify.pause`` and refresh the overlay."""
        if self._client.is_authenticated:
            self._client.pause(self._device_id or None)
            self._maybe_signal("pause")
            self._notify_overlay()

    def _on_next(self, _):
        """Skip to the next track, publish ``track_changed`` and refresh the overlay.

The short sleep gives Spotify time to update before the overlay is polled."""

        if self._client.is_authenticated:
            self._client.next_track()
            self._maybe_signal("track_changed", {"direction": "next"})
            time.sleep(0.5)
            self._notify_overlay()

    def _on_previous(self, _):
        """Skip to the previous track, publish ``track_changed`` and refresh the overlay.

The short sleep gives Spotify time to update before the overlay is polled."""

        if self._client.is_authenticated:
            self._client.previous_track()
            self._maybe_signal("track_changed", {"direction": "previous"})
            time.sleep(0.5)
            self._notify_overlay()

    def _on_volume(self, args):
        """Set the volume from the command's ``level`` argument.

Args:
    args: Command arguments; missing ``level`` leaves the volume unchanged."""

        level = args.get("level")
        if level is not None and self._client.is_authenticated:
            self._client.set_volume(int(level))

    def _on_volume_up(self, _):
        """Raise the device volume by ``volume_step``, capped at 100.

The current volume defaults to 50 when playback state is unavailable."""

        if self._client.is_authenticated:
            playback = self._client.get_playback()
            current = (
                playback["device"].get("volume_percent", 50)
                if playback and playback.get("device")
                else 50
            )
            self._client.set_volume(min(100, current + self._volume_step))

    def _on_volume_down(self, _):
        """Lower the device volume by ``volume_step``, clamped at zero.

The current volume defaults to 50 when playback state is unavailable."""

        if self._client.is_authenticated:
            playback = self._client.get_playback()
            current = (
                playback["device"].get("volume_percent", 50)
                if playback and playback.get("device")
                else 50
            )
            self._client.set_volume(max(0, current - self._volume_step))

    def _on_shuffle(self, args):
        """Toggle or explicitly set shuffle mode.

Args:
    args: Optional ``state``; ``toggle`` (default) flips the current value,
        while ``true``/``1`` enable and other values disable shuffle."""

        if not self._client.is_authenticated:
            return
        state_val = args.get("state", "toggle")
        if state_val == "toggle":
            playback = self._client.get_playback()
            current = playback.get("shuffle_state", False) if playback else False
            self._client.toggle_shuffle(not current)
        else:
            self._client.toggle_shuffle(state_val in ("true", "1"))
        self._notify_overlay()

    def _on_repeat(self, args):
        """Toggle or explicitly set the repeat mode.

Args:
    args: Optional ``state``; ``toggle`` (default) cycles
        ``off`` → ``context`` → ``track``, other values are passed through."""

        if not self._client.is_authenticated:
            return
        state_val = args.get("state", "toggle")
        if state_val == "toggle":
            playback = self._client.get_playback()
            current = playback.get("repeat_state", "off") if playback else "off"
            order = ["off", "context", "track"]
            next_idx = (
                (order.index(current) + 1) % len(order) if current in order else 1
            )
            self._client.set_repeat(order[next_idx])
        else:
            self._client.set_repeat(state_val)
        self._notify_overlay()

    def _on_save(self, _):
        """Save the current track to the user's library."""
        if self._client.is_authenticated:
            self._client.save_current()

    def _on_playtrack(self, args):
        """Search for and play the track described by the ``text`` argument."""
        text = args.get("text", "")
        if text and self._client.is_authenticated:
            self._search_and_play(text)

    def _on_comment(self, args):
        """Handle a chat-style Spotify command.

Supports ``play``, ``pause``, ``skip``, ``prev``/``previous``/``back``,
``volume <n>``, ``save``, ``shuffle``, ``repeat``/``loop`` and
``playtrack <query>``. Unknown commands are ignored."""

        text = args.get("text", "").strip().lower()
        if not text:
            return
        parts = text.split(maxsplit=1)
        sub_cmd = parts[0]
        arg = parts[1] if len(parts) > 1 else None
        if sub_cmd == "play":
            self._on_play({})
        elif sub_cmd == "pause":
            self._on_pause({})
        elif sub_cmd == "skip":
            self._on_next({})
        elif sub_cmd in ("prev", "previous", "back"):
            self._on_previous({})
        elif sub_cmd == "volume" and arg:
            try:
                self._client.set_volume(int(arg))
            except ValueError:
                pass
        elif sub_cmd == "save":
            self._on_save({})
        elif sub_cmd == "shuffle":
            self._on_shuffle({})
        elif sub_cmd in ("repeat", "loop"):
            self._on_repeat({})
        elif sub_cmd == "playtrack":
            self._on_playtrack({"text": text})

    # -- overlay state ------------------------------------------------------

    def _notify_overlay(self):
        """Refresh the published state and emit ``track_changed`` on new tracks.

Progress is reset for a newly seen track unless it is already near the end,
which avoids briefly showing a stale position on the overlay."""

        track_data = self._get_current_track_data()
        if track_data is None:
            if self._last_track_id:
                return
            self.push_state()
            return
        with self._last_track_lock:
            if track_data["id"] and track_data["id"] != self._last_track_id:
                self._last_track_id = track_data["id"]
                self._maybe_signal(
                    "track_changed",
                    {"track": track_data["name"], "artist": track_data["artists"]},
                )
                progress_ms = track_data.get("progress_ms", 0)
                track_data["progress_ms"] = 0
                track_data["progress_sec"] = 0
                pct = (
                    progress_ms / track_data["duration_ms"] * 100
                    if track_data.get("duration_ms")
                    else 0
                )
                if pct < 90:
                    track_data["progress_ms"] = progress_ms
                    track_data["progress_sec"] = progress_ms // 1000
        self.push_state()

    def _get_current_track_data(self):
        """Return formatted current-track data, falling back to the playback state.

Returns ``None`` when neither endpoint reports a track."""

        data = self._client.get_current_track()
        if not data or not data.get("item"):
            playback = self._client.get_playback()
            if playback and playback.get("item"):
                data = playback
            else:
                return None
        return _format_track(data)

    # -- search & play ------------------------------------------------------

    def _search_and_play(self, text: str):
        """Search for a track and either play it or add it to the queue.

``text`` may be ``artist - title``; a field-based query is tried first, then
a free-text fallback. The result reports ``not_found`` or ``ok`` with the
mode and selected track."""

        text = text.strip()
        if text.lower().startswith("playtrack"):
            text = text[len("playtrack") :].strip()
        parts = text.split(" - ", maxsplit=1)
        if len(parts) < 2:
            artist = ""
            song = text
        else:
            artist = parts[0].strip()
            song = parts[1].strip()
        query_parts = []
        if artist:
            query_parts.append(f"artist:{artist}")
        if song:
            query_parts.append(f"track:{song}")
        query = " ".join(query_parts)
        result = self._client.search_track(query)
        if not result:
            query = f"{artist} - {song}" if artist else song
            result = self._client.search_track(query)
        if not result or not result.get("tracks", {}).get("items"):
            return {"status": "not_found", "found": False}
        track = result["tracks"]["items"][0]
        track_name = track["name"]
        track_artists = ", ".join(a["name"] for a in track["artists"])
        track_uri = track["uri"]
        if self._playtrack_mode == "queue":
            self._client.queue_track(track_uri, self._device_id or None)
        else:
            self._client.play_specific(track_uri, self._device_id or None)
        time.sleep(0.5)
        self._notify_overlay()
        return {
            "status": "ok",
            "found": True,
            "mode": self._playtrack_mode,
            "track": {"name": track_name, "artists": track_artists, "uri": track_uri},
        }

    # -- overlay HTML -------------------------------------------------------

    def get_overlay_html(self) -> str:
        """Return the OBS overlay for the current track and playback progress."""
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="color-scheme" content="dark">
<style>
{self.theme_style}
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
        background: transparent;
        font-family: 'Inter', 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
        overflow: hidden;
        width: 100vw;
        height: 100vh;
        display: flex;
        align-items: stretch;
        -webkit-font-smoothing: antialiased;
    }}
    #player {{
        display: none;
        align-items: center;
        gap: min(11vh, 28px);
        padding: min(10vh, 24px) min(3.8vw, 32px);
        background: rgba(0,0,0,0.75);
        border-radius: min(10vh, 24px);
        border: 1px solid rgba(255,255,255,0.08);
        backdrop-filter: blur(8px);
        width: 100%;
    }}
    #player.visible {{ display: flex; }}
    #cover {{
        width: min(66.7vh, 200px);
        height: min(66.7vh, 200px);
        border-radius: min(5vh, 12px);
        object-fit: cover;
        flex-shrink: 0;
        box-shadow: 0 2px 12px rgba(0,0,0,0.4);
    }}
    #info {{ flex: 1; min-width: 0; }}
    #track-name {{
        color: var(--text);
        font-size: min(15vh, 48px);
        font-weight: 700;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }}
    #track-artist {{
        color: var(--text);
        opacity: 0.7;
        font-size: min(12vh, 36px);
        margin-top: 0.15em;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }}
    #progress-wrap {{
        margin-top: min(6.7vh, 16px);
        height: min(3.3vh, 8px);
        border-radius: 2px;
        overflow: hidden;
        position: relative;
    }}
    #progress-wrap::before {{
        content: '';
        position: absolute;
        inset: 0;
        background: var(--text);
        opacity: 0.15;
        border-radius: 2px;
    }}
    #progress-bar {{
        position: relative;
        height: 100%;
        width: 0%;
        background: linear-gradient(90deg, var(--accent), var(--accent2));
        border-radius: 2px;
        transition: width 0.5s ease;
    }}
    #status-text {{
        color: var(--text);
        opacity: 0.5;
        font-size: min(12vh, 36px);
        text-align: center;
        padding: 2vh;
        width: 100%;
    }}
</style>
</head>
<body>
<div id="status-text">Loading Spotify...</div>
<div id="player">
    <img id="cover" src="" alt="Cover">
    <div id="info">
        <div id="track-name"></div>
        <div id="track-artist"></div>
        <div id="progress-wrap"><div id="progress-bar"></div></div>
    </div>
</div>
<script>
const player = document.getElementById('player');
const statusText = document.getElementById('status-text');
const cover = document.getElementById('cover');
const trackName = document.getElementById('track-name');
const trackArtist = document.getElementById('track-artist');
const progressBar = document.getElementById('progress-bar');
const evtSource = new EventSource('/api/v1/plugins/spotify-control/stream');
let progressStart = 0, durationMs = 0, lastUpdate = 0, isPlaying = false;
function updateProgress() {{
    if (!durationMs) return;
    if (isPlaying) {{
        const elapsed = Date.now() - lastUpdate;
        const current = Math.min(progressStart + elapsed, durationMs);
        const pct = (current / durationMs) * 100;
        progressBar.style.width = pct + '%';
    }}
}}
evtSource.onmessage = function(e) {{
    try {{
        const data = JSON.parse(e.data);
        if (data.name) {{
            player.classList.add('visible');
            statusText.style.display = 'none';
            cover.src = data.image || '';
            trackName.textContent = data.name || 'Unknown';
            trackArtist.textContent = data.artists || '';
            durationMs = data.duration_ms || 0;
            progressStart = data.progress_ms || 0;
            lastUpdate = Date.now();
            isPlaying = data.is_playing || false;
            updateProgress();
        }} else if (data.type === 'no_track' && !player.classList.contains('visible')) {{
            statusText.textContent = 'No active track';
        }}
    }} catch(e) {{}}
}};
evtSource.onerror = function() {{
    if (!player.classList.contains('visible')) {{
        statusText.textContent = 'Connection lost...';
    }}
}};
setInterval(updateProgress, 1000);
</script>
</body>
</html>"""

    # -- run ----------------------------------------------------------------

    def run(self) -> None:
        """Start the plugin, opening the OAuth flow first when setup is complete.

OAuth is only started when the GUI is visible, no token is stored and both
client credentials are configured."""

        if (
            not self.gui_hidden
            and not self._client.is_authenticated
            and (self._client_id and self._client_secret)
        ):
            self._on_start_oauth({})
        super().run()


if __name__ == "__main__":
    plugin = SpotifyControlPlugin()
    if (
        not plugin.gui_hidden
        and not plugin._client.is_authenticated
        and (plugin._client_id and plugin._client_secret)
    ):
        plugin._on_start_oauth({})
    plugin.run()
