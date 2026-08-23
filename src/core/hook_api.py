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

# Lifecycle callbacks per event ("live_start" / "live_end" / "unload"):
# {event: {hook_name: callable}}
HOOK_LIFECYCLE: dict[str, dict[str, Callable]] = {
    "live_start": {},
    "live_end": {},
    "unload": {},
}

LIFECYCLE_EVENTS = tuple(HOOK_LIFECYCLE)

# Bus-event subscriptions: pattern -> {hook_name: callback}.
# Patterns follow the plugin ``event_subscriptions`` semantics: exact type
# ("tiktok.gift"), trailing prefix wildcard ("tiktok.*") or the catch-all "*".
# Callbacks are called as ``fn(event_type, data)`` from the bridge's
# background executor — never on the trigger/TikTok threads.
HOOK_EVENT_SUBSCRIPTIONS: dict[str, dict[str, Callable]] = {}

# Registered timers per hook: hook_name -> [timer_entry, ...] where each
# entry is ``{"interval": float, "fn": callable, "next": float}`` and
# ``next`` is a ``time.monotonic()`` deadline managed by the bridge's timer
# scheduler (see core.hook_loader). Hooks cannot import ``threading``
# (import whitelist), so periodic work goes through this API instead.
HOOK_TIMERS: dict[str, list[dict]] = {}

MIN_TIMER_INTERVAL: float = 0.1

MAX_CHAIN_DEPTH: int = 3

# Canonical permissions enforced on per-hook API views (see ``for_hook``).
# ``capabilities`` in hook.json are discovery/advertising tags; these
# ``permissions`` are what a hook may actually call.
HOOK_PERMISSIONS: frozenset[str] = frozenset(
    {
        "rcon",  # rcon_enqueue
        "triggers",  # enqueue_trigger
        "overlay",  # send_overlay_text
        "store",  # store_get / store_set / store_delete / store_all
        "network",  # request (control-plane HTTP helper)
        "events",  # publish_event (custom events on the API EventBus)
    }
)

_API_PORT = int(os.environ.get("RESOLVED_PORT_API_PORT", "29185"))
_API_BASE = os.environ.get("API_BASE_URL", f"http://127.0.0.1:{_API_PORT}/api/v1")

