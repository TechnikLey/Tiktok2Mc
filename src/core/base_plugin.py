"""Base plugin class that eliminates boilerplate across all plugins.

Usage
-----
    from core.base_plugin import BasePlugin

    class MyPlugin(BasePlugin):
        PLUGIN_NAME = "my-plugin"

        def on_command(self, command: str, args: dict):
            if command == "start":
                self.state["running"] = True

        def on_tick(self):
            # Called once per second (override if needed)
            pass

    if __name__ == "__main__":
        MyPlugin().run()
"""

from __future__ import annotations

import atexit
import inspect
import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from core import get_base_dir, parse_args
from core.health_monitor import HealthState, get_health_monitor
from core.plugin_config import load_plugin_config
from core.theme import load_plugin_theme, theme_css

log = logging.getLogger(__name__)

# Reserved command delivered via the command queue when the API disables /
# restarts / unregisters the plugin. The BasePlugin polling loop intercepts
# it (never reaches user handlers), calls ``on_stop()`` and exits cleanly.
SHUTDOWN_COMMAND = "__shutdown__"

# Known permission names for the mandatory permission model (same
# semantics as the hook system): a plugin MUST declare every gated
# helper family it uses in ``plugin.json`` under ``"permissions"``;
# anything else is denied (logged as PLUGIN-0020, safe fallback
# returned). Note: this guards the BasePlugin API surface only; a
# plugin process can still open raw sockets/urllib itself.
PLUGIN_PERMISSIONS = ("store", "network", "plugins", "events")

# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------

_API_PORT = int(os.environ.get("RESOLVED_PORT_API_PORT", "29185"))
_API_BASE = os.environ.get("API_BASE_URL", f"http://127.0.0.1:{_API_PORT}/api/v1")
_SERVER_HOST = os.environ.get("SERVER_HOST", "127.0.0.1")


def _api_url(path: str) -> str:
    return f"{_API_BASE}/{path.lstrip('/')}"


# ---------------------------------------------------------------------------
#  BasePlugin
# ---------------------------------------------------------------------------


class _CircuitBreaker:
    """Minimal per-endpoint circuit breaker.

    After ``max_fails`` consecutive failures the breaker opens for
    ``cooldown`` seconds; calls during that window are dropped locally
    instead of hammering a dead endpoint. A successful call resets the
    failure count.
    """

    __slots__ = ("_fails", "_open_until", "cooldown", "max_fails")

    def __init__(self, max_fails: int = 5, cooldown: float = 30.0) -> None:
        self.max_fails = max(1, int(max_fails))
        self.cooldown = float(cooldown)
        self._fails = 0
        self._open_until = 0.0

    def allow(self) -> bool:
        return time.monotonic() >= self._open_until

    def mark_success(self) -> None:
        self._fails = 0
        self._open_until = 0.0

    def mark_failure(self) -> None:
        self._fails += 1
        if self._fails >= self.max_fails:
            self._open_until = time.monotonic() + self.cooldown
            self._fails = 0


