import json
import logging
import urllib.request

from core.hook_api import HookAPI

log = logging.getLogger(__name__)

API_BASE = "http://127.0.0.1:29185/api/v1"
PLUGIN_NAME = "spotify-control"


def _command(api, command, **kwargs):
    try:
        body = json.dumps({"command": command, "args": kwargs}).encode()
        req = urllib.request.Request(
            f"{API_BASE}/plugins/{PLUGIN_NAME}/command",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=5)
        return True
    except OSError as e:
        log.info(f"[SPOTIFY-HOOK] Command '{command}' failed: {e}")
        return False


def _cmd_post(api, user, command, action_name):
    if _command(api, command):
        api.send_overlay_text(
            title="Spotify", subtitle=f"{action_name} — triggered by {user}", duration=2
        )


def _cmd_current(api, user):
    try:
        resp = urllib.request.urlopen(
            f"{API_BASE}/plugins/{PLUGIN_NAME}/state", timeout=5
        )
        data = json.loads(resp.read().decode())
        state = data.get("state", {})
        if state and state.get("name"):
            progress = state.get("progress_sec", 0)
            duration = state.get("duration_sec", 0)
            pct = (
                f"{progress // 60:02d}:{progress % 60:02d} / {duration // 60:02d}:{duration % 60:02d}"
                if duration
                else ""
            )
            api.send_overlay_text(
                title=state["name"],
                subtitle=f"{state['artists']}  |  {pct}",
                duration=6,
            )
        else:
            api.send_overlay_text(
                title="Spotify", subtitle="No active track", duration=3
            )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        log.info(f"[SPOTIFY-HOOK] Failed to get state: {e}")
        api.send_overlay_text(title="Spotify", subtitle="No active track", duration=3)


def register(api: HookAPI):
    def _make_handler(command, action_title):
        def handler(user, trigger, context):
            _cmd_post(api, str(user), command, action_title)

        return handler

    api.register_action("spotify_play", _make_handler("play", "Play"))
    api.register_action("spotify_pause", _make_handler("pause", "Pause"))
    api.register_action("spotify_next", _make_handler("next", "Next"))
    api.register_action("spotify_skip", _make_handler("next", "Skip"))
    api.register_action("spotify_previous", _make_handler("previous", "Previous"))
    api.register_action("spotify_volume_up", _make_handler("volume_up", "Volume Up"))
    api.register_action(
        "spotify_volume_down", _make_handler("volume_down", "Volume Down")
    )
    api.register_action("spotify_save", _make_handler("save", "Saved"))
    api.register_action("spotify_shuffle", _make_handler("shuffle", "Shuffle"))
    api.register_action("spotify_repeat", _make_handler("repeat", "Repeat"))

    def current_handler(user, trigger, context):
        _cmd_current(api, str(user))

    api.register_action("spotify_current", current_handler)

    log.info(
        "[SPOTIFY-HOOK] Direct-trigger actions loaded (chat commands handled by comment_commands)"
    )
