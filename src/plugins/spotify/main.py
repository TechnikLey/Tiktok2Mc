#!/usr/bin/env python3
# ==================================================
# spotify - Spotify Control Plugin
# ==================================================
# Allows viewers to control Spotify playback via
# TikTok comments and events. Uses the Spotify
# Web API for all playback control.
# ==================================================

import sys
import json
import time
import threading
import webbrowser
import base64
import hashlib
import os
from queue import Queue
from urllib.parse import urlencode, parse_qs
from pathlib import Path

import yaml
import requests
from flask import Flask, Response, request, jsonify, redirect
from core import parse_args, AppConfig, get_base_dir, get_root_dir, get_base_file
from python.registry import register_plugin

# =========================
# Paths & configuration
# =========================
BASE_DIR = get_base_dir()
ROOT_DIR = get_root_dir()

CONFIG_FILE = (ROOT_DIR / "config" / "config.yaml").resolve()
TOKEN_FILE = (ROOT_DIR / "data" / "spotify_token.json").resolve()

args = parse_args()

cfg = {}

try:
    if not CONFIG_FILE.exists():
        print("Config not found")
        sys.exit(1)
    else:
        with CONFIG_FILE.open("r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        SPOTIFY_CFG = cfg.get("spotify", {})
        SPOTIFY_PORT = SPOTIFY_CFG.get("port", 29194)
        CLIENT_ID = SPOTIFY_CFG.get("client_id", "")
        CLIENT_SECRET = SPOTIFY_CFG.get("client_secret", "")
        REDIRECT_URI = SPOTIFY_CFG.get("redirect_uri", f"http://127.0.0.1:{SPOTIFY_PORT}/callback")
        DEVICE_ID = SPOTIFY_CFG.get("device_id", "")
        VOLUME_STEP = SPOTIFY_CFG.get("volume_step", 10)
        SERVER_HOST = cfg.get("server_host", "127.0.0.1")
except Exception as e:
    print(f"Config error: {e}")
    SPOTIFY_PORT = 29194
    CLIENT_ID = ""
    CLIENT_SECRET = ""
    REDIRECT_URI = f"http://127.0.0.1:{SPOTIFY_PORT}/callback"
    DEVICE_ID = ""
    VOLUME_STEP = 10
    SERVER_HOST = "127.0.0.1"

SPOTIFY_EXE_PATH = get_base_file()

# --- Plugin self-registration ---
register_only = args.register_only

if register_only:
    register_plugin(AppConfig(
        name="Spotify Control",
        path=SPOTIFY_EXE_PATH,
        enable=SPOTIFY_CFG.get("enabled", True),
        level=4,
        ics=True
    ))
    sys.exit(0)

# =========================
# Spotify API wrapper
# =========================
SPOTIFY_API = "https://api.spotify.com/v1"
SPOTIFY_AUTH = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN = "https://accounts.spotify.com/api/token"
SCOPES = "user-read-playback-state user-modify-playback-state user-library-modify user-read-currently-playing"


class SpotifyClient:
    def __init__(self, client_id, client_secret, redirect_uri):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.access_token = None
        self.refresh_token = None
        self.expires_at = 0
        self._load_tokens()

    def _load_tokens(self):
        if TOKEN_FILE.exists():
            try:
                with TOKEN_FILE.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                self.access_token = data.get("access_token")
                self.refresh_token = data.get("refresh_token")
                self.expires_at = data.get("expires_at", 0)
            except Exception:
                pass

    def _save_tokens(self):
        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        with TOKEN_FILE.open("w", encoding="utf-8") as f:
            json.dump({
                "access_token": self.access_token,
                "refresh_token": self.refresh_token,
                "expires_at": self.expires_at,
            }, f, indent=2)

    @property
    def is_authenticated(self):
        return bool(self.access_token)

    def get_auth_url(self):
        state = hashlib.sha256(os.urandom(32)).hexdigest()[:16]
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "scope": SCOPES,
            "state": state,
            "show_dialog": "true",
        }
        return f"{SPOTIFY_AUTH}?{urlencode(params)}", state

    def exchange_code(self, code):
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        resp = requests.post(SPOTIFY_TOKEN, data=data, timeout=10)
        if resp.status_code != 200:
            print(f"[SPOTIFY] Token exchange failed: {resp.text}")
            return False
        token_data = resp.json()
        self.access_token = token_data["access_token"]
        self.refresh_token = token_data.get("refresh_token", self.refresh_token)
        self.expires_at = time.time() + token_data["expires_in"]
        self._save_tokens()
        print("[SPOTIFY] Authentication successful")
        return True

    def refresh_access_token(self):
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
                print(f"[SPOTIFY] Token refresh failed: {resp.text}")
                return False
            token_data = resp.json()
            self.access_token = token_data["access_token"]
            if token_data.get("refresh_token"):
                self.refresh_token = token_data["refresh_token"]
            self.expires_at = time.time() + token_data["expires_in"]
            self._save_tokens()
            return True
        except Exception as e:
            print(f"[SPOTIFY] Token refresh error: {e}")
            return False

    def _ensure_token(self):
        if not self.access_token:
            return False
        if time.time() >= self.expires_at - 60:
            if not self.refresh_access_token():
                return False
        return True

    def _headers(self):
        return {"Authorization": f"Bearer {self.access_token}"}

    def _request(self, method, path, **kwargs):
        if not self._ensure_token():
            return None
        url = f"{SPOTIFY_API}{path}"
        try:
            resp = requests.request(method, url, headers=self._headers(), timeout=10, **kwargs)
            if resp.status_code == 401:
                if self.refresh_access_token():
                    resp = requests.request(method, url, headers=self._headers(), timeout=10, **kwargs)
                else:
                    return None
            if resp.status_code == 204:
                return {}
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 404:
                return None
            print(f"[SPOTIFY] API error {resp.status_code}: {resp.text[:200]}")
            return None
        except Exception as e:
            print(f"[SPOTIFY] Request error: {e}")
            return None

    def get_playback(self):
        return self._request("GET", "/me/player")

    def get_current_track(self):
        return self._request("GET", "/me/player/currently-playing")

    def play(self):
        kwargs = {}
        if DEVICE_ID:
            kwargs["json"] = {"device_ids": [DEVICE_ID]}
        return self._request("PUT", "/me/player/play", **kwargs)

    def pause(self):
        kwargs = {}
        if DEVICE_ID:
            kwargs["json"] = {"device_ids": [DEVICE_ID]}
        return self._request("PUT", "/me/player/pause", **kwargs)

    def next_track(self):
        return self._request("POST", "/me/player/next")

    def previous_track(self):
        return self._request("POST", "/me/player/previous")

    def set_volume(self, percent):
        return self._request("PUT", f"/me/player/volume?volume_percent={max(0, min(100, percent))}")

    def toggle_shuffle(self, state):
        return self._request("PUT", f"/me/player/shuffle?state={str(state).lower()}")

    def set_repeat(self, state):
        if state not in ("off", "context", "track"):
            return None
        return self._request("PUT", f"/me/player/repeat?state={state}")

    def save_current(self):
        track = self.get_current_track()
        if not track or not track.get("item"):
            return None
        track_id = track["item"]["id"]
        return self._request("PUT", "/me/tracks", json={"ids": [track_id]})

    def transfer_playback(self):
        if not DEVICE_ID:
            devices = self._request("GET", "/me/player/devices")
            if devices and devices.get("devices"):
                did = devices["devices"][0]["id"]
                return self._request("PUT", "/me/player", json={"device_ids": [did]})
            return None
        return self._request("PUT", "/me/player", json={"device_ids": [DEVICE_ID]})