class BasePlugin:
    """Abstract base for TikTok2MC plugins.

    Handles lifecycle boilerplate:
    - Config loading from ``plugin.json`` + ``config.yaml``
    - Theme loading + CSS generation
    - API client setup (``PluginAPIClient``)
    - Command polling (long-poll with ``?wait=1``)
    - State push to API
    - Window state load/save
    - Overlay HTML registration
    - pywebview window management

    Subclasses **must** define ``PLUGIN_NAME``.
    """

    PLUGIN_NAME: str = ""

    def __init__(self):
        if not self.PLUGIN_NAME:
            raise RuntimeError("PLUGIN_NAME must be set on subclass")

        self._args = parse_args()
        self._base_dir = get_base_dir()
        try:
            self._plugin_dir = Path(inspect.getfile(self.__class__)).resolve().parent
        except (TypeError, OSError):
            self._plugin_dir = Path(__file__).resolve().parent
        self._data_dir = (self._base_dir.parent / "data").resolve()
        self._data_dir.mkdir(parents=True, exist_ok=True)

        self._state_file = self._data_dir / f"window_state_{self.PLUGIN_NAME}.json"
        self._window_state = self._load_window_state()

        self._cfg = load_plugin_config(self._plugin_dir)
        self._server_host = _SERVER_HOST

        # Mandatory permissions from plugin.json ("permissions"); an empty
        # set (missing key / no declaration) denies every gated helper
        # (default deny, same semantics as hooks).
        self._permissions = self._load_permissions()

        self._theme = load_plugin_theme(self._cfg, self.PLUGIN_NAME)
        self._theme_style = theme_css(self._theme)
        self._bg_color = self._theme.get("background", "#000000")

        self._state: dict[str, Any] = {}
        self._lock = threading.Lock()
        self._running = True

        # Command dispatch table — subclasses register handlers here
        self._handlers: dict[str, Any] = {}

        # Set once the graceful shutdown sequence has started (reserved
        # ``__shutdown__`` command or interpreter exit) so on_stop() runs
        # exactly once.
        self._shutdown_started = False

        # External networking: per-URL circuit breakers and managed
        # WebSocket client threads (see http_request / ws_connect).
        self._breakers: dict[str, _CircuitBreaker] = {}
        self._ws_clients: dict[str, dict[str, Any]] = {}
        self._ws_lock = threading.Lock()

        # Register with health monitor
        try:
            hm = get_health_monitor()
            hm.register(f"plugin.{self.PLUGIN_NAME}", HealthState.STARTING)
            self._health = hm
        except Exception:  # health registration is best-effort; plugin must still start
            self._health = None

    # -- properties --------------------------------------------------------

    @property
    def state(self) -> dict[str, Any]:
        """Thread-safe access to plugin state (used by ``_push_state``)."""
        with self._lock:
            return dict(self._state)

    @state.setter
    def state(self, value: dict[str, Any]):
        with self._lock:
            self._state = dict(value)

    @property
    def config(self) -> dict[str, Any]:
        return dict(self._cfg)

    @property
    def theme_style(self) -> str:
        return self._theme_style

    @property
    def bg_color(self) -> str:
        return self._bg_color

    @property
    def gui_hidden(self) -> bool:
        return getattr(self._args, "gui_hidden", False)

    # -- window state -------------------------------------------------------

    def _load_window_state(self) -> dict[str, int]:
        if self._state_file.exists():
            try:
                with self._state_file.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                    return {
                        "width": max(data.get("width", 600), 200),
                        "height": max(data.get("height", 300), 100),
                    }
            except (json.JSONDecodeError, OSError, ValueError) as e:
                log.warning("[%s] Failed to load window state: %s", self.PLUGIN_NAME, e)
        return {"width": 600, "height": 300}

    def save_window_state(self, width: int, height: int) -> None:
        try:
            with self._state_file.open("w", encoding="utf-8") as f:
                json.dump({"width": width, "height": height}, f)
        except (OSError, TypeError) as e:
            log.warning("[%s] Failed to save window state: %s", self.PLUGIN_NAME, e)

    # -- permissions ---------------------------------------------------------

    def _load_permissions(self) -> set[str]:
        """Read ``permissions`` from the plugin manifest.

        Mandatory since v1.0.0: a missing key, an empty list or an
        unreadable manifest yields an **empty set** — every gated helper
        is then denied (default deny, same semantics as hooks). Unknown
        permission names produce a warning and are ignored.
        """
        manifest_path = self._plugin_dir / "plugin.json"
        try:
            with manifest_path.open("r", encoding="utf-8") as f:
                raw = json.load(f)
        except FileNotFoundError:
            log.warning(
                "[%s] plugin.json not found — no permissions granted (default deny)",
                self.PLUGIN_NAME,
            )
            return set()
        except (json.JSONDecodeError, OSError) as e:
            log.warning(
                "[%s] Cannot read plugin.json for permissions: %s", self.PLUGIN_NAME, e
            )
            return set()
        raw_perms = raw.get("permissions")
        if raw_perms is None:
            log.warning(
                "[%s] No 'permissions' declared in plugin.json — all gated "
                "helpers denied (default deny)",
                self.PLUGIN_NAME,
            )
            return set()
        if not isinstance(raw_perms, list):
            log.warning(
                "[%s] 'permissions' must be a list — ignoring invalid value",
                self.PLUGIN_NAME,
            )
            return set()
        perms: set[str] = set()
        for entry in raw_perms:
            if entry in PLUGIN_PERMISSIONS:
                perms.add(entry)
            else:
                log.warning(
                    "[%s] Unknown permission '%s' in plugin.json — ignored (valid: %s)",
                    self.PLUGIN_NAME,
                    entry,
                    ", ".join(PLUGIN_PERMISSIONS),
                )
        log.info(
            "[%s] Permissions declared: %s",
            self.PLUGIN_NAME,
            ", ".join(sorted(perms)),
        )
        return perms

    def _has_permission(self, permission: str) -> bool:
        """Check a gated helper against the manifest's ``permissions``.

        Default deny: undeclared families are rejected with PLUGIN-0020;
        the caller returns its safe fallback — the plugin keeps running.
        """
        if permission in self._permissions:
            return True
        log.warning(
            "[%s] %s: permission '%s' not declared in plugin.json (declared: %s)",
            self.PLUGIN_NAME,
            "PLUGIN-0020",
            permission,
            ", ".join(sorted(self._permissions)) or "<none>",
        )
        if self._health:
            self._health.record_error(
                f"plugin.{self.PLUGIN_NAME}",
                f"permission '{permission}' denied (PLUGIN-0020)",
            )
        return False

    # -- raw HTTP helpers (internal, never permission-gated) -----------------
    #
    # All of BasePlugin's own machinery (command polling, heartbeat,
    # overlay/dashboard registration, query responses) runs through these
    # ungated helpers. The public ``api_*`` wrappers below add permission
    # checks for plugin code; internals must bypass them so a restricted
    # plugin keeps its core channels working.

    def _http_get(self, path: str, timeout: int = 5) -> dict[str, Any] | None:
        """Raw GET JSON from the central API (no permission check)."""
        try:
            req = urllib.request.Request(_api_url(path))
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode())
        except (OSError, json.JSONDecodeError) as e:
            log.warning("[%s] API GET %s failed: %s", self.PLUGIN_NAME, path, e)
            return None

    def _request_json(
        self,
        path: str,
        payload: dict[str, Any] | list[Any] | None = None,
        method: str | None = None,
        timeout: float = 5,
    ) -> Any:
        """Raw request returning the parsed JSON body (no permission check)."""
        verb = method.upper() if method else ("GET" if payload is None else "POST")
        data: bytes | None = None
        headers: dict[str, str] = {}
        if payload is not None:
            try:
                data = json.dumps(payload).encode("utf-8")
            except (TypeError, ValueError) as e:
                log.warning(
                    "[%s] API %s %s: unserializable payload: %s",
                    self.PLUGIN_NAME,
                    verb,
                    path,
                    e,
                )
                return None
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(
            _api_url(path), data=data, headers=headers, method=verb
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            log.warning(
                "[%s] API %s %s failed: HTTP %s",
                self.PLUGIN_NAME,
                verb,
                path,
                exc.code,
            )
            return None
        except (OSError, ValueError) as exc:
            log.warning("[%s] API %s %s failed: %s", self.PLUGIN_NAME, verb, path, exc)
            return None

    # -- public API helpers (permission-gated: ``network``) -------------------

    def api_post(self, path: str, data: dict[str, Any]) -> bool:
        """POST JSON data to the central API. Requires ``network``."""
        if not self._has_permission("network"):
            return False
        return self._api_request("POST", path, data)

    def api_put(self, path: str, data: dict[str, Any]) -> bool:
        """PUT JSON data to the central API. Requires ``network``."""
        if not self._has_permission("network"):
            return False
        return self._api_request("PUT", path, data)

    def api_delete(self, path: str) -> bool:
        """Send a DELETE request to the central API. Requires ``network``."""
        if not self._has_permission("network"):
            return False
        return self._api_request("DELETE", path)

    def _api_request(
        self,
        method: str,
        path: str,
        data: dict[str, Any] | None = None,
    ) -> bool:
        """Raw JSON request helper returning a success flag (no permission
        check — used internally and by the gated ``api_*`` wrappers)."""
        try:
            body = json.dumps(data).encode("utf-8") if data is not None else None
            req = urllib.request.Request(
                _api_url(path),
                data=body,
                headers={"Content-Type": "application/json"}
                if body is not None
                else {},
                method=method,
            )
            urllib.request.urlopen(req, timeout=5)
            return True
        except (OSError, TypeError) as e:
            log.warning("[%s] API %s %s failed: %s", self.PLUGIN_NAME, method, path, e)
            return False

    # -- namespaced persistent store (permission-gated: ``store``) -----------

    def store_get(self, key: str, default: Any = None) -> Any:
        """Read ``key`` from this plugin's persistent store. Requires ``store``."""
        if not self._has_permission("store"):
            return default
        result = self._http_get(f"/plugins/{self.PLUGIN_NAME}/data/{key}")
        if result is None or "value" not in result:
            return default
        return result["value"]

    def store_set(self, key: str, value: Any) -> bool:
        """Persist ``key`` = ``value`` (arbitrary JSON). Requires ``store``."""
        if not self._has_permission("store"):
            return False
        return self._api_request(
            "PUT", f"/plugins/{self.PLUGIN_NAME}/data/{key}", {"value": value}
        )

    def store_delete(self, key: str) -> bool:
        """Delete ``key`` from this plugin's store. Requires ``store``."""
        if not self._has_permission("store"):
            return False
        return self._api_request("DELETE", f"/plugins/{self.PLUGIN_NAME}/data/{key}")

    def store_all(self) -> dict[str, Any]:
        """Return this plugin's whole persistent store. Requires ``store``."""
        if not self._has_permission("store"):
            return {}
        result = self._http_get(f"/plugins/{self.PLUGIN_NAME}/data")
        if not result or "data" not in result:
            return {}
        return result["data"]

    def api_get(self, path: str, timeout: int = 5) -> dict[str, Any] | None:
        """GET JSON data from the central API. Requires ``network``."""
        if not self._has_permission("network"):
            return None
        return self._http_get(path, timeout=timeout)

    def api_request(
        self,
        path: str,
        payload: dict[str, Any] | list[Any] | None = None,
        method: str | None = None,
        timeout: float = 5,
    ) -> Any:
        """Call a control-plane endpoint and return the parsed JSON body.

        Mirrors ``HookAPI.request`` for plugins: ``path`` is relative to
        the API base (``/api/v1``). With ``payload=None`` the request is a
        GET; passing a payload sends it as a JSON body via POST (override
        with ``method``, e.g. ``"PUT"``). Returns the decoded JSON value
        (dict/list/str/...), or ``None`` when the body is empty or the
        request fails — failures are logged, never raised.
        Requires the ``network`` permission.
        """
        if not self._has_permission("network"):
            return None
        return self._request_json(path, payload=payload, method=method, timeout=timeout)

    def push_state(self) -> None:
        """Push current ``self.state`` to the API state endpoint."""
        self._api_request(
            "POST", f"/plugins/{self.PLUGIN_NAME}/state", {"state": self.state}
        )

    def publish_event(
        self, event_type: str, data: dict[str, Any] | None = None
    ) -> bool:
        """Publish an event on the central EventBus. Requires ``events``.

        Event types should be namespaced under your plugin's name
        (``"<plugin-name>.<thing>"``); reserved core families
        (``tiktok.*``/``minecraft.*``) are rejected server-side with
        ``403 API-0009`` regardless of permissions. Returns ``True``
        when the event was accepted by the API.
        """
        if not isinstance(event_type, str) or not event_type.strip():
            log.warning(
                "[%s] publish_event: invalid event type %r",
                self.PLUGIN_NAME,
                event_type,
            )
            return False
        event_type = event_type.strip()
        namespace = f"{self.PLUGIN_NAME}."
        if not event_type.startswith(namespace):
            log.warning(
                "[%s] publish_event: type '%s' is outside your own "
                "namespace '%s*' — prefer namespaced types",
                self.PLUGIN_NAME,
                event_type,
                namespace,
            )
        if not self._has_permission("events"):
            return False
        return self._api_request(
            "POST", "/events", {"type": event_type, "data": data or {}}
        )

    def send_command(
        self, target_plugin: str, command: str, args: dict[str, Any] | None = None
    ) -> bool:
        """Send a command to another plugin via the API. Requires ``plugins``."""
        if not self._has_permission("plugins"):
            return False
        payload = {"command": command, "args": args or {}}
        return self._api_request("POST", f"/plugins/{target_plugin}/command", payload)

    def query_plugin(
        self,
        target_plugin: str,
        query: str,
        args: dict[str, Any] | None = None,
        timeout: float = 5,
    ) -> Any:
        """Query another plugin and return its result.

        Request/response with correlation ids: the target must
        implement ``on_query()``. Returns ``{"id": ..., "result": ...}``
        on success, or ``None`` when the target is unreachable, unknown
        or times out / reports an error.
        Requires the ``plugins`` permission.
        """
        if not self._has_permission("plugins"):
            return None
        payload = {"query": query, "args": args or {}, "timeout": timeout}
        return self._request_json(f"/plugins/{target_plugin}/query", payload=payload)

    def register_overlay(self, html: str) -> None:
        """Register overlay HTML with the central API."""
        self._api_request(
            "POST", f"/plugins/{self.PLUGIN_NAME}/overlay-html", {"html": html}
        )

    def register_dashboard(self, html: str) -> None:
        """Register dashboard page HTML with the central API.

        Only called by ``run()`` when ``get_dashboard_html()`` returns
        non-empty content (opt-in via manifest ``dashboard_ui: true``).
        """
        self._api_request(
            "POST", f"/plugins/{self.PLUGIN_NAME}/dashboard-html", {"html": html}
        )

    # -- command polling ----------------------------------------------------

    def register_handler(self, command: str, callback):
        """Register a command handler.  ``callback`` receives ``(args: dict)``."""
        self._handlers[command] = callback

    def _command_polling_loop(self):
        """Background thread: long-poll commands from the API and dispatch."""
        while self._running:
            result = self._http_get(
                f"/plugins/{self.PLUGIN_NAME}/commands?wait=1", timeout=35
            )
            if not result:
                time.sleep(0.1)
                continue
            for entry in result.get("commands", []):
                cmd = entry.get("command", "")
                args = entry.get("args", {})
                if cmd == SHUTDOWN_COMMAND:
                    # Reserved command: graceful stop — never reaches handlers
                    self._handle_shutdown_command()
                    return
                if cmd == "__query__":
                    # Reserved command: never reaches user handlers
                    self._handle_query(args)
                    continue
                if cmd == "__rpc__":
                    # Reserved command: generic custom endpoint — never
                    # reaches user handlers
                    self._handle_rpc(args)
                    continue
                handler = self._handlers.get(cmd)
                if handler:
                    try:
                        handler(args)
                    except (
                        Exception
                    ) as e:  # handler is user code — must never kill the polling loop
                        log.exception("[%s] Handler '%s' failed", self.PLUGIN_NAME, cmd)
                        if self._health:
                            self._health.record_error(
                                f"plugin.{self.PLUGIN_NAME}",
                                f"handler '{cmd}' failed: {e}",
                            )
                else:
                    # Fall through to subclass ``on_command`` override
                    self.on_command(cmd, args)

    # -- graceful shutdown ---------------------------------------------------

    def on_stop(self) -> None:
        """Called once when the plugin is shut down gracefully.

        The API delivers a reserved ``__shutdown__`` command when the
        plugin is disabled, restarted or unregistered; the polling loop
        intercepts it, calls this method and then exits the process
        cleanly. Also invoked via ``atexit`` on normal interpreter exit.
        Override to flush queues, close files/connections or persist
        final state. Exceptions are logged but never prevent the exit.
        """

    def _handle_shutdown_command(self) -> None:
        """Run the graceful shutdown sequence exactly once, then exit."""
        if self._shutdown_started:
            return
        self._shutdown_started = True
        self._running = False
        self._close_ws_clients()
        log.info("[%s] Shutdown command received — calling on_stop()", self.PLUGIN_NAME)
        try:
            self.on_stop()
        except Exception as e:  # user code — must never block the process exit
            log.exception("[%s] on_stop() failed", self.PLUGIN_NAME)
            if self._health:
                self._health.record_error(
                    f"plugin.{self.PLUGIN_NAME}", f"on_stop failed: {e}"
                )
        if self._health:
            try:
                self._health.set_state(
                    f"plugin.{self.PLUGIN_NAME}", HealthState.STOPPED
                )
            except Exception as exc:  # best-effort health reporting on the way out
                log.debug("[%s] Health state update failed: %s", self.PLUGIN_NAME, exc)
        os._exit(0)

    def _atexit_stop(self) -> None:
        """Fallback: run ``on_stop()`` on normal interpreter exit."""
        if self._shutdown_started:
            return
        self._shutdown_started = True
        self._running = False
        self._close_ws_clients()
        try:
            self.on_stop()
        except Exception:  # never raise out of an atexit handler
            log.exception(
                "[%s] on_stop() failed during interpreter exit", self.PLUGIN_NAME
            )

    # -- external networking (retry + circuit breaker) -----------------------
    #
    # Helpers for talking to third-party services from plugin code. They
    # are NOT permission-gated: a plugin process can always open sockets
    # itself, so gating would only create false security. The value here
    # is shared infrastructure — retries, backoff and a per-endpoint
    # circuit breaker that every extension gets for free.

    def http_request(
        self,
        url: str,
        method: str = "GET",
        *,
        headers: dict[str, str] | None = None,
        json_body: Any = None,
        data: bytes | None = None,
        timeout: float = 10.0,
        retries: int = 2,
        retry_backoff: float = 0.5,
    ) -> dict[str, Any] | None:
        """HTTP request to an external service with retry + circuit breaker.

        Retries connection errors and 5xx responses (exponential backoff
        starting at ``retry_backoff`` seconds); 4xx responses return
        immediately without retrying. Each URL has its own breaker: after
        5 consecutive failures it opens for 30 s and further calls to
        that URL fail fast with ``None`` instead of hammering the dead
        endpoint.

        Returns ``{"status": int, "json": parsed-or-None, "text": str}``
        for any HTTP response (check ``status`` yourself), or ``None``
        when the breaker is open or every attempt raised a network error.
        """
        verb = method.upper()
        body: bytes | None = data
        req_headers = dict(headers or {})
        if json_body is not None:
            if data is not None:
                raise ValueError("pass either json_body or data, not both")
            body = json.dumps(json_body).encode("utf-8")
            req_headers.setdefault("Content-Type", "application/json")

        breaker = self._breakers.get(url)
        if breaker is None:
            breaker = _CircuitBreaker()
            self._breakers[url] = breaker
        if not breaker.allow():
            log.warning(
                "[%s] HTTP %s %s skipped: circuit breaker open",
                self.PLUGIN_NAME,
                verb,
                url,
            )
            return None

        attempts = max(0, int(retries)) + 1
        last_error: Exception | None = None
        for attempt in range(attempts):
            req = urllib.request.Request(
                url, data=body, headers=req_headers, method=verb
            )
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    raw = resp.read()
                    text = raw.decode("utf-8", errors="replace")
                    parsed: Any = None
                    content_type = resp.headers.get("Content-Type", "")
                    if "json" in content_type or (
                        not content_type and text[:1] in ("{", "[")
                    ):
                        try:
                            parsed = json.loads(text)
                        except json.JSONDecodeError:
                            parsed = None
                    breaker.mark_success()
                    return {"status": resp.status, "json": parsed, "text": text}
            except urllib.error.HTTPError as exc:
                # 4xx = caller error, no point retrying; 5xx = server error, retry
                raw = exc.read() if hasattr(exc, "read") else b""
                text = raw.decode("utf-8", errors="replace") if raw else ""
                if exc.code < 500:
                    breaker.mark_success()  # endpoint alive, request wrong
                    return {
                        "status": exc.code,
                        "json": None,
                        "text": text,
                    }
                last_error = exc
                if attempt == attempts - 1:
                    breaker.mark_failure()
                    log.warning(
                        "[%s] HTTP %s %s failed: HTTP %s",
                        self.PLUGIN_NAME,
                        verb,
                        url,
                        exc.code,
                    )
                    return {"status": exc.code, "json": None, "text": text}
            except (OSError, ValueError) as exc:
                last_error = exc
                if attempt == attempts - 1:
                    break
            time.sleep(retry_backoff * (2**attempt))
        breaker.mark_failure()
        log.warning(
            "[%s] HTTP %s %s failed after %d attempt(s): %s",
            self.PLUGIN_NAME,
            verb,
            url,
            attempts,
            last_error,
        )
        return None

    # -- WebSocket client (background thread, auto-reconnect) -----------------

    def ws_connect(
        self,
        url: str,
        on_message: Any,
        *,
        name: str | None = None,
        headers: dict[str, str] | None = None,
        reconnect_delay: float = 5.0,
    ) -> bool:
        """Connect to a WebSocket endpoint in a managed background thread.

        Messages arrive as ``on_message(data)`` (str or bytes) in the
        client thread. The connection auto-reconnects every
        ``reconnect_delay`` seconds until :meth:`ws_close` is called or
        the plugin shuts down. Requires the optional ``websocket-client``
        package.

        Returns ``True`` when the client thread was started.
        """
        try:
            import websocket  # websocket-client
        except ImportError:
            log.error(
                "[%s] ws_connect(%s): package 'websocket-client' not "
                "installed — pip install websocket-client",
                self.PLUGIN_NAME,
                url,
            )
            return False
        if not callable(on_message):
            log.warning(
                "[%s] ws_connect: on_message must be callable", self.PLUGIN_NAME
            )
            return False
        client_name = name or url

        with self._ws_lock:
            existing = self._ws_clients.get(client_name)
            if existing and existing["thread"].is_alive():
                log.warning(
                    "[%s] WebSocket client '%s' already running",
                    self.PLUGIN_NAME,
                    client_name,
                )
                return False

            stop_event = threading.Event()

            def _runner():
                while not stop_event.is_set() and self._running:
                    try:
                        ws = websocket.create_connection(
                            url, header=headers, timeout=10
                        )
                    except Exception as e:  # connect failed — retry later
                        log.warning(
                            "[%s] WebSocket '%s' connect failed: %s",
                            self.PLUGIN_NAME,
                            client_name,
                            e,
                        )
                        stop_event.wait(reconnect_delay)
                        continue
                    log.info(
                        "[%s] WebSocket '%s' connected", self.PLUGIN_NAME, client_name
                    )
                    with self._ws_lock:
                        if client_name in self._ws_clients:
                            self._ws_clients[client_name]["ws"] = ws
                    try:
                        while not stop_event.is_set():
                            try:
                                frame = ws.recv()
                            except Exception:
                                break  # socket closed / timed out -> reconnect
                            if frame is None:
                                break
                            try:
                                on_message(frame)
                            except Exception as e:  # handler is user code
                                log.exception(
                                    "[%s] WebSocket '%s' handler failed",
                                    self.PLUGIN_NAME,
                                    client_name,
                                )
                                if self._health:
                                    self._health.record_error(
                                        f"plugin.{self.PLUGIN_NAME}",
                                        f"ws '{client_name}' handler failed: {e}",
                                    )
                    finally:
                        try:
                            ws.close()
                        except Exception as e:  # best-effort close
                            log.debug(
                                "[%s] WebSocket '%s' close failed: %s",
                                self.PLUGIN_NAME,
                                client_name,
                                e,
                            )
                    if not stop_event.is_set() and self._running:
                        log.info(
                            "[%s] WebSocket '%s' disconnected — reconnecting in %ss",
                            self.PLUGIN_NAME,
                            client_name,
                            reconnect_delay,
                        )
                        stop_event.wait(reconnect_delay)
                log.debug(
                    "[%s] WebSocket '%s' client stopped", self.PLUGIN_NAME, client_name
                )

            thread = threading.Thread(
                target=_runner,
                name=f"{self.PLUGIN_NAME}-ws-{client_name}",
                daemon=True,
            )
            self._ws_clients[client_name] = {
                "thread": thread,
                "stop": stop_event,
                "ws": None,
            }
        thread.start()
        return True

    def ws_close(self, name: str | None = None) -> None:
        """Stop a managed WebSocket client (all clients when name omitted).

        Signals the client thread and force-closes the live socket so a
        blocking ``recv()`` returns immediately.
        """
        with self._ws_lock:
            if name is None:
                clients = list(self._ws_clients.values())
                self._ws_clients.clear()
            else:
                entry = self._ws_clients.pop(name, None)
                clients = [entry] if entry else []
        for entry in clients:
            entry["stop"].set()
            sock = entry.get("ws")
            if sock is not None:
                try:
                    sock.close()
                except Exception as e:  # already closed / never connected
                    log.debug(
                        "[%s] WebSocket force-close failed: %s", self.PLUGIN_NAME, e
                    )

    def _close_ws_clients(self) -> None:
        """Stop all WebSocket clients during shutdown."""
        self.ws_close(None)

    # -- queries (request/response with correlation ids) -------------------

    def on_query(self, query: str, args: dict[str, Any]) -> Any:
        """Answer a query sent via ``POST /plugins/{name}/query``.

        Opt-in: override this and (optionally) declare the supported
        query names in ``plugin.json`` under ``"queries"`` so callers get
        fast feedback for unknown queries. The return value is JSON-
        serialized to the caller; raise an exception to report an error.
        """
        log.debug("[%s] Unhandled query: %s %s", self.PLUGIN_NAME, query, args)
        return None

    def _handle_query(self, args: dict[str, Any]) -> None:
        """Dispatch a ``__query__`` command entry and POST back the answer."""
        query_id = str(args.get("_query_id", ""))
        query = str(args.get("_query", ""))
        payload_args = {k: v for k, v in args.items() if not k.startswith("_")}
        try:
            result = self.on_query(query, payload_args)
            self._api_request(
                "POST",
                f"/plugins/{self.PLUGIN_NAME}/query-response",
                {"id": query_id, "ok": True, "result": result},
            )
        except Exception as e:  # user code — must never kill the polling loop
            log.exception("[%s] Query '%s' failed", self.PLUGIN_NAME, query)
            if self._health:
                self._health.record_error(
                    f"plugin.{self.PLUGIN_NAME}", f"query '{query}' failed: {e}"
                )
            self._api_request(
                "POST",
                f"/plugins/{self.PLUGIN_NAME}/query-response",
                {"id": query_id, "ok": False, "error": str(e)},
            )

    # -- custom endpoints (generic RPC) --------------------------------------

    def on_rpc(self, method: str, path: str, body: dict[str, Any]) -> Any:
        """Handle a call to this plugin's generic endpoint
        (``POST /api/v1/plugins/<name>/rpc``).

        Opt-in: override to give external clients and the dashboard a
        REST-style surface into this plugin without server changes.
        ``method`` is one of GET/POST/PUT/DELETE/PATCH, ``path`` starts
        with ``"/"`` and is plugin-defined (e.g. ``"/songs/42"``),
        ``body`` carries the JSON request object (empty dict for GET).
        The return value must be JSON-serializable; raise an exception
        to report an error (HTTP 502 to the caller).
        """
        log.debug("[%s] Unhandled RPC: %s %s", self.PLUGIN_NAME, method, path)
        return None

    def _handle_rpc(self, args: dict[str, Any]) -> None:
        """Dispatch an ``__rpc__`` command entry and POST back the answer."""
        rpc_id = str(args.get("_rpc_id", ""))
        method = str(args.get("_rpc_method", "GET"))
        path = str(args.get("_rpc_path", "/"))
        body = {k: v for k, v in args.items() if not k.startswith("_")}
        try:
            result = self.on_rpc(method, path, body)
            self._api_request(
                "POST",
                f"/plugins/{self.PLUGIN_NAME}/query-response",
                {"id": rpc_id, "ok": True, "result": result},
            )
        except Exception as e:  # user code — must never kill the polling loop
            log.exception("[%s] RPC %s %s failed", self.PLUGIN_NAME, method, path)
            if self._health:
                self._health.record_error(
                    f"plugin.{self.PLUGIN_NAME}",
                    f"rpc {method} {path} failed: {e}",
                )
            self._api_request(
                "POST",
                f"/plugins/{self.PLUGIN_NAME}/query-response",
                {"id": rpc_id, "ok": False, "error": str(e)},
            )

    # -- tick loop ----------------------------------------------------------

    _HEARTBEAT_INTERVAL = 30  # seconds between heartbeat pings

    def _tick_loop(self):
        """Background thread: calls ``on_tick`` once per second.

        Also sends a heartbeat ping to the API every
        ``_HEARTBEAT_INTERVAL`` seconds so the health monitor does not
        mark an idle plugin as unhealthy.
        """
        heartbeat_counter = 0
        while self._running:
            try:
                self.on_tick()
            except (
                Exception
            ) as e:  # on_tick is user code — must never kill the tick loop
                log.exception("[%s] Tick failed", self.PLUGIN_NAME)
                if self._health:
                    self._health.record_error(
                        f"plugin.{self.PLUGIN_NAME}", f"on_tick failed: {e}"
                    )
            heartbeat_counter += 1
            if heartbeat_counter >= self._HEARTBEAT_INTERVAL:
                heartbeat_counter = 0
                try:
                    self._http_get(
                        f"/plugins/{self.PLUGIN_NAME}/commands?wait=0",
                        timeout=5,
                    )
                except (OSError, json.JSONDecodeError):
                    pass
                # Report heartbeat to health monitor
                if self._health:
                    self._health.record_heartbeat(f"plugin.{self.PLUGIN_NAME}")
            time.sleep(1)

    # -- subclass hooks -----------------------------------------------------

    def on_command(self, command: str, args: dict[str, Any]) -> None:
        """Called when an unhandled command arrives.

        Subclasses should override this or use ``register_handler()``.
        """
        log.debug("[%s] Unhandled command: %s %s", self.PLUGIN_NAME, command, args)

    def on_tick(self) -> None:
        """Called once per second in the background tick thread.

        Subclasses should override for periodic work (e.g. timer countdown).
        """

    def get_overlay_html(self) -> str:
        """Return the HTML string for the overlay.

        Subclasses **must** override this.
        """
        raise NotImplementedError("Subclasses must implement get_overlay_html()")

    def get_dashboard_html(self) -> str:
        """Return the HTML string for the plugin's dashboard tab.

        Opt-in: return a full HTML page and declare ``"dashboard_ui": true``
        in ``plugin.json``.  The page is served at
        ``/api/v1/plugins/{name}/dashboard`` (same origin as the API, so
        relative ``/api/v1/...`` calls work — state SSE, commands, store)
        and embedded as a tab in the web dashboard.  Default: no page.
        """
        return ""

    # -- window / run -------------------------------------------------------

    def _start_threads(self):
        self._running = True
        tick_thread = threading.Thread(target=self._tick_loop, daemon=True)
        tick_thread.start()

        poll_thread = threading.Thread(target=self._command_polling_loop, daemon=True)
        poll_thread.start()

        return tick_thread, poll_thread

    def run(self) -> None:
        """Main entry point: register overlay, start threads, open window."""
        # Graceful-shutdown fallback: if the process exits normally (window
        # closed, gui_hidden tick thread ended) on_stop() still runs once.
        atexit.register(self._atexit_stop)

        if self._health:
            self._health.set_state(f"plugin.{self.PLUGIN_NAME}", HealthState.RUNNING)
            self._health.record_heartbeat(f"plugin.{self.PLUGIN_NAME}")

        html = self.get_overlay_html()
        self.register_overlay(html)

        dashboard_html = self.get_dashboard_html()
        if dashboard_html:
            self.register_dashboard(dashboard_html)

        tick_thread, _poll_thread = self._start_threads()

        if not self.gui_hidden:
            try:
                import webview

                window = webview.create_window(
                    self.PLUGIN_NAME,
                    f"http://{_SERVER_HOST}:{_API_PORT}/api/v1/plugins/{self.PLUGIN_NAME}/overlay",
                    width=self._window_state["width"],
                    height=self._window_state["height"],
                    on_top=True,
                    background_color=self._bg_color,
                )
                webview.start()
            except ImportError:
                log.error(
                    "[%s] pywebview not installed — cannot open GUI window",
                    self.PLUGIN_NAME,
                )
        else:
            log.info(
                "[%s] Running in gui_hidden mode. Open "
                "http://%s:%d/api/v1/plugins/%s/overlay in OBS as a Browser Source.",
                self.PLUGIN_NAME,
                _SERVER_HOST,
                _API_PORT,
                self.PLUGIN_NAME,
            )
            tick_thread.join()
