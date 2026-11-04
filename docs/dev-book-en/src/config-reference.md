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

## Chatbot Configuration (`config/chatbot.yaml`)

The TikTok chatbot has its own config file, edited via the Chatbot tab:

```yaml
enabled: false
spam_protection:
  min_interval_s: 7.0    # seconds between two messages
  max_per_minute: 8      # rate limit
  max_queue: 20          # pending messages before dropping
  dedupe_identical: true # skip duplicate consecutive messages
  max_len: 150           # max message length (chars)
replies:                 # first matching rule wins
  - on: gift             # gift | follow | join | keyword
    match: ""            # empty = any gift; otherwise gift name / keyword
    message: "Thanks {user} for {gift}!"
session:
  tt_target_idc: ""      # optional data-center hint
```

The encrypted TikTok session itself is **not** stored here — see `data/chatbot_session.json` below. Details in [TikTok Chatbot](./ch06-00-tiktok-chatbot.md).

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
| `data/chatbot_session.json` | Encrypted TikTok chatbot session (never plaintext) |
| `core/runtime/reload_chatbot` | Signal file: bridge reloads chatbot config/session |
| `core/runtime/plugin_start_<name>` | Signal file to start a plugin |
| `core/runtime/plugin_stop_<name>` | Signal file to stop a plugin |

## Gift Catalog (`gifts.json`)

The gift catalog maps gift IDs to names and powers the gift picker in the Actions editor.

- **`gifts.auto_sync`** (default `true`) — refresh the catalog at every app start.
- **`gifts.source`** (default `auto`) — `auto` tries TikTok's official gift endpoint first and falls back to the [antiops mirror](https://github.com/antiops/tiktok-trending-data); `official` or `fallback` pin a single source.

A successful sync **replaces** the runtime file `core/gifts.json` with TikTok's current list. The shipped factory template `defaults/gifts.json` is never modified and keeps serving as fallback when the runtime file is missing or unreadable; the previous runtime catalog is backed up before each overwrite. `GET /api/v1/gifts` reads `core/gifts.json` first and falls back to `defaults/gifts.json`; `POST /api/v1/gifts/sync` runs a sync on demand (used by the Actions editor's "Sync gifts" button).