spotify = SpotifyClient(CLIENT_ID, CLIENT_SECRET, REDIRECT_URI)

# =========================
# Flask setup
# =========================
app = Flask(__name__)

auth_state = None


@app.route("/login")
def login():
    global auth_state
    url, state = spotify.get_auth_url()
    auth_state = state
    return redirect(url)


@app.route("/callback")
def callback():
    code = request.args.get("code")
    state = request.args.get("state")
    error = request.args.get("error")
    if error:
        return f"Spotify auth error: {error}", 400
    if not code:
        return "Missing authorization code", 400
    if spotify.exchange_code(code):
        overlay_clients.notify_auth(True)
        _notify_overlay()
        return "<html><body><h2>Connected to Spotify!</h2><p>You can close this window.</p></body></html>"
    return "Authorization failed", 400


@app.route("/status")
def status_endpoint():
    return jsonify({
        "authenticated": spotify.is_authenticated,
        "has_client_id": bool(CLIENT_ID),
    })


@app.route("/current")
def current_track():
    if not spotify.is_authenticated:
        return jsonify({"error": "not_authenticated"}), 401
    data = spotify.get_current_track()
    if not data or not data.get("item"):
        playback = spotify.get_playback()
        if playback and playback.get("item"):
            data = playback
        else:
            return jsonify({"error": "no_track"}), 404
    return jsonify(_format_track(data))


