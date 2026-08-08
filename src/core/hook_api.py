from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

log = logging.getLogger(__name__)

HOOK_ACTIONS: dict[str, Callable] = {}

MAX_CHAIN_DEPTH: int = 3


class HookAPI:
    """
    Runtime API passed to every event_hook script via its ``register()`` function.

    Provides controlled access to main.py internals (RCON queue, trigger queue)
    and per-hook config via ``get_hook_config()``.
    """

    def __init__(
        self,
        rcon_queue: asyncio.Queue,
        trigger_queue: asyncio.Queue,
        main_loop: asyncio.AbstractEventLoop,
        config: dict,
        valid_functions: set[str],
        hook_configs: dict[str, dict] | None = None,
    ) -> None:
        self._rcon_queue = rcon_queue
        self._trigger_queue = trigger_queue
        self._main_loop = main_loop
        self._config = config
        self._valid_functions = valid_functions
        self._hook_configs: dict[str, dict] = hook_configs or {}
        self._current_depth: int = 0
        self._banned_triggers: set[str] = set()

    # --------------------------------------------------
    # Public API
    # --------------------------------------------------

    @property
    def config(self) -> dict:
        """Read-only access to the loaded global config.yaml values."""
        from copy import deepcopy
        return deepcopy(self._config)

    def get_hook_config(self, name: str) -> dict:
        """Return the per-hook config for a named hook.

        Falls back to an empty dict if the hook has no config.
        """
        return self._hook_configs.get(name, {})

    def set_depth(self, depth: int) -> None:
        self._current_depth = depth

    def register_action(self, name: str, fn: Callable) -> None:
        """
        Register a handler under the given name.
        The name must match the $-command in actions.mca.
        First registration wins — duplicates are ignored with a warning.
        """
        if not isinstance(name, str) or not name.strip():
            log.info(f"[HOOK] register_action: invalid name: {name!r}")
            return
        if name in HOOK_ACTIONS:
            log.warning(f"[HOOK] Duplicate action '{name}' — first registration kept.")
            return
        HOOK_ACTIONS[name] = fn
        log.info(f"[HOOK] Registered action: {name}")

    def rcon_enqueue(self, commands: list[str]) -> None:
        if not commands:
            return
        try:
            self._main_loop.call_soon_threadsafe(
                self._rcon_queue.put_nowait, (commands, "hook")
            )
        except asyncio.QueueFull:
            log.warning("[HOOK] RCON queue full — commands dropped.")

    def enqueue_trigger(self, action_name: str, user: str = "hook") -> None:
        if action_name in self._banned_triggers:
            log.error(f"[HOOK] enqueue_trigger('{action_name}') permanently blocked "
                  f"— trigger was banned after loop detection.")
            return
        depth = self._current_depth + 1
        if depth > MAX_CHAIN_DEPTH:
            self._banned_triggers.add(action_name)
            log.error(f"[HOOK] enqueue_trigger('{action_name}') blocked — "
                  f"chain depth {depth} exceeds maximum ({MAX_CHAIN_DEPTH}). "
                  f"Trigger '{action_name}' is now permanently banned for this session. "
                  f"Possible infinite loop.")
            return
        try:
            self._main_loop.call_soon_threadsafe(
                self._trigger_queue.put_nowait, (action_name, user, depth)
            )
        except asyncio.QueueFull:
            log.warning(f"[HOOK] Trigger queue full — '{action_name}' dropped.")

    def log(self, msg: str) -> None:
        log.info(f"[HOOK] {msg}")

    def send_overlay_text(self, title: str, subtitle: str | None = "", duration: int | None = 3, overlay_name: str | None = "default") -> bool:
        try:
            from core.overlay_utils import send_overlay_text as _send_overlay
            return _send_overlay(title, subtitle, duration, overlay_name)
        except Exception as e:  # hook boundary: overlay failure must never crash trigger dispatch
            log.error(f"[HOOK] send_overlay_text failed: {e}")
            return False

    def get_valid_functions(self) -> set[str]:
        return self._valid_functions

    def update_runtime_state(
        self,
        config: dict | None = None,
        valid_functions: set[str] | None = None,
    ) -> None:
        """Update references to runtime state after a live reload."""
        if config is not None:
            self._config = config
        if valid_functions is not None:
            self._valid_functions = valid_functions
