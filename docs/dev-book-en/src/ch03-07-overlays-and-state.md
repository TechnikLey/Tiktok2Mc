# Overlays & State

Plugins can provide overlay content for OBS or the pywebview window. There are two levels: static HTML and dynamic state updates via SSE.

## How Overlays Work

```
Plugin Process           API Server                    Browser / OBS
     │                        │                                │
     │── POST /overlay-html ─→│                                │
     │                        │── GET /plugins/{name}/overlay →│
     │                        │    (static HTML)               │
     │                        │                                │
     │── POST /state ───────→ │                                │
     │                        │── SSE: data: {...} ──────────→ │
     │                        │    (EventSource Stream)        │
```

## Static Overlay HTML

Every plugin **must** override `get_overlay_html()`. The HTML is loaded once on startup and served via the API server.

```python
def get_overlay_html(self) -> str:
    return """<!DOCTYPE html>
<html>
<head>
    <style>
        body { margin: 0; background: transparent; }
        .count { font-size: 48px; color: #ff4444; }
    </style>
</head>
<body>
    <div class="count" id="counter">0</div>
    <script>
        const es = new EventSource("/api/v1/plugins/my-plugin/stream");
        es.onmessage = (e) => {
            const data = JSON.parse(e.data);
            document.getElementById("counter").innerText = data.count;
        };
        es.onerror = () => {
            es.close();
            setTimeout(() => {
                window.location.reload();
            }, 2000);
        };
    </script>
</body>
</html>"""
```

**Overlay URL**: `http://127.0.0.1:29185/api/v1/plugins/<name>/overlay`

Use this URL as a **Browser Source** in OBS.

## Dynamic State via SSE

### Set and Transfer State

```python
self._state["count"] = self._counter
self.push_state()
```

`push_state()` sends `POST /api/v1/plugins/{name}/state` to the API server. The server stores the state in the `PluginStateStore` and forwards it via SSE (`GET /api/v1/plugins/{name}/stream` — the SSE endpoint) to all connected clients.

### SSE Code in HTML

```javascript
const es = new EventSource("/api/v1/plugins/my-plugin/stream");
es.onmessage = (e) => {
    const data = JSON.parse(e.data);
    document.getElementById("counter").innerText = data.count;
};
es.onerror = () => {
    es.close();
    setTimeout(() => {
        new EventSource("/api/v1/plugins/my-plugin/stream");
    }, 2000);
};
```

### When to Call push_state()?

- After every state change that should be visible in the overlay
- In `on_tick()` for periodic changes (timer countdown)
- Not for every single change — collect and call once

## Replacing `get_overlay_html()` at Runtime

If the HTML itself needs to change (e.g., theme switch):

```python
self.register_overlay("<html>New HTML</html>")
```

For frequent content changes, `push_state()` is the right approach.

## Saving State Across Restarts

`push_state()` is volatile — the state only lives in the API server. For persistent data:

```python
class MyPlugin(BasePlugin):
    def __init__(self):
        super().__init__()
        count_file = self._data_dir / f"{self.PLUGIN_NAME}_state.json"
        self._data = self._load(count_file)

    def _load(self, path):
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return {}

    def _save(self, path):
        path.write_text(json.dumps(self._data), encoding="utf-8")
```

> [!WARNING]
> `self._data_dir` is **the same for all plugins** (`<project>/data/`). Always use plugin-specific filenames.

## Theme Support

```python
def get_overlay_html(self) -> str:
    return f"""<!DOCTYPE html>
<html>
<head>
    <style>
{self.theme_style}
        body {{ background: var(--background); color: var(--text); }}
    </style>
</head>
<body>...</body>
</html>"""
```

Available CSS variables: `--background`, `--text`, `--accent`, `--muted`, `--danger`, `--separator`

## GUI Window with pywebview

The base class opens a pywebview window pointing to the overlay URL. Use `--gui-hidden` to suppress the window:

```bash
python src/plugins/my-plugin/main.py --gui-hidden
```

Save window dimensions:

```python
self.save_window_state(width, height)
```

## Common Errors

| Problem | Cause | Solution |
|---------|---------|--------|
| Overlay stays black | `get_overlay_html()` missing | Implement it |
| No real-time updates | `push_state()` missing | Call after each change |
| SSE disconnects | No `onerror` handler | Add `setTimeout` reconnection |
| Theme not working | `{self.theme_style}` not included | Insert in `<style>` |
