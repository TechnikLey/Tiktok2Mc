# Plugin-Bundled Hooks

Hooks can be bundled with a plugin. This is useful when a plugin wants to provide `$` commands that interact with the plugin.

## Directory Structure

```
src/plugins/<plugin>/
├── plugin.json
├── main.py
├── config.yaml
└── hooks/
    └── <hook-name>/
        ├── hook.json
        ├── main.py
        └── config.yaml
```

## Hook Manifest for Plugin Bundles

Set the `plugin` field in `hook.json`:

```json
{
  "name": "spotify-control",
  "version": "1.0.0",
  "display_name": "Spotify Control",
  "plugin": "spotify",
  "min_api_version": "1.0.0",
  "config_schema": {
    "version": 1,
    "fields": []
  }
}
```

## Advantages

- **Togetherness**: Plugin and hook are installed and updated together.
- **Integration**: The hook can communicate with the plugin via the Event API.
- **Unified versioning**: Plugin and hook share the update cycle.

## Communication Between Hook and Plugin

The hook can trigger events that the plugin receives via the Event-Command-Mapper:

```python
# In the hook
api.rcon_enqueue([f"say Spotify command from {user}!"])

# The hook triggers an event that the Event-Command-Mapper
# forwards to the plugin. See [Event-Command-Mapper](./ch05-02-event-command-mapper.md) for details.
```

## Detection

The system automatically detects plugin-bundled hooks. They are searched in the `src/plugins/*/hooks/` directory and linked to the corresponding plugin.
