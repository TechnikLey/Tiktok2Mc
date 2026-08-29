"""Event-Command Mapper — central wiring between EventBus events and plugin commands.

Reads ``data/event_commands.yaml`` and dispatches plugin commands whenever
matching events arrive on the EventBus.  Zero coupling: plugins do not know
about events; the mapper does not know about plugin internals.

Config format (YAML)::_

    event_commands:
      minecraft.player_death:
        - target: my-timer-plugin
          command: pause
      some-plugin.countdown_finished:
        - target: my-scoreboard-plugin
          command: add_point
          args: {amount: 1}
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from pathlib import Path
from typing import Any

from ruamel.yaml.error import YAMLError

from core.health_monitor import HealthState, get_health_monitor
from core.paths import get_root_dir
from core.yaml_utils import load_yaml, save_yaml

log = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path("defaults/event_commands.yaml")
DATA_CONFIG_PATH = Path("data/event_commands.yaml")

MAX_HISTORY = 50


class EventCommandMapper:
    """Background task that listens to EventBus events and dispatches commands."""

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._running = False
        self._history: deque[dict[str, Any]] = deque(maxlen=MAX_HISTORY)
        self._dispatch_counts: dict[str, int] = {}
        self._health = get_health_monitor()
        self._health.register("event_command_mapper", HealthState.STARTING)

    # ------------------------------------------------------------------
    #  Config helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _config_path() -> Path:
        root = get_root_dir()
        data_path = root / DATA_CONFIG_PATH
        if data_path.exists():
            return data_path
        default_path = root / DEFAULT_CONFIG_PATH
        if default_path.exists():
            return default_path
        return data_path  # will be created empty

    def _load_mappings(self) -> dict[str, list[dict[str, Any]]]:
        """Return {event_type: [mapping, ...]} from config."""
        path = self._config_path()
        if not path.exists():
            return {}
        try:
            cfg = load_yaml(path)
            return dict(cfg.get("event_commands", {}))
        except (OSError, ValueError, YAMLError) as exc:
            log.warning("[ECM] Failed to load event_commands config: %s", exc)
            return {}

    def _ensure_config_file(self) -> None:
        """Create an empty data/event_commands.yaml if it does not exist."""
        data_path = get_root_dir() / DATA_CONFIG_PATH
        if not data_path.exists():
            data_path.parent.mkdir(parents=True, exist_ok=True)
            save_yaml(data_path, {"event_commands": {}})

    # ------------------------------------------------------------------
    #  Diagnostics
    # ------------------------------------------------------------------

    def get_diagnostics(self) -> dict[str, Any]:
        """Return current mapper diagnostics for dashboard consumers."""
        mappings = self._load_mappings()
        total_reactions = sum(len(actions) for actions in mappings.values())
        return {
            "active": self._running,
            "total_events": len(mappings),
            "total_reactions": total_reactions,
            "recent_dispatches": list(self._history),
            "dispatch_counts": dict(self._dispatch_counts),
        }

    # ------------------------------------------------------------------
    #  Dispatch
    # ------------------------------------------------------------------

    def _dispatch(self, event_type: str, event_data: dict[str, Any]) -> None:
        from core.api.plugin_overlay import command_queue

        mappings = self._load_mappings()
        actions = mappings.get(event_type)
        if not actions:
            return

        for action in actions:
            target = action.get("target")
            command = action.get("command")
            args = action.get("args", {})

            if not target or not command:
                log.warning("[ECM] Bad mapping for %s: %s", event_type, action)
                continue

            try:
                command_queue.enqueue(target, command, **args)
                self._history.append(
                    {
                        "timestamp": time.time(),
                        "event": event_type,
                        "target": target,
                        "command": command,
                        "args": args,
                        "status": "ok",
                    }
                )
                self._dispatch_counts[event_type] = (
                    self._dispatch_counts.get(event_type, 0) + 1
                )
                log.info(
                    "[ECM] Dispatched %s → %s/%s (args=%s)",
                    event_type,
                    target,
                    command,
                    args,
                )
            except (TypeError, ValueError, KeyError) as exc:
                self._history.append(
                    {
                        "timestamp": time.time(),
                        "event": event_type,
                        "target": target,
                        "command": command,
                        "args": args,
                        "status": "error",
                        "error": str(exc),
                    }
                )
                log.error(
                    "[ECM] Failed to dispatch %s → %s/%s: %s",
                    event_type,
                    target,
                    command,
                    exc,
                )
                try:
                    self._health.record_error(
                        "event_command_mapper",
                        f"Dispatch failed: {event_type} -> {target}/{command}: {exc}",
                    )
                    self._health.set_state("event_command_mapper", HealthState.DEGRADED)
                except Exception:  # best-effort health reporting
                    pass

    # ------------------------------------------------------------------
    #  Background loop
    # ------------------------------------------------------------------

    async def _loop(self) -> None:
        """Subscribe to all events and dispatch matching commands."""
        from core.api.eventbus import event_bus

        q = event_bus.subscribe()  # subscribe to ALL events
        log.info("[ECM] Event-Command Mapper started")
        try:
            while self._running:
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=5.0)
                except asyncio.TimeoutError:
                    continue

                event_type = msg.get("type", "")
                event_data = msg.get("data", {})
                self._dispatch(event_type, event_data)
        except asyncio.CancelledError:
            pass
        finally:
            event_bus.unsubscribe(q)
            log.info("[ECM] Event-Command Mapper stopped")

    # ------------------------------------------------------------------
    #  Public lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background mapper task."""
        if self._running:
            return
        self._ensure_config_file()
        self._running = True
        self._task = asyncio.create_task(self._loop())
        self._health.set_state("event_command_mapper", HealthState.RUNNING)

    async def stop(self) -> None:
        """Stop the background mapper task gracefully."""
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
        self._health.set_state("event_command_mapper", HealthState.STOPPED)


# Module-level singleton
_mapper: EventCommandMapper | None = None


def get_event_command_mapper() -> EventCommandMapper:
    """Return the global ``EventCommandMapper`` singleton."""
    global _mapper
    if _mapper is None:
        _mapper = EventCommandMapper()
    return _mapper
