# Cross-Plugin Communication

Plugins can communicate with each other in two ways: directly via `send_command` or loosely coupled via the EventBus.

## Direct Commands: `send_command()`

```python
self.send_command("timer", "pause", {})
self.send_command("win-counter", "add_win", {"amount": 1})
```

The target plugin must have a matching handler registered:

```python
class TimerPlugin(BasePlugin):
    def __init__(self):
        super().__init__()
        self.register_handler("pause", self._on_pause)
        self.register_handler("start", self._on_start)

    def _on_pause(self, args):
        self._running = False
```

Internally, `send_command` calls the API: `POST /api/v1/plugins/timer/command` with body `{"command": "pause", "args": {}}`. The API server places the command into the CommandQueue of the target plugin.

**Advantage**: Simple, direct, synchronous.
**Disadvantage**: Creates dependency — Plugin A must know Plugin B.

## Event-Based Communication: EventBus + ECM

The recommended approach for loose coupling:

```python
# Plugin A publishes an event
self.api_post("/events", {
    "type": "timer.zero",
    "data": {}
})
```

In `data/event_commands.yaml`, what happens is defined:

```yaml
event_commands:
  timer.zero:
    - target: win-counter
      command: add_win
      args: {amount: 1}
```

**Advantages**: Zero coupling, central configuration, easily extensible.

## Workflow Example: TikTok Gift → Timer → Win-Counter

```
tiktok.gift → Event-Command-Mapper → Timer (start, 60s)
    → Timer expires → timer.zero is published
    → Event-Command-Mapper → Win-Counter (add_win)
```

Configuration in `event_commands.yaml`:

```yaml
event_commands:
  tiktok.gift:
    - target: timer
      command: start
      args: {duration: 60}
  timer.zero:
    - target: win-counter
      command: add_win
      args: {amount: 1}
```

No plugin contains hardcoded references to other plugins.

## Communication Between Plugins and Hooks

Hooks can trigger events that plugins receive. To do this, the hook uses `api.enqueue_trigger()` or indirectly the Event-Command-Mapper. Plugins cannot call hooks directly — hooks are only intended for `$` commands in `actions.mca`.

## Summary

| Situation | Mechanism |
|-----------|-------------|
| One plugin must directly control another | `send_command()` |
| An event should trigger multiple plugins | EventBus + ECM |
| The connection should be configurable | EventBus + ECM |
| Loose coupling desired | EventBus + ECM |

## Next Chapter

Learn about [Overlays & State](./ch03-07-overlays-and-state.md) for real-time updates in the browser or OBS.
