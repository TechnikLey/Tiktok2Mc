# Receiving Events

Events are the central communication path. This chapter shows how your plugin receives TikTok events and how the Event-Command-Mapper enables loose coupling.

## Two Paths to Your Plugin

| Path | Source | Setup | Handler Name |
|-----|--------|-------------|--------------|
| **Event Bridge** | TikTok events (Gift, Follow, Like, Comment, Join, Share) | `event_subscriptions` in `plugin.json` | `"tiktok_event"` |
| **Event-Command-Mapper** | All EventBus events (TikTok, Plugins, System) | `event_commands.yaml` | Any, defined in the YAML |

**Why two paths?** The Event Bridge is the quick start for TikTok — plugins receive TikTok events without additional setup by setting `event_subscriptions`. The Event-Command-Mapper (ECM) is the flexible tool for loose coupling: one event can trigger multiple plugins, and plugins don't need to know about each other. In practice, a TikTok plugin usually uses the Bridge; the ECM connects plugins together (e.g., Timer → WinCounter).

## Path 1: Event Bridge (TikTok Events)

### Declare Subscription

In the `plugin.json`:

```json
{
  "event_subscriptions": ["tiktok.gift", "tiktok.follow"]
}
```

Wildcard `"tiktok.*"` subscribes to all TikTok events. The Event Bridge only delivers TikTok events, so subscriptions use the `tiktok.` namespace (either exact types like `"tiktok.follow"` or the prefix wildcard `"tiktok.*"`). Events from other plugins or the system are **not** delivered via `event_subscriptions` — use the [Event-Command-Mapper](./ch05-02-event-command-mapper.md) (`event_commands.yaml`) for those. Your own published events use the namespace `plugin-name.event`.

### Register Handler

```python
class MyPlugin(BasePlugin):
    def __init__(self):
        super().__init__()
        self.register_handler("tiktok_event", self._on_event)

    def _on_event(self, args):
        event_type = args.get("event_type", "")
        user = args.get("user", "")
        data = args.get("data", {})
```

### Event Data Structure

The Event Bridge delivers standardized dictionaries:

```python
# tiktok.gift
{
    "event_type": "tiktok.gift",
    "user": "fan123",
    "data": {
        "gift_name": "Rose",
        "gift_id": "5655",
        "count": 1
    }
}

# tiktok.follow
{
    "event_type": "tiktok.follow",
    "user": "new_fan",
    "data": {}
}

# tiktok.comment
{
    "event_type": "tiktok.comment",
    "user": "commenter",
    "data": {}
}

# tiktok.like
{
    "event_type": "tiktok.like",
    "user": "fan",
    "data": {
        "delta": 12,   # Likes since session start (events throttled to ~1/3 s)
        "total": 162   # Total likes for the session
    }
}

# tiktok.join / tiktok.share
{
    "event_type": "tiktok.join",
    "user": "visitor",
    "data": {}
}
```

> [!NOTE]
> The comment text is **not** part of the `tiktok.comment` event (`data` is empty). Comment texts are delivered via the [Comment Handler](#comment-handler-comment_handler) (see below).

> [!NOTE]
> The Event Bridge publishes TikTok events on the EventBus, filters them in the bridge process (`_event_bridge_worker`), and enqueues the command `"tiktok_event"` in the CommandQueue of the API server.

### Complete Example: Reacting to Multiple Event Types

```python
class ReactionPlugin(BasePlugin):
    def __init__(self):
        super().__init__()
        self.register_handler("tiktok_event", self._on_event)

    def _on_event(self, args):
        etype = args["event_type"]
        user = args["user"]

        if etype == "tiktok.gift":
            gname = args.get("data", {}).get("gift_name", "?")
            log.info(f"{user} sent {gname}")

        elif etype == "tiktok.follow":
            log.info(f"New follower: {user}")

        elif etype == "tiktok.comment":
            log.info(f"Comment from {user}")
```

## Path 2: Event-Command-Mapper

The Event-Command-Mapper (ECM) runs as a background task in the API server. It subscribes to **all** EventBus events and forwards them to plugin commands based on the `data/event_commands.yaml`.

### Configuration

```yaml
# data/event_commands.yaml
event_commands:
  timer.zero:
    - target: win-counter
      command: add_win
      args: {amount: 1}
  minecraft.player_death:
    - target: timer
      command: pause
```

When the `timer.zero` event arrives, the ECM sends the command `add_win` with the arguments to the plugin `win-counter`.

### In Plugin Code

```python
# Publish event (triggers ECM)
self.api_post("/events", {
    "type": "timer.zero",
    "data": {}
})

# React to ECM commands
self.register_handler("add_win", self._on_add_win)

def _on_add_win(self, args):
    amount = args.get("amount", 1)
    self._wins += amount
```

### Advantages

- **No coupling**: The timer plugin does not need to know about `win-counter`
- **Central configuration**: All mappings in one YAML file
- **Flexible**: One event can trigger multiple commands to multiple plugins
- **Changeable at runtime**: The file is re-read on each request

## Publishing Your Own Events

```python
self.api_post("/events", {
    "type": "my-plugin.reached",
    "data": {"value": 42}
})
```

Naming convention: `plugin-name.event` (namespace with dot).

## Delivery Guarantees

| Aspect | Guarantee |
|--------|----------|
| Order | Events of the same type are processed in order of arrival |
| Delivery | At-Most-Once after processing by the handler. On network errors, an event may be re-requested. |
| Timeout | Polling timeout: 30s server-side, 35s client-side |

## Comment Handler (`comment_handler`)

Plugins can react to TikTok comments with a specific prefix. The declaration is made in the `plugin.json`:

```json
{
  "comment_handler": {
    "prefix": "$",
    "enabled": true
  }
}
```

| Field | Description |
|------|--------------|
| `prefix` | Character that marks a command (e.g., `$` for `$song`). Default: `"$"`. |
| `enabled` | Whether the handler is active. Default: `true`. |

When a TikTok comment starts with the prefix (e.g., `$song`), the system forwards the command text **without the prefix** to the plugin via `POST /plugins/{name}/command`. The plugin registers a handler for the `"comment"` command for this:

```python
self.register_handler("comment", self._on_comment)

def _on_comment(self, args):
    text = args.get("text", "")          # e.g. "song"
    username = args.get("username", "")  # e.g. "fan123"
```

> [!NOTE]
> Without the `comment_handler` declaration, the prefix is not registered and the system does not forward the comment to the plugin. The `tiktok.comment` event only contains the username and an empty `data` — the comment text arrives exclusively through this command.

## Common Errors

| Problem | Cause | Solution |
|---------|---------|--------|
| Events not arriving | `event_subscriptions` missing | Add in `plugin.json` |
| Handler not called | Handler name incorrect | Check `register_handler("tiktok_event", ...)` |
| ECM not responding | `event_commands.yaml` missing/erroneous | Check YAML syntax |
| Duplicate processing | No idempotency in handler | Check state before action |

## Next Chapter

In the next chapter you will learn about [Cross-Plugin Communication](./ch03-06-cross-plugin-communication.md).
