"""Declarative plugin event bridge (API process).

Routes EventBus events to plugins that declare ``event_subscriptions`` in
their ``plugin.json``, and delivers prefixed comments to plugins that
declare a ``comment_handler``. TikTok events arrive as a standardized
``tiktok_event`` command; every other bus source (Minecraft webhooks,
timers, server lifecycle, plugin-emitted events) arrives as a generic
``bus_event`` command.

This service intentionally runs in the **API process** — the same process
that owns the polled ``command_queue`` — so dispatched commands actually
reach the plugin subprocesses.  The historical implementation lived in the
bridge process and enqueued into an orphaned in-process queue, which meant
declared subscriptions were silently never delivered.

Delivery contracts (docs/dev-book ``ch03-05``):

* ``event_subscriptions: ["tiktok.gift", "tiktok.*"]`` → a standardized
  ``tiktok_event`` command carrying ``event_type`` / ``user`` / ``data``
  (TikTok events always carry a ``user``).
* Subscriptions to **any other bus source** (``minecraft.*``, ``timer.*``,
  ``server.*``, plugin-emitted events, or the catch-all ``*``) → a
  ``bus_event`` command carrying ``event_type`` / ``data`` — no ``user``
  is required for these sources.
* ``comment_handler: {"prefix": "$", "enabled": true}`` → a ``comment``
  command carrying ``text`` (prefix stripped) and ``username`` for every
  ``tiktok.comment`` whose text starts with the prefix.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any

from core.health_monitor import HealthState, get_health_monitor
from core.plugin_config import discover_plugins_dir, load_plugin_manifest

log = logging.getLogger(__name__)

DEFAULT_COMMENT_PREFIX = "$"


def match_event(event_type: str, pattern: str) -> bool:
    """Return whether *event_type* matches a subscription *pattern*.

    Supports the catch-all (``*``), exact names (``tiktok.gift``) and
    trailing wildcards (``tiktok.*`` matches every ``tiktok.<suffix>``).
    """
    if pattern == "*":
        return True
    if pattern == event_type:
        return True
    if pattern.endswith(".*"):
        prefix = pattern[:-2]
        return event_type.startswith(prefix + ".")
    return False


def load_manifest_declarations(
    plugins_dir: Any = None,
) -> tuple[dict[str, list[str]], dict[str, dict[str, Any]]]:
    """Scan plugin manifests and extract declarative delivery rules.

    Returns ``(subscriptions, comment_handlers)`` where *subscriptions*
    maps ``pattern -> [plugin_names]`` and *comment_handlers* maps
    ``plugin_name -> {"prefix": str}`` for enabled handlers only.
    """
    subs: dict[str, list[str]] = {}
    handlers: dict[str, dict[str, Any]] = {}
    if plugins_dir is None:
        plugins_dir = discover_plugins_dir()
    if not plugins_dir.is_dir():
        return subs, handlers

    for child in sorted(plugins_dir.iterdir()):
        if not child.is_dir():
            continue
        manifest = load_plugin_manifest(child)
        if not manifest:
            continue
        name = manifest.get("name", "")
        if not name:
            continue
        for pattern in manifest.get("event_subscriptions", []):
            subs.setdefault(str(pattern), []).append(name)
        declared = manifest.get("comment_handler")
        if isinstance(declared, dict) and declared.get("enabled", True):
            handlers[name] = {
                "prefix": str(declared.get("prefix") or DEFAULT_COMMENT_PREFIX),
            }

    log.info(
        "[EVENT-BRIDGE] Loaded %d subscription pattern(s), %d comment handler(s)",
        len(subs),
        len(handlers),
    )
    return subs, handlers


class PluginEventBridge:
    """Background task that forwards bus events to subscribed plugins."""

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._running = False
        self._lock = threading.Lock()
        self._subscriptions: dict[str, list[str]] = {}
        self._comment_handlers: dict[str, dict[str, Any]] = {}
        self._health = get_health_monitor()
        self._health.register("plugin_event_bridge", HealthState.UNKNOWN)

    # ------------------------------------------------------------------
    #  Declarations
    # ------------------------------------------------------------------

    def refresh_subscriptions(self) -> None:
        """Reload manifest declarations (thread-safe)."""
        subscriptions, comment_handlers = load_manifest_declarations()
        with self._lock:
            self._subscriptions = subscriptions
            self._comment_handlers = comment_handlers
        self._warn_unknown_subscriptions(subscriptions)

    @staticmethod
    def _warn_unknown_subscriptions(subscriptions: dict[str, list[str]]) -> None:
        """Warn about exact-name subscriptions no source declares (J.3 #12).

        Uses the unified event catalog (core events + every plugin's
        ``emitted_events``) as the delivery registry. Wildcards are never
        flagged — they intentionally cover events that may appear later.
        Best-effort: catalog failures must not affect delivery.
        """
        try:
            from core.api.services.reaction_catalog import collect_known_event_keys

            known = collect_known_event_keys()
        except Exception as exc:
            log.debug("[EVENT-BRIDGE] Event catalog unavailable: %s", exc)
            return
        for pattern, names in sorted(subscriptions.items()):
            if pattern == "*" or pattern.endswith(".*"):
                continue
            if pattern not in known:
                log.warning(
                    "[EVENT-BRIDGE] Plugin(s) %s subscribe to unknown event '%s' "
                    "(no core event or emitted_events declaration matches)",
                    ", ".join(sorted(set(names))),
                    pattern,
                )

    # ------------------------------------------------------------------
    #  Dispatch
    # ------------------------------------------------------------------

    def _recipients_for(self, event_type: str) -> set[str]:
        with self._lock:
            subscriptions = dict(self._subscriptions)
        recipients: set[str] = set()
        for pattern, names in subscriptions.items():
            if match_event(event_type, pattern):
                recipients.update(names)
        return recipients

    def _comment_recipients(self, comment_text: str) -> list[tuple[str, str]]:
        """Return ``(plugin_name, stripped_text)`` for matching handlers."""
        with self._lock:
            handlers = dict(self._comment_handlers)
        matched: list[tuple[str, str]] = []
        for name, config in handlers.items():
            prefix = config.get("prefix", DEFAULT_COMMENT_PREFIX)
            if not prefix or not comment_text.startswith(prefix):
                continue
            matched.append((name, comment_text[len(prefix) :]))
        return matched

    def _dispatch(self, event_type: str, event_data: dict[str, Any]) -> None:
        """Route one bus event to all matching plugins (pure logic, no loop)."""
        from core.api.plugin_overlay import command_queue

        if event_type.startswith("tiktok."):
            user = event_data.get("user")
            if not user:
                return

            data = {k: v for k, v in event_data.items() if k != "user"}

            for plugin_name in self._recipients_for(event_type):
                command_queue.enqueue(
                    plugin_name,
                    "tiktok_event",
                    event_type=event_type,
                    user=user,
                    data=data,
                )
                log.debug(
                    "[EVENT-BRIDGE] %s → %s (tiktok_event)", event_type, plugin_name
                )

            if event_type == "tiktok.comment":
                comment_text = str(data.get("comment", ""))
                if comment_text:
                    for plugin_name, stripped in self._comment_recipients(comment_text):
                        command_queue.enqueue(
                            plugin_name,
                            "comment",
                            text=stripped,
                            username=user,
                        )
                        log.debug(
                            "[EVENT-BRIDGE] comment → %s (user=%s)", plugin_name, user
                        )
            return

        # Generic bus sources (minecraft.*, timer.*, server.*, plugin events):
        # deliver as ``bus_event`` without requiring a ``user`` field.
        recipients = self._recipients_for(event_type)
        if not recipients:
            return
        data = dict(event_data)
        for plugin_name in recipients:
            command_queue.enqueue(
                plugin_name,
                "bus_event",
                event_type=event_type,
                data=data,
            )
            log.debug("[EVENT-BRIDGE] %s → %s (bus_event)", event_type, plugin_name)

    # ------------------------------------------------------------------
    #  Background loop
    # ------------------------------------------------------------------

    async def _loop(self) -> None:
        from core.api.eventbus import event_bus

        q = event_bus.subscribe()  # all events; filtered in _dispatch
        log.info("[EVENT-BRIDGE] PluginEventBridge started (declarative)")
        try:
            while self._running:
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=5.0)
                except asyncio.TimeoutError:
                    continue
                try:
                    self._dispatch(msg.get("type", ""), msg.get("data", {}))
                except Exception as exc:  # worker must never die
                    log.error("[EVENT-BRIDGE] Dispatch failed: %s", exc)
                    try:
                        self._health.record_error(
                            "plugin_event_bridge", f"Dispatch failed: {exc}"
                        )
                        self._health.set_state(
                            "plugin_event_bridge", HealthState.DEGRADED
                        )
                    except Exception:  # best-effort health reporting
                        pass
        except asyncio.CancelledError:
            pass
        finally:
            event_bus.unsubscribe(q)
            log.info("[EVENT-BRIDGE] PluginEventBridge stopped")

    # ------------------------------------------------------------------
    #  Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        if self._running:
            return
        self.refresh_subscriptions()
        self._running = True
        self._task = asyncio.create_task(self._loop())
        self._health.set_state("plugin_event_bridge", HealthState.RUNNING)

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self._health.set_state("plugin_event_bridge", HealthState.STOPPED)


# Module-level singleton
_bridge: PluginEventBridge | None = None


def get_plugin_event_bridge() -> PluginEventBridge:
    """Return the global ``PluginEventBridge`` singleton."""
    global _bridge
    if _bridge is None:
        _bridge = PluginEventBridge()
    return _bridge
