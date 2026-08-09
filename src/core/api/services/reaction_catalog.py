"""Reaction catalog assembly for the GUI reactions wizard.

Merges built-in core events (TikTok, Minecraft, Server) with the
``emitted_events`` and ``accepted_commands`` declared by each plugin
manifest. Plugins self-describe their reaction capabilities in
``plugin.json`` — no GUI code changes are needed for a new plugin to
appear in the wizard.
"""

import logging
from pathlib import Path
from typing import Any

import core.paths
from core.api.launcher import PluginLauncher

log = logging.getLogger(__name__)

# Built-in events that are not owned by a plugin (TikTok, Minecraft, Server).
CORE_EVENTS: dict[str, dict[str, str]] = {
    # TikTok
    "tiktok.follow": {
        "name": "New Follower",
        "desc": "When someone follows your TikTok account",
        "category": "tiktok",
        "icon": "👤",
    },
    "tiktok.join": {
        "name": "Viewer Joins",
        "desc": "When someone joins your live stream",
        "category": "tiktok",
        "icon": "🚪",
    },
    "tiktok.comment": {
        "name": "New Comment",
        "desc": "When someone sends a chat message",
        "category": "tiktok",
        "icon": "💬",
    },
    "tiktok.like": {
        "name": "New Like",
        "desc": "When someone likes your stream",
        "category": "tiktok",
        "icon": "❤️",
    },
    "tiktok.share": {
        "name": "New Share",
        "desc": "When someone shares your stream",
        "category": "tiktok",
        "icon": "🔗",
    },
    "tiktok.gift": {
        "name": "Gift Received",
        "desc": "When someone sends a gift",
        "category": "tiktok",
        "icon": "🎁",
    },
    # Minecraft
    "minecraft.player_death": {
        "name": "Player Dies",
        "desc": "When you or another player dies",
        "category": "minecraft",
        "icon": "💀",
    },
    "minecraft.player_respawn": {
        "name": "Player Respawns",
        "desc": "When a player respawns after dying",
        "category": "minecraft",
        "icon": "✨",
    },
    # Server
    "server.started": {
        "name": "Server Starts",
        "desc": "When the Minecraft server finishes starting",
        "category": "server",
        "icon": "🟢",
    },
    "server.stopping": {
        "name": "Server Stopping",
        "desc": "When the Minecraft server begins to shut down",
        "category": "server",
        "icon": "🛑",
    },
}

# Quick-start presets shown on the empty reactions screen.
CORE_TEMPLATES: list[dict[str, Any]] = [
    {
        "event": "minecraft.player_death",
        "plugin": "spotify-control",
        "command": "pause",
        "args": {},
        "title": "Pause Music on Death",
        "desc": "Automatically pause Spotify when you die in Minecraft.",
    },
    {
        "event": "timer.zero",
        "plugin": "win-counter",
        "command": "add_win",
        "args": {"amount": 1},
        "title": "Add Win on Timer",
        "desc": "Award a win when the countdown timer hits zero.",
    },
    {
        "event": "tiktok.gift",
        "plugin": "timer",
        "command": "add_time",
        "args": {"seconds": 30},
        "title": "Add Time on Gift",
        "desc": "Add 30 seconds to the timer every time someone sends a gift.",
    },
]


def _plugins_dir() -> Path | None:
    """Return the plugins directory (dev or release layout), or None."""
    root = core.paths.get_root_dir()
    for candidate in (root / "src" / "plugins", root / "plugins"):
        if candidate.is_dir():
            return candidate
    return None


def build_reaction_catalog() -> dict[str, Any]:
    """Assemble the full reaction catalog from core + plugin manifests.

    Returns ``{"events": ..., "plugins": ..., "commands": ...,
    "templates": [...]}``.  Plugin-declared entries always override any
    core entry with the same key so plugins can extend or replace the
    built-in catalog.
    """
    events: dict[str, dict[str, Any]] = dict(CORE_EVENTS)
    plugins: dict[str, dict[str, Any]] = {}
    commands: dict[str, dict[str, Any]] = {}

    plugins_dir = _plugins_dir()
    if plugins_dir is None:
        log.warning(
            "Plugins directory not found — reaction catalog has core events only"
        )
        return {
            "events": events,
            "plugins": plugins,
            "commands": commands,
            "templates": CORE_TEMPLATES,
        }

    launcher = PluginLauncher(plugins_dir=plugins_dir)
    for manifest in launcher._discover_from_manifests():
        plugins[manifest.name] = {
            "name": manifest.display_name or manifest.name,
            "desc": manifest.description,
            "icon": manifest.icon,
        }
        for ev in manifest.emitted_events:
            data = ev.model_dump()
            # Plugin events are grouped under the plugin's own name.
            data["category"] = manifest.name
            events[ev.key] = data
        if manifest.accepted_commands:
            commands[manifest.name] = {
                key: cmd.model_dump() for key, cmd in manifest.accepted_commands.items()
            }

    return {
        "events": events,
        "plugins": plugins,
        "commands": commands,
        "templates": CORE_TEMPLATES,
    }