def _format_track(data):
    item = data.get("item", {})
    progress = data.get("progress_ms", 0)
    is_playing = data.get("is_playing", False)
    return {
        "id": item.get("id", ""),
        "name": item.get("name", "Unknown"),
        "artists": ", ".join(a.get("name", "") for a in item.get("artists", [])),
        "album": item.get("album", {}).get("name", ""),
        "image": item["album"]["images"][0]["url"] if item.get("album", {}).get("images") else "",
        "duration_ms": item.get("duration_ms", 0),
        "progress_ms": progress,
        "is_playing": is_playing,
        "progress_sec": progress // 1000,
        "duration_sec": item.get("duration_ms", 0) // 1000,
    }


# --- Playback control endpoints ---
@app.route("/play", methods=["POST"])
def cmd_play():
    if not spotify.is_authenticated:
        return jsonify({"error": "not_authenticated"}), 401
    spotify.play()
    _notify_overlay()
    return jsonify({"status": "ok"})


@app.route("/pause", methods=["POST"])
def cmd_pause():
    if not spotify.is_authenticated:
        return jsonify({"error": "not_authenticated"}), 401
    spotify.pause()
    _notify_overlay()
    return jsonify({"status": "ok"})


@app.route("/next", methods=["POST"])
def cmd_next():
    if not spotify.is_authenticated:
        return jsonify({"error": "not_authenticated"}), 401
    spotify.next_track()
    time.sleep(0.5)
    _notify_overlay()
    return jsonify({"status": "ok"})


@app.route("/previous", methods=["POST"])
def cmd_previous():
    if not spotify.is_authenticated:
        return jsonify({"error": "not_authenticated"}), 401
    spotify.previous_track()
    time.sleep(0.5)
    _notify_overlay()
    return jsonify({"status": "ok"})


@app.route("/volume", methods=["POST"])
def cmd_volume():
    if not spotify.is_authenticated:
        return jsonify({"error": "not_authenticated"}), 401
    level = request.args.get("level", type=int)
    if level is None:
        return jsonify({"error": "missing level"}), 400
    spotify.set_volume(level)
    return jsonify({"status": "ok"})


@app.route("/volume/up", methods=["POST"])
def cmd_volume_up():
    if not spotify.is_authenticated:
        return jsonify({"error": "not_authenticated"}), 401
    playback = spotify.get_playback()
    if playback and playback.get("device"):
        current = playback["device"].get("volume_percent", 50)
    else:
        current = 50
    spotify.set_volume(min(100, current + VOLUME_STEP))
    return jsonify({"status": "ok"})


@app.route("/volume/down", methods=["POST"])
def cmd_volume_down():
    if not spotify.is_authenticated:
        return jsonify({"error": "not_authenticated"}), 401
    playback = spotify.get_playback()
    if playback and playback.get("device"):
        current = playback["device"].get("volume_percent", 50)
    else:
        current = 50
    spotify.set_volume(max(0, current - VOLUME_STEP))
    return jsonify({"status": "ok"})


@app.route("/shuffle", methods=["POST"])
def cmd_shuffle():
    if not spotify.is_authenticated:
        return jsonify({"error": "not_authenticated"}), 401
    state = request.args.get("state", "").lower()
    if state == "toggle":
        playback = spotify.get_playback()
        current = playback.get("shuffle_state", False) if playback else False
        spotify.toggle_shuffle(not current)
    else:
        spotify.toggle_shuffle(state in ("true", "1"))
    return jsonify({"status": "ok"})


@app.route("/repeat", methods=["POST"])
def cmd_repeat():
    if not spotify.is_authenticated:
        return jsonify({"error": "not_authenticated"}), 401
    state = request.args.get("state", "toggle")
    if state == "toggle":
        playback = spotify.get_playback()
        current = playback.get("repeat_state", "off") if playback else "off"
        order = ["off", "context", "track"]
        next_idx = (order.index(current) + 1) % len(order) if current in order else 1
        spotify.set_repeat(order[next_idx])
    else:
        spotify.set_repeat(state)
    return jsonify({"status": "ok"})


@app.route("/save", methods=["POST"])
def cmd_save():
    if not spotify.is_authenticated:
        return jsonify({"error": "not_authenticated"}), 401
    result = spotify.save_current()
    if result is None:
        return jsonify({"error": "no_track"}), 404
    return jsonify({"status": "ok"})


