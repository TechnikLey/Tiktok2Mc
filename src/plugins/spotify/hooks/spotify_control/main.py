"""Hook that exposes Spotify playback commands to trigger actions."""

import logging

from core.hook_api import HookAPI

log = logging.getLogger(__name__)

PLUGIN_NAME = "spotify-control"


def _command(api, command, **kwargs):
    """Send a command to the Spotify plugin and report whether it was accepted.

Args:
    api: Hook API used for the request.
    command: Plugin command name such as ``play``.
    **kwargs: Arguments forwarded as the command's ``args`` object.

Returns:
    ``True`` when the API returned a response, ``False`` otherwise."""

    return (
        api.request(
            f"plugins/{PLUGIN_NAME}/command",
            payload={"command": command, "args": kwargs},
        )
        is not None
    )


def _cmd_post(api, user, command, action_title):
    """Run a playback command and show a short overlay confirmation on success.

Args:
    api: Hook API used for the request and overlay.
    user: Display name shown in the confirmation.
    command: Plugin command name.
    action_title: Human-readable action label."""

    if _command(api, command):
        api.send_overlay_text(
            title="Spotify",
            subtitle=f"{action_title} — triggered by {user}",
            duration=2,
        )


def _cmd_current(api, user):
    """Show the currently playing track, or a status message, on the overlay.

The state endpoint is queried first; progress is only shown when the
duration is known."""

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
    """Register the Spotify trigger actions exposed by this hook.

Each action forwards to the Spotify plugin and reports success on the
overlay. Chat-command handling lives in ``comment_commands`` instead."""

    def _make_handler(command, action_title):
        """Build an action handler that runs ``command`` and reports ``action_title``.

Args:
    command: Plugin command name.
    action_title: Human-readable action label.

Returns:
    A handler accepting ``(user, trigger, context)``."""

        def handler(user, trigger, context):
            """Handle one Spotify trigger action.

Args:
    user: User who triggered the action.
    trigger: Trigger name (unused).
    context: Trigger context (unused)."""

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
        """Show the current track for the ``spotify_current`` action.

Args:
    user: User who triggered the action.
    trigger: Trigger name (unused).
    context: Trigger context (unused)."""

        _cmd_current(api, str(user))

    api.register_action("spotify_current", current_handler)

    log.info(
        "[SPOTIFY-HOOK] Direct-trigger actions loaded (chat commands handled by comment_commands)"
    )
