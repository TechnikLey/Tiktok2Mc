# ==================================================
# hook_api.py - Event Hook API for $-commands
# ==================================================
# Provides the HookAPI class that is passed to every
# event_hook script via its register(api) function.
# Also holds the global HOOK_ACTIONS registry.
# ==================================================

from __future__ import annotations

import asyncio
from typing import Callable

# Global registry: action_name -> handler callable
HOOK_ACTIONS: dict[str, Callable] = {}

# Built-in $-commands handled directly by main.py — cannot be overridden by hooks
_RESERVED_NAMES: frozenset[str] = frozenset({"random"})

# Maximum trigger chain depth before enqueue_trigger blocks (prevents infinite loops)
MAX_CHAIN_DEPTH: int = 3

class HookAPI:
    """
    Runtime API passed to every event_hook script.
    Provides controlled access to main.py internals.

    Usage inside a hook script:
        def register(api):
            api.register_action("my_action", my_handler)

        def my_handler(user, trigger, context):
            api.rcon_enqueue(["say Hello " + user])
    """

    def __init__(
        self,
        rcon_queue: asyncio.Queue,
        trigger_queue: asyncio.Queue,
        main_loop: asyncio.AbstractEventLoop,
        config: dict,
    ) -> None:
        self._rcon_queue = rcon_queue
        self._trigger_queue = trigger_queue
        self._main_loop = main_loop
        self._config = config
        self._current_depth: int = 0  # Set by main.py before each handler call
        self._banned_triggers: set[str] = set()  # Triggers blocked after loop detection

    # --------------------------------------------------
    # Public API
    # --------------------------------------------------

    @property
    def config(self) -> dict:
        """Read-only access to the loaded config.yaml values."""
        return self._config

    def register_action(self, name: str, fn: Callable) -> None:
        """
        Register a handler under the given name.
        The name must match the $-command in actions.mca.
        First registration wins — duplicates are ignored with a warning.
        """
        if not isinstance(name, str) or not name.strip():
            print(f"[HOOK] register_action: invalid name: {name!r}")
            return
        if name in _RESERVED_NAMES:
            print(f"[HOOK] [ERROR] '{name}' is a reserved built-in command — cannot be overridden by a hook.")
            return
        if name in HOOK_ACTIONS:
            print(f"[HOOK] [WARN] Duplicate action '{name}' — first registration kept.")
            return
        HOOK_ACTIONS[name] = fn
        print(f"[HOOK] Registered action: {name}")

    def rcon_enqueue(self, commands: list[str]) -> None:
        """
        Enqueue a list of Minecraft RCON commands for execution.
        Commands are run in order by the RCON worker.
        """
        if not commands:
            return
        try:
            self._main_loop.call_soon_threadsafe(
                self._rcon_queue.put_nowait, (commands, "hook")
            )
        except asyncio.QueueFull:
            print("[HOOK] [WARN] RCON queue full — commands dropped.")

    def enqueue_trigger(self, action_name: str, user: str = "hook") -> None:
        """
        Push another trigger into the trigger queue.
        Useful for chaining actions.
        """
        if action_name in self._banned_triggers:
            print(f"[HOOK] [ERROR] enqueue_trigger('{action_name}') permanently blocked "
                  f"— trigger was banned after loop detection.")
            return
        depth = self._current_depth + 1
        if depth > MAX_CHAIN_DEPTH:
            self._banned_triggers.add(action_name)
            print(f"[HOOK] [ERROR] enqueue_trigger('{action_name}') blocked — "
                  f"chain depth {depth} exceeds maximum ({MAX_CHAIN_DEPTH}). "
                  f"Trigger '{action_name}' is now permanently banned for this session. "
                  f"Possible infinite loop.")
            return
        try:
            self._main_loop.call_soon_threadsafe(
                self._trigger_queue.put_nowait, (action_name, user, depth)
            )
        except asyncio.QueueFull:
            print(f"[HOOK] [WARN] Trigger queue full — '{action_name}' dropped.")

    def log(self, msg: str) -> None:
        """Print a message with [HOOK] prefix."""
        print(f"[HOOK] {msg}")