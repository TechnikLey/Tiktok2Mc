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

Must be overridden. Returns the HTML string for the overlay. Called once by `run()` on startup.

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

## Overlay

| Method | Description |
|---------|--------------|
| `self.register_overlay(html)` | Replaces the overlay HTML at runtime via `POST /plugins/{name}/overlay-html`. |
| `self.theme_style` | Returns CSS variables (`--background`, `--text`, `--accent`, `--muted`, `--danger`, `--separator`) as a string. |
| `self.gui_hidden` | `True` if `--gui-hidden` is set or pywebview is not installed. |

## Communication

| Method | Description |
|---------|--------------|
| `self.send_command(target, command, args)` | Sends a command to another plugin via `POST /plugins/{target}/command`. Returns `True`/`False`. |
| `self.api_post(path, data)` | Sends HTTP POST to `http://127.0.0.1:29185/api/v1/{path}`. Returns `True`/`False`. |
| `self.api_get(path, timeout=5)` | Sends HTTP GET. Returns the JSON object or `None` on errors. |

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
> The supervisor terminates the plugin process via `SIGTERM`. Background threads are started as `daemon=True` and are terminated automatically. For own resources (files, network connections), `atexit` handlers can be registered.

## Next Chapter

Learn how to [Receive Events](./ch03-05-events-and-subscriptions.md) — both from TikTok and via the Event-Command-Mapper.
