#!/usr/bin/env python3
# ==================================================
# spotify.py - Spotify Control Event Hook
# ==================================================
# Registers $spotify* direct-trigger actions for
# gifts, follows, likes etc. in actions.mca.
#
# Chat-based commands (!spotify, !sp) are handled
# by the comment_commands HTTP handler instead.
#
# USAGE in actions.mca:
#   follow:$spotify_current              # Shows current track on follow
#   gift_id:$spotify_play                # Resumes playback
#   gift_id:$spotify_pause               # Pauses playback
#   gift_id:$spotify_skip                # Next track
#   gift_id:$spotify_previous            # Previous track
#   gift_id:$spotify_volume_up           # Volume up
#   gift_id:$spotify_volume_down         # Volume down
#   gift_id:$spotify_save                # Save song to library
#   gift_id:$spotify_shuffle             # Toggle shuffle
#   gift_id:$spotify_repeat              # Toggle repeat
# ==================================================

from core.hook_api import HookAPI
import logging
log = logging.getLogger(__name__)

PLUGIN_PORT = 29194
PLUGIN_BASE = f"http://127.0.0.1:{PLUGIN_PORT}"


def _request(method, path, **kwargs):
    try:
        import requests
        resp = requests.request(method, f"{PLUGIN_BASE}{path}", timeout=5, **kwargs)
        if resp.status_code == 200:
            return resp.json()
        return None
    except requests.ConnectionError:
        return None
    except Exception as e:
        log.info(f"[SPOTIFY-HOOK] Request error: {e}")
        return None


def _cmd_post(api, user, path, action_name):
    result = _request("POST", path)
    if result is not None:
        api.send_overlay_text(
            title="Spotify",
            subtitle=f"{action_name} — triggered by {user}",
            duration=2
        )


def _cmd_current(api, user):
    track = _request("GET", "/current")
    if track and "name" in track:
        progress = track.get("progress_sec", 0)
        duration = track.get("duration_sec", 0)
        pct = f"{progress // 60:02d}:{progress % 60:02d} / {duration // 60:02d}:{duration % 60:02d}" if duration else ""
        api.send_overlay_text(
            title=track["name"],
            subtitle=f"{track['artists']}  |  {pct}",
            duration=6
        )
    else:
        api.send_overlay_text(
            title="Spotify",
            subtitle="No active track",
            duration=3
        )


def register(api: HookAPI):
    def _make_handler(path, action_title):
        def handler(user, trigger, context):
            if isinstance(user, dict):
                _cmd_post(api, user.get("user", "Unknown"), path, action_title)
                return
            _cmd_post(api, str(user), path, action_title)
        return handler

    api.register_action("spotify_play", _make_handler("/play", "Play"))
    api.register_action("spotify_pause", _make_handler("/pause", "Pause"))
    api.register_action("spotify_next", _make_handler("/next", "Next"))
    api.register_action("spotify_skip", _make_handler("/next", "Skip"))
    api.register_action("spotify_previous", _make_handler("/previous", "Previous"))
    api.register_action("spotify_volume_up", _make_handler("/volume/up", "Volume Up"))
    api.register_action("spotify_volume_down", _make_handler("/volume/down", "Volume Down"))
    api.register_action("spotify_save", _make_handler("/save", "Saved"))
    api.register_action("spotify_shuffle", _make_handler("/shuffle?state=toggle", "Shuffle"))
    api.register_action("spotify_repeat", _make_handler("/repeat?state=toggle", "Repeat"))

    def current_handler(user, trigger, context):
        if isinstance(user, dict):
            _cmd_current(api, user.get("user", "Unknown"))
        else:
            _cmd_current(api, str(user))

    api.register_action("spotify_current", current_handler)

    log.info("[SPOTIFY-HOOK] Direct-trigger actions loaded (chat commands handled by comment_commands)")
