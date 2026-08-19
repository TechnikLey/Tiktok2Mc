# Configuration Reference

This chapter describes the most important configuration options of the system. The configuration is divided into several levels.

## Global Configuration (`config.yaml`)

The global `config/config.yaml` contains system-wide settings:

```yaml
# Address under which the bridge reaches RCON (bind address of the servers)
server_host: "127.0.0.1"

# RCON connection to the Minecraft server
rcon:
  enabled: true
  port: 25575
  password: ""

# TikTok connection
tiktok:
  user: "your_tiktok_name"

# System settings
api:
  port: 29185
```

## Plugin Configuration

Each plugin has its own `config.yaml` in its directory:

```yaml
# Plugin-specific settings here
```

The available fields are determined by the `config_schema` in the `plugin.json`.

## Hook Configuration

Each hook has its own `config.yaml` in its directory:

```yaml
# Hook-specific settings here
```

The available fields are determined by the `config_schema` in the `hook.json`.

## Event Commands (`event_commands.yaml`)

This file defines how events from the EventBus are forwarded to plugins:

```yaml
event_commands:
  # Event type:
  #   - target: Plugin name
  #     command: Command
  #     args: { ... }
  minecraft.player_death:
    - target: timer
      command: pause
  timer.zero:
    - target: win-counter
      command: add_win
      args: {amount: 1}
```

## Runtime Files

The system creates and uses the following files at runtime:

| File | Purpose |
|---|---|
| `data/api_plugin_registry.json` | Persisted plugin registry |
| `data/hook_registry.json` | Persisted hook registry |
| `data/actions.mca` | User-edited actions.mca |
| `data/event_commands.yaml` | User-edited event commands |
| `core/runtime/plugin_start_<name>` | Signal file to start a plugin |
| `core/runtime/plugin_stop_<name>` | Signal file to stop a plugin |

## gifts.json Path (Dev vs. Release)

- **Development**: `defaults/gifts.json` (source of truth in the repo)
- **Release/Installed**: `core/gifts.json` (copied by the build system)

Code reads from `core/gifts.json` first, then falls back to `defaults/gifts.json` (see `src/core/api/routes/actions.py`).
