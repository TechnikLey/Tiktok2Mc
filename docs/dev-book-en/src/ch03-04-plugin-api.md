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

## Communication

| Method | Description |
|---------|--------------|
| `self.send_command(target, command, args)` | Sends a command to another plugin via `POST /plugins/{target}/command`. Returns `True`/`False`. |
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
7. User disables → Signal file → Supervisor terminates process (SIGTERM)
```

> [!NOTE]
> The supervisor terminates the plugin process via `SIGTERM`. Background threads are started as `daemon=True` and are terminated automatically. For own resources (files, network connections), register `atexit` handlers:
> ```python
> import atexit
> def cleanup():
>     self._file.close()
> atexit.register(cleanup)
> ```

## REST API Endpoints (for Non-Python Plugins)

Plugins in other languages communicate directly via HTTP with the API server (`http://127.0.0.1:29185/api/v1/`):

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/plugins` | List all registered plugins |
| `POST` | `/plugins/{name}/command` | Send a command to a plugin |
| `GET` | `/plugins/{name}/commands?wait=1` | Poll for pending commands (long-polling) |
| `POST` | `/plugins/{name}/state` | Update plugin state (for SSE) |
| `GET` | `/plugins/{name}/stream` | SSE stream for state updates |
| `POST` | `/plugins/{name}/overlay-html` | Set overlay HTML |
| `GET` | `/plugins/{name}/overlay` | Retrieve overlay HTML |
| `GET` | `/plugins/{name}/config` | Read plugin configuration |
| `PUT` | `/plugins/{name}/config` | Write plugin configuration |
| `POST` | `/events` | Publish a custom event on the EventBus |
| `POST` | `/triggers/dispatch` | Fire an actions.mca trigger (no debounce — see below) |
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