_STORE_TIMEOUT = 5
_NAMESPACE_OK = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class HookContext(dict):
    """Structured event context passed to hook actions.

    A plain ``dict`` subclass: all values stay accessible via ``.get()`` /
    ``in`` / iteration / ``json.dumps``. On top, required keys can be read
    as attributes — ``context.gift_name`` instead of
    ``context["gift_name"]``. Attribute access fails fast with an
    ``AttributeError`` on unknown keys (typo protection), while optional
    keys should be read via ``.get(key, default)`` as usual.
    """

    def __getattr__(self, key: str) -> object:
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key) from None


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
        # ``None`` = unrestricted (root instance / tests); a bound view
        # carries the exact grants from its hook manifest.
        self._permissions: frozenset[str] | None = None

    # --------------------------------------------------
    # Public API
    # --------------------------------------------------

    def for_hook(self, name: str, permissions: list[str] | None = None) -> HookAPI:
        """Return a per-hook view of this shared API bound to *name*.

        Used by the loader so each hook's ``register()`` gets an API whose
        persistent-store helpers target the hook's own namespace.  All other
        methods share the same queues/config references as the root instance.

        ``permissions`` carries the grants from the hook's manifest. When a
        list is given, guarded API calls (``rcon_enqueue``, ``enqueue_trigger``,
        ``send_overlay_text``, ``store_*``) are denied unless the required
        permission is included; unknown permission names are warned about.
        Passing ``None`` keeps the view unrestricted (bridge-internal use).
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
        if permissions is not None:
            granted = frozenset(permissions)
            unknown = sorted(granted - HOOK_PERMISSIONS)
            if unknown:
                log.warning(
                    "[HOOK] '%s' declares unknown permission(s): %s (supported: %s)",
                    name,
                    ", ".join(unknown),
                    ", ".join(sorted(HOOK_PERMISSIONS)),
                )
            clone._permissions = granted
        return clone

    def _allow(self, permission: str, method: str) -> bool:
        """Check a guarded call against this view's grants.

        Unrestricted views (``_permissions is None``) always pass. Denied
        calls are logged as HOOK-0009 and rejected with a safe return value.
        """
        if self._permissions is None or permission in self._permissions:
            return True
        log.warning(
            "[HOOK-0009] '%s' denied %s — missing permission '%s' in hook.json",
            self._name or "<unbound>",
            method,
            permission,
        )
        return False

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
        """Register a lifecycle callback.

        Supported events: ``"live_start"`` (TikTok connection established),
        ``"live_end"`` (live stream ended) and ``"unload"`` (this hook is
        being unloaded before a runtime reload or shutdown — release
        resources here). Unknown events are rejected.
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

    def on_unload(self, fn: Callable) -> None:
        """Register a dispose callback run when this hook is unloaded.

        Called with no arguments before the hook's registrations are
        cleared (runtime reload or bridge shutdown). Use it to close
        files/connections or flush in-memory state — there is no other
        teardown signal for hooks.
        """
        self.register_lifecycle("unload", fn)

    def register_timer(self, interval: float, fn: Callable) -> bool:
        """Run ``fn()`` periodically every *interval* seconds.

        The callback takes no arguments and runs on the bridge's shared
        timer scheduler thread (never on the trigger/TikTok threads).
        Exceptions are isolated and reported as HOOK-0010; the timer
        keeps running. Intervals below ``MIN_TIMER_INTERVAL`` (0.1 s)
        are clamped. Returns ``True`` when the timer was registered,
        ``False`` on invalid input. Timers are removed automatically on
        unload/reload of the hook.
        """
        if not callable(fn):
            log.warning(
                "[HOOK] register_timer(%s): not callable (hook '%s')",
                interval,
                self._name or "<unbound>",
            )
            return False
        try:
            interval_f = float(interval)
        except (TypeError, ValueError):
            log.warning("[HOOK] register_timer: invalid interval %r", interval)
            return False
        if interval_f < MIN_TIMER_INTERVAL:
            log.warning(
                "[HOOK] register_timer: interval %s below minimum %ss — clamped",
                interval_f,
                MIN_TIMER_INTERVAL,
            )
            interval_f = MIN_TIMER_INTERVAL
        import time as _time

        HOOK_TIMERS.setdefault(self._name or "<unbound>", []).append(
            {
                "interval": interval_f,
                "fn": fn,
                "next": _time.monotonic() + interval_f,
            }
        )
        log.info(
            "[HOOK] Registered timer (%ss) for '%s'",
            interval_f,
            self._name or "<unbound>",
        )
        return True

    def register_event(self, event_pattern: str, fn: Callable) -> None:
        """Subscribe this hook to bus events matching *event_pattern*.

        Patterns follow the plugin ``event_subscriptions`` semantics:
        exact type (``"tiktok.gift"``), trailing prefix wildcard
        (``"tiktok.*"``, ``"minecraft.*"``) or the catch-all ``"*"``.
        The callback is called as ``fn(event_type, data)`` from the
        bridge's background executor. Last registration wins per hook
        and pattern; re-register after a runtime reload.
        """
        if not isinstance(event_pattern, str) or not event_pattern.strip():
            log.warning("[HOOK] register_event: invalid pattern %r", event_pattern)
            return
        if not callable(fn):
            log.warning("[HOOK] register_event(%r): not callable", event_pattern)
            return
        HOOK_EVENT_SUBSCRIPTIONS.setdefault(event_pattern.strip(), {})[
            self._name or "<unbound>"
        ] = fn
        log.info(
            "[HOOK] Registered event subscription: %s (hook '%s')",
            event_pattern.strip(),
            self._name or "<unbound>",
        )

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
        if not self._allow("rcon", "rcon_enqueue"):
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
        if not self._allow("triggers", "enqueue_trigger"):
            return
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
        ctx_data = HookContext(context) if isinstance(context, dict) else HookContext()
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
        if not self._allow("overlay", "send_overlay_text"):
            return False
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

    def _store_allowed(self, method: str) -> bool:
        if not self._allow("store", method):
            return False
        try:
            self._require_namespace()
            return True
        except ValueError as exc:
            log.warning("[HOOK] %s: %s", method, exc)
            return False

    def store_get(self, key: str, default: object = None) -> object:
        """Read ``key`` from this hook's persistent store (default when absent)."""
        if not self._store_allowed("store_get"):
            return default
        name = self._name
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
        if not self._store_allowed("store_set"):
            return False
        name = self._name
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
        if not self._store_allowed("store_delete"):
            return False
        name = self._name
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
        if not self._store_allowed("store_all"):
            return {}
        name = self._name
        url = f"{_API_BASE}/plugins/{name}/data"
        try:
            with urllib.request.urlopen(url, timeout=_STORE_TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8")).get("data")
                return data if isinstance(data, dict) else {}
        except (OSError, ValueError) as exc:
            log.warning("[HOOK] store_all() failed: %s", exc)
            return {}

    def publish_event(self, event_type: str, data: dict | None = None) -> bool:
        """Publish a custom event on the API EventBus.

        The event type **must** be namespaced under the hook's own name
        (``"<hook-name>.<thing>"``) so hooks cannot spoof core event
        types like ``tiktok.gift``; other types are rejected with a
        warning. Requires the ``events`` permission in hook.json. The
        POST is best-effort — returns ``True`` when delivered.
        """
        if not self._allow("events", "publish_event"):
            return False
        if not isinstance(event_type, str) or not event_type.strip():
            log.warning("[HOOK] publish_event: invalid type %r", event_type)
            return False
        clean = event_type.strip()
        prefix = f"{self._name}." if self._name else ""
        if prefix and not clean.startswith(prefix):
            log.warning(
                "[HOOK] publish_event('%s') rejected — hook events must be "
                "namespaced under '%s*' to avoid spoofing core event types",
                clean,
                prefix,
            )
            return False
        body = json.dumps({"type": clean, "data": data or {}}).encode("utf-8")
        req = urllib.request.Request(
            f"{_API_BASE}/events",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=_STORE_TIMEOUT):
                return True
        except (urllib.error.HTTPError, OSError, ValueError) as exc:
            log.warning("[HOOK] publish_event('%s') failed: %s", clean, exc)
            return False

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

    # --------------------------------------------------
    # Control-plane requests (request/response)
    # --------------------------------------------------

    def request(
        self,
        path: str,
        payload: dict | list | None = None,
        method: str | None = None,
        timeout: float = _STORE_TIMEOUT,
    ) -> object | None:
        """Call a control-plane API endpoint and return the parsed JSON body.

        ``path`` is relative to the API base (``/api/v1``), e.g.
        ``"plugins/some-plugin/state"``. With ``payload=None`` the request is a
        GET; passing a payload sends it as a JSON body via POST (override
        with ``method``, e.g. ``"PUT"``). Returns the decoded JSON value
        (dict/list/str/...), or ``None`` when the body is empty or the
        request fails — failures are logged, never raised.

        Requires the ``network`` permission in hook.json. Note that this is
        an ergonomic gate on the HookAPI surface only: hooks may still use
        raw ``urllib``/``requests`` directly (see sandbox notes in the dev
        book).
        """
        if not self._allow("network", "request"):
            return None
        if not isinstance(path, str) or not path.strip():
            log.warning("[HOOK] request: invalid path %r", path)
            return None
        clean = path.strip().lstrip("/")
        verb = method.upper() if method else ("GET" if payload is None else "POST")
        data = None
        headers: dict[str, str] = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(
            f"{_API_BASE}/{clean}", data=data, headers=headers, method=verb
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            log.warning("[HOOK] request %s %s failed: HTTP %s", verb, clean, exc.code)
            return None
        except (OSError, ValueError) as exc:
            log.warning("[HOOK] request %s %s failed: %s", verb, clean, exc)
            return None


def clear_hook_registrations() -> int:
    """Remove all hook-registered actions, lifecycle callbacks, event
    subscriptions and timers.

    Used by the runtime hook reload before hooks are loaded again.
    Returns the number of removed actions.
    """
    removed = len(HOOK_ACTIONS)
    HOOK_ACTIONS.clear()
    HOOK_ACTION_OWNERS.clear()
    for callbacks in HOOK_LIFECYCLE.values():
        callbacks.clear()
    HOOK_EVENT_SUBSCRIPTIONS.clear()
    HOOK_TIMERS.clear()
    return removed
