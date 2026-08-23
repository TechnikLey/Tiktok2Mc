import logging

from core.hook_api import HookAPI

log = logging.getLogger(__name__)

PLUGIN_NAME = "spotify-control"


def _command(api, command, **kwargs):
    return (
        api.request(
            f"plugins/{PLUGIN_NAME}/command",
            payload={"command": command, "args": kwargs},
        )
        is not None
    )


def _cmd_post(api, user, command, action_title):
    if _command(api, command):
        api.send_overlay_text(
            title="Spotify",
            subtitle=f"{action_title} — triggered by {user}",
            duration=2,
        )


def _cmd_current(api, user):
    data = api.request(f"plugins/{PLUGIN_NAME}/state")
    state = (data or {}).get("state") if isinstance(data, dict) else None
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
    elif state is not None:
        api.send_overlay_text(title="Spotify", subtitle="No active track", duration=3)
    else:
        log.info("[SPOTIFY-HOOK] Failed to get state")


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
