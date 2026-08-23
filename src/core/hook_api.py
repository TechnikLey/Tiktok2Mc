from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import urllib.error
import urllib.request
from collections.abc import Callable

log = logging.getLogger(__name__)

HOOK_ACTIONS: dict[str, Callable] = {}

# Action name -> hook manifest name that registered it. Maintained alongside
# HOOK_ACTIONS so a runtime hook reload can unload exactly what each hook owns.
HOOK_ACTION_OWNERS: dict[str, str] = {}

# Lifecycle callbacks per event ("live_start" / "live_end"):
# {event: {hook_name: callable}}
HOOK_LIFECYCLE: dict[str, dict[str, Callable]] = {
    "live_start": {},
    "live_end": {},
}

LIFECYCLE_EVENTS = tuple(HOOK_LIFECYCLE)

MAX_CHAIN_DEPTH: int = 3

_API_PORT = int(os.environ.get("RESOLVED_PORT_API_PORT", "29185"))
_API_BASE = os.environ.get("API_BASE_URL", f"http://127.0.0.1:{_API_PORT}/api/v1")

_STORE_TIMEOUT = 5
_NAMESPACE_OK = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class HookAPI:
    """
    Runtime API passed to every event_hook script via its ``register()`` function.

    Provides controlled access to main.py internals (RCON queue, trigger queue)
    and per-hook config via ``get_hook_config()``.

    Each hook receives its own view created via :meth:`for_hook` (bound to the
    hook's manifest name), so the persistent-store helpers automatically use
    the hook's own namespace.
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
        self._name: str = ""

    # --------------------------------------------------
    # Public API
    # --------------------------------------------------

    def for_hook(self, name: str) -> HookAPI:
        """Return a per-hook view of this shared API bound to *name*.

        Used by the loader so each hook's ``register()`` gets an API whose
        persistent-store helpers target the hook's own namespace.  All other
        methods share the same queues/config references as the root instance.
        """
        clone = HookAPI(
            self._rcon_queue,
            self._trigger_queue,
            self._main_loop,
            self._config,
            self._valid_functions,
            self._hook_configs,
        )
        clone._name = name
        return clone

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

        Veto contract: the bridge calls ``fn(user, trigger, context)`` and
        aborts the rest of the trigger chain when the handler returns
        ``False``. Returning ``None`` (the default) or ``True`` continues.
        """
        if not isinstance(name, str) or not name.strip():
            log.info(f"[HOOK] register_action: invalid name: {name!r}")
            return
        if name in HOOK_ACTIONS:
            log.warning(f"[HOOK] Duplicate action '{name}' — first registration kept.")
            return
        HOOK_ACTIONS[name] = fn
        HOOK_ACTION_OWNERS[name] = self._name or "<unbound>"
        log.info(f"[HOOK] Registered action: {name}")

    def register_lifecycle(self, event: str, fn: Callable) -> None:
        """Register a lifecycle callback for ``"live_start"`` or ``"live_end"``.

        The callback is called with no arguments when the TikTok connection is
        established / the live stream ends. Unknown events are rejected.
        Last registration wins per hook and event.
        """
        if event not in HOOK_LIFECYCLE:
            log.warning(
                "[HOOK] register_lifecycle: unknown event %r (supported: %s)",
                event,
                ", ".join(LIFECYCLE_EVENTS),
            )
            return
        if not callable(fn):
            log.warning("[HOOK] register_lifecycle(%r): not callable", event)
            return
        HOOK_LIFECYCLE[event][self._name or "<unbound>"] = fn

    def on_live_start(self, fn: Callable) -> None:
        """Shortcut for ``register_lifecycle("live_start", fn)``."""
        self.register_lifecycle("live_start", fn)

    def on_live_end(self, fn: Callable) -> None:
        """Shortcut for ``register_lifecycle("live_end", fn)``."""
        self.register_lifecycle("live_end", fn)

    @staticmethod
    def _put_nowait_guarded(queue: asyncio.Queue, item: object, label: str) -> None:
        """Put an item on a bounded queue, catching ``QueueFull`` in the callback.

        ``call_soon_threadsafe(queue.put_nowait, ...)`` raises ``QueueFull``
        inside the loop callback rather than in the calling thread, so a
        surrounding ``try/except asyncio.QueueFull`` never fires.  This wrapper
        performs the put inside the callback so drops are actually logged.
        """
        try:
            queue.put_nowait(item)
        except asyncio.QueueFull:
            log.warning("[HOOK] %s dropped — queue full", label)

    def _enqueue_threadsafe(
        self, queue: asyncio.Queue, item: object, label: str
    ) -> None:
        try:
            self._main_loop.call_soon_threadsafe(
                self._put_nowait_guarded, queue, item, label
            )
        except RuntimeError:
            log.warning("[HOOK] %s dropped — main loop not running", label)

    def rcon_enqueue(self, commands: list[str]) -> None:
        if not commands:
            return
        self._enqueue_threadsafe(
            self._rcon_queue, (commands, "hook"), f"rcon:{commands!r}"
        )

    def enqueue_trigger(
        self, action_name: str, user: str = "hook", context: dict | None = None
    ) -> None:
        """Enqueue another trigger chain.

        ``context`` optionally carries structured event data (see the hook
        context contract in the dev book) that the target chain's hook
        actions receive as their third handler argument. When omitted, the
        new chain starts with a fresh ``{"source": "hook"}`` context.
        """
        if action_name in self._banned_triggers:
            log.error(
                f"[HOOK] enqueue_trigger('{action_name}') permanently blocked "
                f"— trigger was banned after loop detection."
            )
            return
        depth = self._current_depth + 1
        if depth > MAX_CHAIN_DEPTH:
            self._banned_triggers.add(action_name)
            log.error(
                f"[HOOK] enqueue_trigger('{action_name}') blocked — "
                f"chain depth {depth} exceeds maximum ({MAX_CHAIN_DEPTH}). "
                f"Trigger '{action_name}' is now permanently banned for this session. "
                f"Possible infinite loop."
            )
            return
        ctx_data = dict(context) if isinstance(context, dict) else {}
        ctx_data.setdefault("source", "hook")
        if self._name:
            ctx_data.setdefault("hook", self._name)
        self._enqueue_threadsafe(
            self._trigger_queue,
            (action_name, user, depth, ctx_data),
            f"trigger:{action_name}",
        )

    def log(self, msg: str) -> None:
        log.info(f"[HOOK] {msg}")

    def send_overlay_text(
        self,
        title: str,
        subtitle: str = "",
        duration: int | None = 3,
        overlay_name: str | None = "default",
    ) -> bool:
        try:
            from core.overlay_utils import send_overlay_text as _send_overlay

            return _send_overlay(
                title,
                subtitle,
                duration if duration is not None else 3,
                overlay_name if overlay_name is not None else "default",
            )
        except (
            Exception
        ) as e:  # hook boundary: overlay failure must never crash trigger dispatch
            log.error(f"[HOOK] send_overlay_text failed: {e}")
            return False

    def get_valid_functions(self) -> set[str]:
        return self._valid_functions

    # --------------------------------------------------
    # Persistent store (namespaced, own namespace per hook)
    # --------------------------------------------------

    @property
    def name(self) -> str:
        """This hook's manifest name (empty on the unbound root instance)."""
        return self._name

    def _require_namespace(self) -> str:
        if not self._name or not _NAMESPACE_OK.match(self._name):
            raise ValueError(
                "Persistent store unavailable: API is not bound to a hook name."
            )
        return self._name

    def store_get(self, key: str, default: object = None) -> object:
        """Read ``key`` from this hook's persistent store (default when absent)."""
        try:
            name = self._require_namespace()
        except ValueError as exc:
            log.warning("[HOOK] store_get('%s'): %s", key, exc)
            return default
        url = f"{_API_BASE}/plugins/{name}/data/{key}"
        try:
            with urllib.request.urlopen(url, timeout=_STORE_TIMEOUT) as resp:
                return json.loads(resp.read().decode("utf-8")).get("value", default)
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                log.warning("[HOOK] store_get('%s') failed: HTTP %s", key, exc.code)
            return default
        except (OSError, ValueError) as exc:
            log.warning("[HOOK] store_get('%s') failed: %s", key, exc)
            return default

    def store_set(self, key: str, value: object) -> bool:
        """Persist ``key`` = ``value`` (any JSON-serializable data)."""
        try:
            name = self._require_namespace()
        except ValueError as exc:
            log.warning("[HOOK] store_set('%s'): %s", key, exc)
            return False
        url = f"{_API_BASE}/plugins/{name}/data/{key}"
        body = json.dumps({"value": value}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        try:
            with urllib.request.urlopen(req, timeout=_STORE_TIMEOUT):
                return True
        except (urllib.error.HTTPError, OSError, ValueError) as exc:
            log.warning("[HOOK] store_set('%s') failed: %s", key, exc)
            return False

    def store_delete(self, key: str) -> bool:
        """Delete ``key``; returns ``False`` when it did not exist."""
        try:
            name = self._require_namespace()
        except ValueError as exc:
            log.warning("[HOOK] store_delete('%s'): %s", key, exc)
            return False
        url = f"{_API_BASE}/plugins/{name}/data/{key}"
        req = urllib.request.Request(url, method="DELETE")
        try:
            with urllib.request.urlopen(req, timeout=_STORE_TIMEOUT):
                return True
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                log.warning("[HOOK] store_delete('%s') failed: HTTP %s", key, exc.code)
            return False
        except (OSError, ValueError) as exc:
            log.warning("[HOOK] store_delete('%s') failed: %s", key, exc)
            return False

    def store_all(self) -> dict:
        """Return the whole persistent store of this hook (empty dict if none)."""
        try:
            name = self._require_namespace()
        except ValueError as exc:
            log.warning("[HOOK] store_all(): %s", exc)
            return {}
        url = f"{_API_BASE}/plugins/{name}/data"
        try:
            with urllib.request.urlopen(url, timeout=_STORE_TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8")).get("data")
                return data if isinstance(data, dict) else {}
        except (OSError, ValueError) as exc:
            log.warning("[HOOK] store_all() failed: %s", exc)
            return {}

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


def clear_hook_registrations() -> int:
    """Remove all hook-registered actions and lifecycle callbacks.

    Used by the runtime hook reload before hooks are loaded again.
    Returns the number of removed actions.
    """
    removed = len(HOOK_ACTIONS)
    HOOK_ACTIONS.clear()
    HOOK_ACTION_OWNERS.clear()
    for callbacks in HOOK_LIFECYCLE.values():
        callbacks.clear()
    return removed
