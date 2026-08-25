# Plugin API Reference

All public methods of `BasePlugin` available to you during development.

## Base Class

```python
from core.base_plugin import BasePlugin

class MyPlugin(BasePlugin):
    PLUGIN_NAME = "my-plugin"
```

## Required Attributes and Methods

### `PLUGIN_NAME: str`

Must match exactly the `name` field in the `plugin.json`. Used for API endpoints, the CommandQueue, and the Plugin Registry.

### `get_overlay_html() -> str`

Must be overridden. Returns the HTML string for the overlay. Called once by `run()` on startup. For plugins without an overlay, a minimal return is sufficient: `return "<html><body></body></html>"` or `return ""`.

### `get_dashboard_html() -> str`

Optional. Returns a full HTML page that the web dashboard embeds as a tab. Only registered when it returns non-empty content — declare `"dashboard_ui": true` in `plugin.json` so the tab appears. See [Dashboard Pages](#dashboard-pages).

## Configuration

| Method | Description |
|---------|--------------|
| `self.config` | Returns a **copy** of the config dict. Read-only. |

## State Management

| Method | Description |
|---------|--------------|
| `self.state` | Thread-safe access to the plugin state (dictionary). Returns a copy. |
| `self.state = {...}` | Replaces the entire state (thread-safe). |
| `self.push_state()` | Sends the current state via `POST /plugins/{name}/state` to the API server → SSE → browser. |

**Thread Safety**: `self.state` (property) is thread-safe and should be used for read and write access from parallel threads. Direct access to `self._state["key"] = val` is atomic under CPython for individual assignments, but not for compound operations:

```python
# Recommended: thread-safe via the property
state = self.state
state["count"] = self._counter
self.state = state
self.push_state()

# Also OK (single assignment, atomic under GIL):
self._state["count"] = self._counter
self.push_state()  # reads via thread-safe self.state
```

> **Rule of thumb**: Use `self.state =` for compound operations (e.g., increment, updating multiple fields at once). `self._state[key] = val` is only safe for single, atomic assignments.

## Overlay

| Method | Description |
|---------|--------------|
| `self.register_overlay(html)` | Replaces the overlay HTML at runtime via `POST /plugins/{name}/overlay-html`. |
| `self.theme_style` | Returns the plugin theme's CSS variables as a string. Which variables exist depends on the `theme:` section of the plugin configuration (e.g. `--background`, `--text`, `--accent`). |
| `self.gui_hidden` | `True` if `--gui-hidden` is set. |

## Dashboard Pages

Plugins can provide their own page inside the web dashboard (a tab in the
sidebar next to the fixed views). This is opt-in:

1. Declare `"dashboard_ui": true` in `plugin.json`.
2. Override `get_dashboard_html()` and return a full HTML document.

`run()` then registers the page automatically (or at runtime via
`self.register_dashboard(html)`). The dashboard embeds it as an iframe under
`/api/v1/plugins/{name}/dashboard`; the tab only appears while the plugin is
enabled.

Because the page shares the origin with the API, it can use relative
`/api/v1/...` calls — the same building blocks as overlays:

- `EventSource("/api/v1/plugins/{name}/stream")` for live state (`push_state()`)
- `POST /api/v1/plugins/{name}/command` to trigger your own command handlers
- `GET/PUT /api/v1/plugins/{name}/data[/{key}]` for the persistent store

#### Dashboard pages follow the GUI theme

The web dashboard loads plugin pages with a `?theme=dark|light` query
parameter and refreshes already-open tabs when the user toggles light/dark
mode. Your page should read the parameter and set CSS variables accordingly,
so the tab stays readable in both modes (the plugin's overlay colors from the
`theme:` config section are meant for the **overlay window**, not the tab):

```html
<head>
  <script>
    (function () {
      var t = new URLSearchParams(location.search).get('theme');
      if (!t && window.matchMedia) {
        t = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
      }
      document.documentElement.setAttribute('data-theme', t || 'dark');
    })();
  </script>
  <style>
    /* self.theme_style first, then GUI-theme overrides */
    :root { --background: #f6f7f9; --text: #1b1e23; --accent: #4c8dff; }
    [data-theme="dark"] { --background: #15171c; --text: #e8eaed; --accent: #5a8dff; }
  </style>
</head>
```

Without the parameter (e.g. when opened in a new tab), fall back to
`prefers-color-scheme` as shown above.

```python
class MyPlugin(BasePlugin):
    PLUGIN_NAME = "my-plugin"

    def get_dashboard_html(self) -> str:
        return """<!DOCTYPE html>
<html><body>
  <div id="out">...</div>
  <script>
    const es = new EventSource("/api/v1/plugins/my-plugin/stream");
    es.onmessage = (e) => { out.textContent = JSON.parse(e.data).value; };
  </script>
</body></html>"""
```

## Communication

| Method | Description |
|---------|--------------|
| `self.send_command(target, command, args)` | Sends a command to another plugin via `POST /plugins/{target}/command`. Returns `True`/`False`. |
| `self.query_plugin(target, query, args=None, timeout=5)` | Sends a query to another plugin and returns the parsed response (`{"id": ..., "result": ...}`), or `None` on timeout/error. See [Querying Plugins](#querying-plugins-requestresponse). |
| `self.api_post(path, data)` | Sends HTTP POST to `http://127.0.0.1:29185/api/v1/{path}`. Returns `True`/`False`. |
| `self.api_get(path, timeout=5)` | Sends HTTP GET. Returns the JSON object or `None` on errors. |
| `self.api_request(path, payload=None, method=None, timeout=5)` | Full request/response: returns the **parsed JSON body** (`dict`/`list`/str/...), or `None` on empty body/errors. With `payload=None` it sends a GET; passing a payload sends JSON via POST (override with `method="PUT"` etc.). Never raises. |

> [!NOTE]
> The API base URL can be overridden via the environment variable `API_BASE_URL` (e.g., for different host/port configuration). Default: `http://127.0.0.1:29185/api/v1`.

```python
# Send command to timer plugin
self.send_command("timer", "pause", {})

# Publish your own event
self.api_post("/events", {
    "type": "my-plugin.reached",
    "data": {"count": 42}
})

# Query plugin list
plugins = self.api_get("/plugins")

# Request/response with body access (PUT + parsed response)
result = self.api_request(
    "plugins/my-plugin/data/counter",
    payload={"value": 42},
    method="PUT",
)
```

## Command Handlers

```python
self.register_handler("command_name", callback)
```

Signature of the callback: `callback(args: dict) -> None`

Fallback for unregistered commands:

```python
def on_command(self, command, args):
    """Called when no matching handler exists."""
    log.warning(f"Unknown command: {command}")
```

## Permissions (mandatory)

Like hooks, plugins declare which capabilities of the plugin API they use.
Add a `permissions` list to your `plugin.json`:

```json
{
  "name": "my-plugin",
  "permissions": ["store", "events"]
}
```

| Permission | Grants |
|------------|--------|
| `store` | `store_get`, `store_set`, `store_delete`, `store_all` |
| `network` | Generic control-plane HTTP: `api_get`, `api_post`, `api_put`, `api_delete`, `api_request` |
| `plugins` | Cross-plugin communication: `send_command`, `query_plugin` |
| `events` | `publish_event(type, data)` — publish on the EventBus |

> [!IMPORTANT]
> **Default deny (breaking since v1.0.0):** every gated helper whose family
> is not declared is rejected with its safe fallback (`False`/`None`/`{}`/
> default) and logged as `PLUGIN-0020`; the plugin keeps running. Declare
> exactly what you use.

Not gated (always available — these are the plugin's own core channels):
command polling and handlers, heartbeat, `push_state`,
`register_overlay`, `register_dashboard`, `on_stop`.

Notes:

- Unknown permission names are ignored with a warning at startup.
- Permissions guard the **BasePlugin API surface only** — a plugin process is
  full Python and can still open raw sockets itself. For hard isolation use
  [sandbox profiles](./ch03-02-plugin-structure.md#sandbox-profiles).
- Prefer `publish_event` over raw `api_post("/events", ...)` — it only needs
  the `events` permission and validates your namespace (`"<plugin-name>.<thing>"`;
  reserved core families `tiktok.*`/`minecraft.*` are rejected server-side
  with `403 API-0009`).

## External Networking (retry + circuit breaker)

For talking to third-party services (Discord bots, game servers, external
APIs) plugins get shared infrastructure instead of building their own:

### `http_request(url, method="GET", *, headers=None, json_body=None, data=None, timeout=10.0, retries=2, retry_backoff=0.5)`

```python
resp = self.http_request(
    "https://api.example.test/v1/things",
    method="POST",
    json_body={"name": "x"},
)
if resp is None:
    ...  # network exhausted or breaker open — handle offline case
elif resp["status"] >= 400:
    ...
else:
    payload = resp["json"]  # parsed automatically when response is JSON
```

- Retries connection errors and `5xx` with exponential backoff; `4xx`
  returns immediately (caller error).
- Per-URL circuit breaker: after 5 consecutive failures the URL is skipped
  locally for 30 s (`None` return instead of hammering a dead endpoint);
  any success resets it.
- Returns `{"status", "json", "text"}` for HTTP responses, `None` when the
  request could not be completed.

### `ws_connect(url, on_message, *, name=None, headers=None, reconnect_delay=5.0)` / `ws_close()`

Managed WebSocket client threads with auto-reconnect (requires the bundled
`websocket-client` package):

```python
def start(self):  # e.g. from __init__ or a command handler
    self.ws_connect(
        "wss://game.example.test/feed",
        self.on_game_message,
        name="game",
    )

def on_game_message(self, data):
    # data is str (or bytes); runs in the client thread
    event = json.loads(data)
    ...

def on_stop(self):
    self.ws_close()  # all clients; ws_close("game") for one
```

- Auto-reconnects every `reconnect_delay` seconds until closed or the
  plugin shuts down (all clients are stopped automatically on shutdown).
- Handler exceptions are isolated and reported to the health monitor.
- Duplicate `name` while running → returns `False`.

> [!NOTE]
> These helpers are **not** permission-gated: a plugin process can always
> open raw sockets itself, so gating would only add friction without real
> security. The value is shared retry/breaker/reconnect infrastructure.

## Lifecycle

### `run()`

Called once, does not return (blocks until plugin termination). Executes:

1. Set plugin status to `RUNNING` in `HealthMonitor`
2. Retrieve `get_overlay_html()` and send to API
3. Start tick thread (`on_tick()` once per second)
4. Start polling thread (long-polling `?wait=1`)
5. Open pywebview window (optional)

### `on_tick()`

Called once per second by the tick thread. Override it for periodic tasks (e.g., timer countdown). The attribute `self._running` is predefined by `BasePlugin`; additional attributes must be initialized in `__init__`:

```python
def __init__(self):
    super().__init__()
    self._remaining = 60  # Initialization before on_tick()

def on_tick(self):
    if self._running and self._remaining > 0:
        self._remaining -= 1
        self.push_state()
```

**Threading Note**: `on_tick()` runs in the tick thread. Handlers run in the polling thread. `self._state` (direct access) and `self.state` (property) are safe under CPython for individual assignments (GIL guarantees atomic dict operations).

### `on_stop()`

Called exactly once when the plugin is shut down gracefully — i.e., when it
is disabled, restarted or unregistered via the dashboard/API (the API
delivers a reserved internal command to the plugin before the process is
stopped), and as an `atexit` fallback on normal interpreter exit.
Override it to flush queues, close files/connections or persist final state:

```python
def __init__(self):
    super().__init__()
    self._events: list[dict] = []

def on_stop(self):
    self.flush_pending_events()
    self.push_state()
```

- Exceptions in `on_stop()` are logged but never prevent the exit.
- The reserved shutdown command never reaches your command handlers.
- A hard kill (e.g., frozen process) cannot run `on_stop()` — keep critical
  state persisted continuously via the persistent store (`store_set`) rather
  than only at shutdown.

## Directories

| Property | Type | Description |
|-------------|-----|--------------|
| `self._data_dir` | `Path` | Global data directory: `<project>/data/`. **All plugins share this directory** — use plugin-specific filenames. |
| `self._plugin_dir` | `Path` | Plugin's own directory (next to main.py). Contains config.yaml and plugin.json. |

```python
# Save persistent counter (plugin-specific filename!)
count_file = self._data_dir / f"{self.PLUGIN_NAME}_count.json"

# Config-own files
theme_file = self._plugin_dir / "theme.json"
```

## Additional Properties

| Property | Description |
|-------------|--------------|
| `self.bg_color` | Background color from the theme (string) |
| `self.save_window_state(w, h)` | Saves window size for next start |

## Typical Plugin Lifecycle

```
1. System starts → PluginWatcher scans plugin.json
2. API Server registers plugin in Registry
3. User enables → Signal file → Supervisor starts subprocess
4. python main.py → if __name__ → MyPlugin().run()
5. run() registers overlay, starts threads
6. Polling thread receives commands → Handler is called
7. User disables → API delivers shutdown command → on_stop() runs
   → process exits cleanly (hard stop signal only if still alive)
```

> [!NOTE]
> Disable/restart/unregister deliver a reserved shutdown command to the
> plugin first and wait briefly (~1 s grace) before writing the hard stop
> signal — so `on_stop()` can flush state. Background threads are started
> as `daemon=True`; you do not need your own `atexit` handlers anymore —
> override `on_stop()` instead (see above).

## REST API Endpoints (for Non-Python Plugins)

Plugins in other languages communicate directly via HTTP with the API server (`http://127.0.0.1:29185/api/v1/`):

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/plugins` | List all registered plugins (includes each plugin's `queries` field) |
| `GET` | `/plugins/queries` | Query discovery: all declared query names per plugin |
| `POST` | `/plugins/{name}/command` | Send a command to a plugin |
| `POST` | `/plugins/{name}/query` | Query a plugin (request/response — see below) |
| `POST` | `/plugins/{name}/query-response` | Plugin-internal: deliver a query answer |
| `POST` | `/plugins/{name}/rpc` | Call the plugin's generic custom endpoint (`on_rpc()`) — see below |
| `GET` | `/plugins/{name}/commands?wait=1` | Poll for pending commands (long-polling) |
| `POST` | `/plugins/{name}/state` | Update plugin state (for SSE) |
| `GET` | `/plugins/{name}/stream` | SSE stream for state updates |
| `POST` | `/plugins/{name}/overlay-html` | Set overlay HTML |
| `GET` | `/plugins/{name}/overlay` | Retrieve overlay HTML |
| `POST` | `/plugins/{name}/dashboard-html` | Set dashboard page HTML (manifest: `dashboard_ui`) |
| `GET` | `/plugins/{name}/dashboard` | Retrieve dashboard page HTML |
| `GET` | `/rcon/status` | RCON connection status (read-only) |
| `POST` | `/rcon/command` | Execute a Minecraft command directly (`{"command": "..."}`) — see below |
| `GET` | `/plugins/{name}/config` | Read plugin configuration |
| `PUT` | `/plugins/{name}/config` | Write plugin configuration |
| `POST` | `/events` | Publish a custom event on the EventBus |
| `POST` | `/triggers/dispatch` | Fire an actions.mca trigger (no debounce — see below) |
| `POST` | `/events/ingest` | Publish a namespaced event and optionally fire a trigger in one call (see below) |
| `GET` | `/plugins/{name}/data` | Read the plugin's whole persistent store |
| `GET` | `/plugins/{name}/data/{key}` | Read one key from the plugin's store |
| `PUT` | `/plugins/{name}/data/{key}` | Write one key (body: `{"value": <any JSON>}`) |
| `DELETE` | `/plugins/{name}/data/{key}` | Delete one key from the plugin's store |
| `GET` | `/outbound/channels` | Outbound channels with status/counters (URLs masked) |
| `POST` | `/outbound/channels/{name}/test` | Send a test message through one channel |
| `GET` | `/health` | API server health status |
| `GET` | `/diagnostics` | Full diagnostic report |

**Authentication**: If `api_key` is set in the global `config.yaml`, every request must include the `X-API-Key: <key>` header (only applies to requests from outside localhost).

**Base URL**: Default `http://127.0.0.1:29185/api/v1/`, overridable via the `API_BASE_URL` environment variable.

### Direct RCON Access

`POST /api/v1/rcon/command` with body `{"command": "say hello"}` executes a
Minecraft command **directly** from the API process and returns the server's
response (`{"response": "..."}`). This is the same endpoint the dashboard
Console view uses.

> [!WARNING]
> Unlike `!`-lines in `actions.mca`, this path **bypasses the bridge's RCON
> queue, throttling and retries**. Use it for interactive queries and rare
> administrative actions — not for high-frequency trigger commands. It is
> **disabled by default** (`rcon.http_command_api: false` in `config.yaml`,
> security/stability default); set it to `true` to enable it — the dashboard
> Console tab requires this. When disabled, requests are rejected with
> `403 MC-0012` while the queue path keeps working.

### Querying Plugins (Request/Response)

Plugins can expose **server-side queries** — request/response with
correlation ids, e.g. a leaderboard answering `"top"`. This is the
supported way to read structured data *from* a plugin process (the
dashboard and other extensions call it like any REST endpoint):

1. Override `on_query(query, args) -> Any` in your plugin class. The
   return value is JSON-serialized to the caller; raise an exception to
   report an error.
2. Optionally declare the supported query names in `plugin.json` under
   `"queries": ["top", "stats"]` — callers then get an instant 404 for
   unknown queries instead of waiting for the timeout.

Callers use `POST /plugins/{name}/query` with body
`{"query": "top", "args": {}, "timeout": 5}` (timeout clamped to
0.5–30 s). The query is delivered to the plugin through its command
queue as the reserved command `__query__` with a correlation id; the
BasePlugin polling loop routes it to `on_query()` automatically and
POSTs the answer back. Python plugins simply call
`self.query_plugin(target, query, args)`.

Responses: `200 {"id": ..., "result": ...}` on success; `504 PLUGIN-0018`
if the plugin doesn't answer in time; `502 PLUGIN-0019` if the handler
raised. Commands (`!`-lines, reactions) remain fire-and-forget — queries
are for reads that need a result.

#### Query Discovery

Because queries are an intentional contract between two plugins, the API
exposes what exists: `GET /plugins/queries` scans every `plugin.json` and
returns all declared query names together with the plugin's enabled state:

```json
{
  "total": 1,
  "plugins": [
    { "name": "deathcounter", "queries": ["deaths"], "enabled": true }
  ]
}
```

Plugins without a `queries` declaration are omitted (their queries would
404 at call time anyway). The same information is available per plugin via
the `queries` field of `GET /plugins`. Calling an undeclared query fails
fast with a 404 whose detail lists the plugin's declared queries — so a
typo tells you immediately what *is* available.

Reference implementation: the shipped **death-counter** plugin answers
the `"deaths"` query.

```python
class MyPlugin(BasePlugin):
    PLUGIN_NAME = "leaderboard"

    def on_query(self, query: str, args: dict):
        if query == "top":
            scores = self.store_get("scores", {})
            top = sorted(scores.items(), key=lambda kv: -kv[1])[:10]
            return [{"user": u, "points": p} for u, p in top]
        return None
```

### Custom Endpoints (`on_rpc()` — generic RPC)

When the `commands`/`queries` schemas are not enough, every plugin gets a
REST-style surface without any server changes:

```python
def on_rpc(self, method: str, path: str, body: dict) -> Any:
    """Called for POST /api/v1/plugins/<name>/rpc calls."""
    if method == "POST" and path == "/songs":
        song = create_song(body)
        return {"id": song.id}
    if method == "GET" and path.startswith("/songs/"):
        return lookup_song(path.rsplit("/", 1)[1])
    raise ValueError(f"no route: {method} {path}")
```

Call it from dashboards, external tools or other plugins:

```json
POST /api/v1/plugins/spotify/rpc
{
  "method": "POST",
  "path": "/queue/play",
  "body": {"uri": "spotify:track:..."},
  "timeout": 5
}
```

- **Response**: `{"id": ..., "result": ...}` on success; `504 PLUGIN-0018`
  on timeout; `502 PLUGIN-0019` when `on_rpc()` raised.
- Delivery uses the same reserved-command channel as queries
  (`__rpc__`, correlation id via the query store) and reuses the
  query-response endpoint for the answer.
- `method` is GET/POST/PUT/DELETE/PATCH, `path` must start with `/` and is
  plugin-defined, `body` is an optional JSON object (empty for GET).
- Return value must be JSON-serializable; raising reports an error to the
  caller without killing the polling loop.

### Persistent Store (namespaced)

Every plugin gets its own JSON file under `data/plugin_data/<name>.json` —
you never need to touch the shared `data/` directory yourself, and you cannot
collide with other plugins. Keys are flat strings (`[A-Za-z0-9_.-]`, max 128
chars), values are arbitrary JSON and survive restarts.

Python plugins use the built-in helpers on `BasePlugin`:

```python
class MyPlugin(BasePlugin):
    PLUGIN_NAME = "leaderboard"

    def on_command(self, command, args):
        if command == "add_point":
            scores = self.store_get("scores", {})
            user = args.get("user", "?")
            scores[user] = scores.get(user, 0) + 1
            self.store_set("scores", scores)

        elif command == "reset":
            self.store_delete("scores")
```

Non-Python extensions use plain HTTP:

```json
PUT /api/v1/plugins/leaderboard/data/scores.user-1
{"value": {"points": 10}}
```

> [!TIP]
> Prefer many small keys over one giant blob if you update frequently — each
> write rewrites the namespace's whole JSON file atomically.

### Firing Trigger Actions Programmatically

`POST /api/v1/triggers/dispatch` executes an `actions.mca` trigger exactly as if
the corresponding TikTok event had occurred — without the cooldown of the GUI
Event Tester (`/triggers/execute`). This is the supported way for extensions to
drive actions.mca on their own schedule (timers, cron, external integrations):

```json
POST /api/v1/triggers/dispatch
{
  "trigger": "bonus_drop",
  "user": "System",
  "gift_id": null,
  "gift_name": null
}
```

- **trigger**: Action name from `actions.mca`, a gift ID, or one of the built-in
  event names (`follow`, `like`, `join`, `share`, `comment`, `gift`)
- **user**: Username passed as `{user}` (default `"System"`)
- **gift_id / gift_name**: Optional; for gift triggers (`gift_id` replaces the
  trigger name on the wire)
- **Response**: `{"status": "success", "trigger": ..., "user": ..., "message": ...}`
  — `status` is `"error"` for validation failures or an unreachable bridge
- The call is **not** rate-limited and is **not** marked as a test event;
  every dispatch is recorded in the trigger history (`GET /triggers/history`)

### Generic Event Ingest (Bus + Trigger in One Call)

`POST /api/v1/events/ingest` is the structured inbound for extensions and
external systems (games, OBS bots, Home Assistant, automation). It publishes
a namespaced event on the EventBus — reaching plugins via
`event_subscriptions`, hooks via `register_event`, the outbound dispatcher
and the GUI live feed — and optionally fires an `actions.mca` trigger chain
in the same call:

```json
POST /api/v1/events/ingest
{
  "type": "mygame.player_death",
  "data": {"player": "Notch", "level": 42},
  "trigger": "on_death",
  "user": "Notch"
}
```

| Field | Required | Meaning |
|-------|----------|---------|
| `type` | yes | Namespaced event type `<source>.<event>` (e.g. `mygame.player_death`) |
| `data` | no | Free-form payload dict (default `{}`) |
| `trigger` | no | `actions.mca` action name to dispatch as well |
| `user` / `gift_id` / `gift_name` | no | Payload for the optional trigger; falls back to the matching `data` keys |

- **Response**: `{"status": "ok", "event": ..., "trigger": {...}}` — the
  `trigger` key only appears when a trigger was dispatched and carries the
  same shape as `/triggers/dispatch`.
- Reserved core families (`tiktok.*`, `minecraft.*`) are rejected (`403`,
  `API-0009`) — publish under your own namespace.
- Use this endpoint instead of the minecraft-branded bridge webhook when
  integrating your own game: no queue-pause side effects, no naming
  collisions, full control over the event name.

### Outbound Webhooks

The API process can forward live events to external HTTP endpoints
("outbound channels", e.g. Discord webhooks). Channels are configured in the
global `config.yaml` under `outbound.channels`; each channel subscribes via
event patterns (`tiktok.gift`, `tiktok.*`, `*`) with the same matching rules
as plugin `event_subscriptions`:

```yaml
outbound:
  enabled: true          # master switch for all channels
  max_fails: 3           # circuit breaker: failures before cooldown
  cooldown: 10           # circuit breaker: pause in seconds
  retries: 1             # extra delivery attempts per message
  timeout: 5             # HTTP timeout in seconds
  channels:
    - name: "discord-events"
      url: "https://discord.com/api/webhooks/..."
      events: ["tiktok.*"]
      format: discord    # discord | raw
      template: "**{user}** triggered *{type}*"
      enabled: true
```

Two payload formats are supported:

- **raw**: JSON envelope `{"type": "...", "data": {...}, "timestamp": ...}`
- **discord**: Discord webhook payload `{"content": "<template>"}` — templates
  support `{user}`, `{type}` and any event data placeholder (`{comment}`,
  `{gift_id}`, ...); unknown placeholders become empty strings

Every channel has its own circuit breaker (same mechanism as overlays): after
`max_fails` consecutive failed deliveries the channel pauses for `cooldown`
seconds and drops incoming events instead of sending. Failed deliveries are
retried `retries` times (1 s apart). Status and per-channel counters are
exposed via `GET /api/v1/outbound/channels` (URLs are masked), and a manual
connectivity probe is available via
`POST /api/v1/outbound/channels/{name}/test` — the probe ignores event
patterns and does not touch the circuit breaker or counters.

### Notifications

The notification dispatcher is the unified way to surface user-facing
messages (status updates, warnings, results) without caring *where* they
appear. Senders pass **their own channel settings inline** — no global
configuration required. Plugins use the `BasePlugin` API helpers:

```python
result = self.api_request("notifications", payload={
    "title": "Backup done",
    "channels": {
        "overlay": {"duration": 4},                    # OBS overlay text
        "sound":   {"file": "data/sounds/alert.wav"},  # .wav (Windows)
        "tts":     {"rate": 0},                        # Windows SAPI speech
        "discord": {"webhook_url": "https://discord.com/api/webhooks/..."},
    },
})  # -> {"sent": [...], "failed": [...], "skipped": [...]}
```

For pure fire-and-forget, `self.api_post("notifications", {...})` also works
and returns a success flag instead of the body.

Built-in channels: `log` (always available), `overlay`, `sound`,
`tts`, `discord`. Additional channel handlers can be registered in
`core/api/notification_dispatcher.py` (`CHANNEL_HANDLERS`) — making this an
exchangeable-channel system rather than a fixed list. Every request carries
its own parameters, so different actions can target **different webhooks,
sounds or overlays** within the same session; each call is independent.
(Optionally, a `notifications:` section in the global `config.yaml` can
provide default params for callers that only name a channel — plugins never
rely on it.)

Omitting `channels` delivers to the optionally globally configured channels
(or `log` when none are); naming unknown channels logs `NOTIF-0002` and
reports them as `skipped`. A channel that fails during delivery (missing
file, webhook error, ...) is reported as `failed` with `NOTIF-0001` in the
API log — delivery problems never raise and don't change the HTTP status;
you only see them in the response (`failed`/`skipped`).

#### Recommended pattern: self-contained plugin settings

Expose every delivery setting (webhook URL, sound file, overlay duration,
...) through your plugin's own `config_schema`, pass it inline as shown
above, and mention it in your plugin README ("configure it in the plugin
settings") — end users then never touch YAML or the global config.

REST endpoints: `POST /api/v1/notifications` (send), 
`GET /api/v1/notifications/channels` (enabled state + built-in/configured
channels), `POST /api/v1/notifications/reload` (re-read the optional global
config section after edits).

## Next Chapter

Learn how to [Receive Events](./ch03-05-events-and-subscriptions.md) — both from TikTok and via the Event-Command-Mapper.
