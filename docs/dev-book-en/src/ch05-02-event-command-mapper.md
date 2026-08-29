# Event-Command-Mapper

The Event-Command-Mapper is a service that maps EventBus events to plugin commands. It enables loose coupling between components.

## Configuration

The configuration is done in the `event_commands.yaml` file:

```yaml
event_commands:
  minecraft.player_death:
    - target: timer
      command: pause
    - target: spotify-control
      command: pause
  timer.zero:
    - target: win-counter
      command: add_win
      args: {amount: 1}
```

## How It Works

1. An event is published on the EventBus (e.g., `timer.zero`).
2. The Event-Command-Mapper receives the event.
3. It looks up matching entries in the configuration.
4. For each match, it sends a command to the target plugin.

## Format

Each entry consists of:

| Field | Description |
|---|---|
| `target` | Name of the target plugin (from `plugin.json`) |
| `command` | Command to be sent to the plugin |
| `args` | Optional arguments as a dictionary |

## Plugin Development

As a plugin developer, you do not need to interact with the Event-Command-Mapper directly. You create handlers for the commands that other components send to your plugin:

```python
self.register_handler("pause", self._on_pause)
self.register_handler("add_win", self._on_add_win)
```

And you publish events that other plugins can react to:

```python
self.api_post("/events", {
    "type": "my-plugin.event",
    "data": {...}
})
```

## Advantages

- **No direct dependencies**: Plugins do not need to know each other.
- **Central configuration**: All mappings are documented in one file.
- **Flexible**: New mappings can be added without changing code.
- **Extensible**: The Event-Command-Mapper is loaded automatically on startup.
