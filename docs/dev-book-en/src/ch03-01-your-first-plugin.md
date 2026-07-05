# Your First Plugin

In this tutorial you will create a plugin that reacts to TikTok follow events and gift events.

The code from the [Quickstart](./ch01-00-getting-started.md) is extended here.

## The Complete Example

Replace `src/plugins/my-plugin/main.py`:

```python
import logging
from core.base_plugin import BasePlugin

log = logging.getLogger(__name__)

class MyPlugin(BasePlugin):
    PLUGIN_NAME = "my-plugin"

    def __init__(self):
        super().__init__()
        cfg = self.config
        self._threshold = cfg.get("threshold", 10)

        self.register_handler("tiktok_event", self._on_tiktok_event)
        self.register_handler("count", self._on_count)

        self._counter = 0
        self._state["count"] = 0

    # -- Receiving TikTok Events --

    def _on_tiktok_event(self, args):
        event_type = args.get("event_type", "")
        user = args.get("user", "")
        data = args.get("data", {})

        if event_type == "tiktok.follow":
            log.info(f"{user} is now following!")
            self._counter += 1
            self._state["count"] = self._counter
            self.push_state()

            if self._counter >= self._threshold:
                self.api_post("/events", {
                    "type": "my-plugin.milestone",
                    "data": {"count": self._counter}
                })

        elif event_type == "tiktok.gift":
            gift_name = data.get("gift_name", "unknown")
            log.info(f"{user} sent {gift_name}")

    # -- Receiving Commands from Other Plugins --

    def _on_count(self, args):
        self._counter += args.get("increment", 1)
        self._state["count"] = self._counter
        self.push_state()

    # -- Overlay --

    def get_overlay_html(self) -> str:
        ss = self.theme_style
        return f"""<!DOCTYPE html>
<html>
<head><style>
{ss}
    body {{ background: var(--background); color: var(--text); }}
    .count {{ font-size: 48px; }}
</style></head>
<body>
    <div class="count" id="counter">0</div>
    <script>
        new EventSource("/api/v1/plugins/my-plugin/stream");
        es.onmessage = (e) => {{
            const d = JSON.parse(e.data);
            document.getElementById("counter").innerText = d.count;
        }};
        es.onerror = () => {{
            es.close();
            setTimeout(() => {{ new EventSource("/api/v1/plugins/my-plugin/stream"); }}, 2000);
        }};
    </script>
</body>
</html>"""

if __name__ == "__main__":
    MyPlugin().run()
```

## How It Works

### 1. Plugin Identity

`PLUGIN_NAME = "my-plugin"` uniquely identifies the plugin. The value must match the `name` field in the `plugin.json`.

### 2. Register Handlers

`self.register_handler("tiktok_event", self._on_tiktok_event)` stores the method in an internal dictionary. When the polling thread receives a command, it looks up the matching handler and calls it.

Handler names are freely selectable. `"tiktok_event"` is a standard name used by the Event Bridge for TikTok events.

### 3. Read Configuration

```python
cfg = self.config
self._threshold = cfg.get("threshold", 10)
```

`self.config` returns a copy of the configuration from `config.yaml`.

### 4. Manage State

```python
self._state["count"] = self._counter
self.push_state()
```

`self._state` is a dictionary you can fill as you wish. `push_state()` sends the current state to the API server, which distributes it via SSE to connected browsers.

### 5. Publish Events

```python
self.api_post("/events", {
    "type": "my-plugin.milestone",
    "data": {"count": self._counter}
})
```

This is how you trigger your own event. Other plugins or the Event-Command-Mapper can react to it.

## The Lifecycle in Detail

`run()` (from `BasePlugin`) performs the following steps:

1. **Register health**: Set plugin status to `RUNNING`
2. **Register overlay**: Call `get_overlay_html()`, send HTML via `POST /plugins/{name}/overlay-html` to API
3. **Start two background threads**:
   - **Tick thread**: Calls `on_tick()` once per second. Sends a heartbeat every 30s (polling with `?wait=0`)
   - **Polling thread**: Loops `GET /plugins/{name}/commands?wait=1` (long-polling, server blocks up to 30s). On response: call matching handler from `self._handlers`
4. **Open GUI window**: If pywebview is installed and `--gui-hidden` is not set

## Event Data of TikTok Events

The Event Bridge delivers the following dictionary to the `tiktok_event` handler:

```python
{
    "event_type": "tiktok.follow",   # or tiktok.gift, tiktok.comment, ...
    "user": "TikTokUsername",        # TikTok username
    "data": {                         # Event-specific fields
        # For gift: gift_name, gift_id, count
        # For comment: comment, comment_id
        # For like: like_count
    }
}
```

The detailed structure can be found in [Receiving Events](./ch03-05-events-and-subscriptions.md).

## The Path of a TikTok Event to Your Handler

```
TikTok Live → TikTokLive Client (Bridge Process)
    → _publish_tiktok_event("follow", username)
    → EventBus.publish("tiktok.follow", {type, user})
    → _event_bridge_worker (filters by tiktok.*)
    → command_queue.enqueue(plugin, "tiktok_event", event_type, user, data)
    → API Server (CommandQueue)
    → Plugin Polling Thread (GET /commands?wait=1)
    → self._handlers["tiktok_event"](args)
```

## Next Steps

Now you know the basic lifecycle. In the next chapter you will learn about [Plugin Structure & Manifest](./ch03-02-plugin-structure.md) in detail.