@app.route("/comment", methods=["POST"])
def cmd_comment():
    user = request.args.get("user", "Unknown")
    text = request.args.get("text", "").strip().lower()
    if not text:
        return jsonify({"error": "missing text"}), 400
    parts = text.split(maxsplit=1)
    command = parts[0]
    arg = parts[1] if len(parts) > 1 else None

    if command == "play":
        spotify.play()
        _notify_overlay()
    elif command == "pause":
        spotify.pause()
        _notify_overlay()
    elif command in ("skip", "next"):
        spotify.next_track()
        time.sleep(0.5)
        _notify_overlay()
    elif command in ("prev", "previous", "back"):
        spotify.previous_track()
        time.sleep(0.5)
        _notify_overlay()
    elif command == "volume" and arg:
        try:
            spotify.set_volume(int(arg))
        except ValueError:
            return jsonify({"error": "invalid level"}), 400
    elif command == "save":
        spotify.save_current()
    elif command == "shuffle":
        playback = spotify.get_playback()
        current = playback.get("shuffle_state", False) if playback else False
        spotify.toggle_shuffle(not current)
        _notify_overlay()
    elif command in ("repeat", "loop"):
        playback = spotify.get_playback()
        current = playback.get("repeat_state", "off") if playback else "off"
        order = ["off", "context", "track"]
        next_idx = (order.index(current) + 1) % len(order) if current in order else 1
        spotify.set_repeat(order[next_idx])
    elif command in ("current", "song", "track"):
        return current_track()
    else:
        return jsonify({"error": "unknown_command"}), 400
    return jsonify({"status": "ok"})


# --- Overlay (SSE + HTML) ---
class OverlayClients:
    def __init__(self):
        self.listeners = []

    def add(self, q):
        self.listeners.append(q)

    def remove(self, q):
        try:
            self.listeners.remove(q)
        except ValueError:
            pass

    def notify(self, data):
        for q in self.listeners:
            q.put(data)

    def notify_auth(self, success):
        self.notify({"type": "auth", "success": success})


overlay_clients = OverlayClients()


_last_track_id = None


def _notify_overlay():
    global _last_track_id
    data = spotify.get_current_track()
    if not data or not data.get("item"):
        playback = spotify.get_playback()
        if playback and playback.get("item"):
            data = playback
        else:
            if _last_track_id:
                return
            overlay_clients.notify({"type": "no_track"})
            return
    track = _format_track(data)
    track["type"] = "track"
    if track["id"] and track["id"] != _last_track_id:
        _last_track_id = track["id"]
        progress_ms = track.get("progress_ms", 0)
        track["progress_ms"] = 0
        track["progress_sec"] = 0
        pct = progress_ms / track["duration_ms"] * 100 if track.get("duration_ms") else 0
        if pct < 90:
            track["progress_ms"] = progress_ms
            track["progress_sec"] = progress_ms // 1000
    overlay_clients.notify(track)


def _poll_spotify():
    while True:
        time.sleep(2)
        try:
            if spotify.is_authenticated:
                _notify_overlay()
        except Exception:
            pass


@app.route("/")
def overlay():
    return HTML_OVERLAY


@app.route("/stream")
def overlay_stream():
    q = Queue()
    overlay_clients.add(q)
    def event_stream():
        try:
            if spotify.is_authenticated:
                data = spotify.get_current_track()
                if data and data.get("item"):
                    track = _format_track(data)
                    track["type"] = "track"
                    yield f"data: {json.dumps(track)}\n\n"
            yield f"data: {json.dumps({'type': 'connected', 'authenticated': spotify.is_authenticated})}\n\n"
            while True:
                data = q.get()
                yield f"data: {json.dumps(data)}\n\n"
        except GeneratorExit:
            pass
        finally:
            overlay_clients.remove(q)
    return Response(event_stream(), mimetype="text/event-stream")


