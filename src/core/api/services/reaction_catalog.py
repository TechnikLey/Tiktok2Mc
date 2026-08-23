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

# Version of the unified event catalog schema. Bump when the shape of
# ``build_reaction_catalog()`` changes in a breaking way so consumers
# (GUI wizards, external tools) can detect and adapt.
CATALOG_VERSION = 1

# Built-in events that are not owned by a plugin (TikTok, Minecraft, Server).
CORE_EVENTS: dict[str, dict[str, Any]] = {
    # TikTok
    "tiktok.follow": {
        "name": "New Follower",
        "name_i18n": {"en": "New Follower", "de": "Neuer Follower"},
        "desc": "When someone follows your TikTok account",
        "desc_i18n": {
            "en": "When someone follows your TikTok account",
            "de": "Jemand folgt deinem TikTok-Account",
        },
        "category": "tiktok",
        "icon": "👤",
    },
    "tiktok.join": {
        "name": "Viewer Joins",
        "name_i18n": {"en": "Viewer Joins", "de": "Zuschauer betritt"},
        "desc": "When someone joins your live stream",
        "desc_i18n": {
            "en": "When someone joins your live stream",
            "de": "Jemand betritt deinen Live-Stream",
        },
        "category": "tiktok",
        "icon": "🚪",
    },
    "tiktok.comment": {
        "name": "New Comment",
        "name_i18n": {"en": "New Comment", "de": "Neuer Kommentar"},
        "desc": "When someone sends a chat message",
        "desc_i18n": {
            "en": "When someone sends a chat message",
            "de": "Jemand sendet eine Nachricht",
        },
        "category": "tiktok",
        "icon": "💬",
    },
    "tiktok.like": {
        "name": "New Like",
        "name_i18n": {"en": "New Like", "de": "Neues Like"},
        "desc": "When someone likes your stream",
        "desc_i18n": {
            "en": "When someone likes your stream",
            "de": "Jemand liked deinen Stream",
        },
        "category": "tiktok",
        "icon": "❤️",
    },
    "tiktok.share": {
        "name": "New Share",
        "name_i18n": {"en": "New Share", "de": "Neuer Share"},
        "desc": "When someone shares your stream",
        "desc_i18n": {
            "en": "When someone shares your stream",
            "de": "Jemand teilt deinen Stream",
        },
        "category": "tiktok",
        "icon": "🔗",
    },
    "tiktok.gift": {
        "name": "Gift Received",
        "name_i18n": {"en": "Gift Received", "de": "Geschenk erhalten"},
        "desc": "When someone sends a gift",
        "desc_i18n": {
            "en": "When someone sends a gift",
            "de": "Jemand sendet ein Geschenk",
        },
        "category": "tiktok",
        "icon": "🎁",
    },
    # Minecraft
    "minecraft.player_death": {
        "name": "Player Dies",
        "name_i18n": {"en": "Player Dies", "de": "Spieler stirbt"},
        "desc": "When you or another player dies",
        "desc_i18n": {
            "en": "When you or another player dies",
            "de": "Du oder ein anderer Spieler stirbt",
        },
        "category": "minecraft",
        "icon": "💀",
    },
    "minecraft.player_respawn": {
        "name": "Player Respawns",
        "name_i18n": {"en": "Player Respawns", "de": "Spieler spawnt neu"},
        "desc": "When a player respawns after dying",
        "desc_i18n": {
            "en": "When a player respawns after dying",
            "de": "Ein Spieler spawnt nach dem Tod neu",
        },
        "category": "minecraft",
        "icon": "✨",
    },
    # Server
    "server.started": {
        "name": "Server Starts",
        "name_i18n": {"en": "Server Starts", "de": "Server startet"},
        "desc": "When the Minecraft server finishes starting",
        "desc_i18n": {
            "en": "When the Minecraft server finishes starting",
            "de": "Der Minecraft-Server hat erfolgreich gestartet",
        },
        "category": "server",
        "icon": "🟢",
    },
    "server.stopping": {
        "name": "Server Stopping",
        "name_i18n": {"en": "Server Stopping", "de": "Server stoppt"},
        "desc": "When the Minecraft server begins to shut down",
        "desc_i18n": {
            "en": "When the Minecraft server begins to shut down",
            "de": "Der Minecraft-Server fährt herunter",
        },
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


def collect_known_event_keys(plugins_dir: Path | None = None) -> set[str]:
    """Return every event key known to the system (J.3 #12 delivery registry).

    Merges the built-in core events with every plugin's declared
    ``emitted_events``. The PluginEventBridge uses this to warn about
    subscriptions pointing at unknown event names (typo protection).
    """
    known = set(CORE_EVENTS)
    plugins_dir = plugins_dir or _plugins_dir()
    if plugins_dir is None or not plugins_dir.is_dir():
        return known

    launcher = PluginLauncher(plugins_dir=plugins_dir)
    try:
        manifests = launcher._discover_from_manifests()
    except Exception as exc:  # catalog must never break on a broken manifest
        log.warning("Failed to scan plugin manifests for emitted events: %s", exc)
        return known
    for manifest in manifests:
        for ev in manifest.emitted_events:
            known.add(ev.key)
    return known


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
            "version": CATALOG_VERSION,
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
        "version": CATALOG_VERSION,
        "events": events,
        "plugins": plugins,
        "commands": commands,
        "templates": CORE_TEMPLATES,
    }