HTML_OVERLAY = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="color-scheme" content="dark">
<style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
        background: transparent;
        font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
        overflow: hidden;
        width: 100vw;
        height: 100vh;
        display: flex;
        align-items: stretch;
    }
    #player {
        display: none;
        align-items: center;
        gap: min(11vh, 28px);
        padding: min(10vh, 24px) min(3.8vw, 32px);
        background: rgba(0,0,0,0.75);
        border-radius: min(10vh, 24px);
        border: 1px solid rgba(255,255,255,0.08);
        backdrop-filter: blur(8px);
        width: 100%;
    }
    #player.visible { display: flex; }
    #cover {
        width: min(66.7vh, 200px);
        height: min(66.7vh, 200px);
        border-radius: min(5vh, 12px);
        object-fit: cover;
        flex-shrink: 0;
        box-shadow: 0 2px 12px rgba(0,0,0,0.4);
    }
    #info { flex: 1; min-width: 0; }
    #track-name {
        color: #fff;
        font-size: min(15vh, 48px);
        font-weight: 700;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    #track-artist {
        color: rgba(255,255,255,0.7);
        font-size: min(12vh, 36px);
        margin-top: 0.15em;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    #progress-wrap {
        margin-top: min(6.7vh, 16px);
        height: min(3.3vh, 8px);
        background: rgba(255,255,255,0.15);
        border-radius: 2px;
        overflow: hidden;
    }
    #progress-bar {
        height: 100%;
        width: 0%;
        background: linear-gradient(90deg, #1db954, #1ed760);
        border-radius: 2px;
        transition: width 0.5s ease;
    }
    #status-text {
        color: rgba(255,255,255,0.5);
        font-size: min(12vh, 36px);
        text-align: center;
        padding: 2vh;
        width: 100%;
    }
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
const evtSource = new EventSource('/stream');

let progressStart = 0, durationMs = 0, lastUpdate = 0, isPlaying = false;

function updateProgress() {
    if (!durationMs) return;
    if (isPlaying) {
        const elapsed = Date.now() - lastUpdate;
        const current = Math.min(progressStart + elapsed, durationMs);
        const pct = (current / durationMs) * 100;
        progressBar.style.width = pct + '%';
    }
}

evtSource.onmessage = function(e) {
    try {
        const data = JSON.parse(e.data);
        if (data.type === 'track') {
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
        } else if (data.type === 'auth' && data.success) {
            statusText.textContent = 'Spotify connected!';
        } else if (data.type === 'no_track' && !player.classList.contains('visible')) {
            if (data.authenticated !== false) {
                statusText.textContent = 'No active track';
            } else {
                statusText.textContent = 'Spotify not connected – open /login';
            }
        } else if (data.type === 'connected' && !player.classList.contains('visible')) {
            if (data.authenticated) {
                statusText.textContent = 'No active track';
            } else {
                statusText.textContent = 'Spotify not connected – open /login';
            }
        }
    } catch(e) {}
};
evtSource.onerror = function() {
    if (!player.classList.contains('visible')) {
        statusText.textContent = 'Connection lost...';
    }
};

setInterval(updateProgress, 1000);
</script>
</body>
</html>"""

# =========================
# Server + Main
# =========================
def run_flask():
    app.run(host=SERVER_HOST, port=SPOTIFY_PORT, threaded=True)


if __name__ == "__main__":
    if not CLIENT_ID or not CLIENT_SECRET:
        print("=" * 60)
        print("  SPOTIFY PLUGIN — CONFIGURATION REQUIRED")
        print("=" * 60)
        print()
        print("  To use the Spotify plugin you need:")
        print("  1. A Spotify Developer account (https://developer.spotify.com)")
        print("  2. An app with Client ID and Client Secret")
        print("  3. Redirect URI set to: http://127.0.0.1:29194/callback")
        print()
        print("  Then add to config/config.yaml:")
        print("    spotify:")
        print("      client_id: \"YOUR_CLIENT_ID\"")
        print("      client_secret: \"YOUR_CLIENT_SECRET\"")
        print()
        print("  On first start, your browser will open for Spotify login.")
        print("=" * 60)

    server_thread = threading.Thread(target=run_flask, daemon=True)
    server_thread.start()

    polling_thread = threading.Thread(target=_poll_spotify, daemon=True)
    polling_thread.start()

    if spotify.is_authenticated:
        print(f"[SPOTIFY] Already authenticated. Starting on port {SPOTIFY_PORT}")
    else:
        print(f"[SPOTIFY] Not authenticated. Open http://127.0.0.1:{SPOTIFY_PORT}/login in your browser")
        if CLIENT_ID and CLIENT_SECRET:
            url, _ = spotify.get_auth_url()
            webbrowser.open(url)

    gui_hidden = args.gui_hidden
    if not gui_hidden:
        try:
            import webview
            window = webview.create_window(
                "Spotify Control",
                f"http://127.0.0.1:{SPOTIFY_PORT}/",
                width=440,
                height=160,
                on_top=True,
                background_color="#000000"
            )
            webview.start(debug=False)
        except ImportError:
            server_thread.join()
    else:
        print(f"[SPOTIFY] GUI hidden, running server only.")
        server_thread.join()
