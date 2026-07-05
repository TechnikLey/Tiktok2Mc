# Core Concepts

This chapter explains the architecture and the most important components you need to know as a developer.

## System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Supervisor (start.py)                  │
│  Starts and monitors all components                      │
└─────────────────────────────────────────────────────────┘
         │                   │                   │
         ▼                   ▼                   ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│  API Server      │  │  Bridge (main.py)│  │  Minecraft      │
│  (FastAPI)       │  │  TikTok Client   │  │  Server         │
│  Port 29185      │  │  EventBus        │  │  (RCON)         │
│                  │  │  Hook Loader     │  │                 │
│  Plugin Watcher  │  │  RCON Worker     │  │                 │
│  CommandQueue    │  │  Event Bridge    │  │                 │
│  Event-Command-  │  │  Trigger Worker  │  │                 │
│  Mapper          │  │                  │  │                 │
└────────┬─────────┘  └────────┬─────────┘  └────────┬────────┘
         │                     │                      │
         │   HTTP (POST/GET)   │   asyncio.Queue      │   RCON
         ▼                     ▼                      ▼
┌──────────────────────────────────────────────────────────┐
│  Plugins (Subprocesses)                                    │
│  python src/plugins/*/main.py                             │
│  Communicate via HTTP with API Server                      │
└──────────────────────────────────────────────────────────┘
```

### Supervisor (`src/python/start.py`)

The supervisor is the lifecycle manager. It starts the API server, bridge process, Minecraft server, and GUI, monitors their health, and restarts them if necessary.

### API Server (`src/core/api/server.py`)

Central HTTP server (FastAPI) on port 29185. Provides:

- **Plugin registration and management** — `PluginWatcher` scans `src/plugins/` and registers plugins
- **CommandQueue** — Stores incoming commands per plugin (long-polling via `?wait=1`)
- **Event-Command-Mapper** — Forwards EventBus events to plugin commands
- **Overlay delivery** — HTML and SSE updates for OBS/browser
- **Plugin signals** — Signal files in `core/runtime/` control plugin start/stop

### Bridge Process (`src/python/main.py`)

The TikTok→Minecraft bridge process. Contains:

- **TikTokLive Client** — Receives live events (Gift, Follow, Like, Comment, Join, Share)
- **EventBus** — In-memory publish/subscribe (asyncio.Queue-based, max. 2000 events per queue)
- **Event-Bridge Worker** — Forwards TikTok events to plugins with matching `event_subscriptions`
- **Trigger Worker** — Processes `actions.mca` and executes actions
- **RCON Worker** — Sends Minecraft commands to the server (with retry logic)
- **Hook Loader** — Loads and initializes hooks from `src/hooks/`

## Two Paths of Event Delivery

```
TikTok-Event
    │
    ├──→ EventBus (Bridge Process)
    │       │
    │       ├──→ Event-Bridge Worker → CommandQueue → Plugin Polling
    │       │      (Filters by event_subscriptions)
    │       │
    │       ├──→ Event-Command-Mapper → CommandQueue → Plugin Polling
    │       │      (Mapping via event_commands.yaml)
    │       │
    │       └──→ Trigger Worker → execute_global_command()
    │              (Executes actions.mca: RCON, Scripts, Overlays, Shell)
    │
    └──→ TikTok-Client Callback → Trigger Queue (directly for actions.mca trigger names)
```

## Plugins vs. Hooks

| Criterion | Plugin | Hook |
|-----------|--------|------|
| Execution | Own subprocess (python .../main.py) | In bridge process (direct call) |
| Communication | HTTP (POST/GET to API server) | Function call (via HookAPI) |
| GUI | pywebview window or OBS overlay | No GUI |
| State | Own state (via `push_state()`) | No state |
| Latency | ~1s (polling interval) | Milliseconds |
| Complexity | Full class with threads | Simple function |
| Use case | Complex logic, GUI, timers | Simple `$` commands for Minecraft |

## Communication Paths

```
Plugin A ──send_command("B", "start", {})──→ API Server ──→ Plugin B (CommandQueue)
Plugin A ──api_post("/events", ...)─────────→ EventBus ──→ Event-Command-Mapper ──→ Plugin B
Plugin A ──api_post("/events", ...)─────────→ EventBus ──→ Event-Bridge ──→ Plugin B
Hook ──────api.rcon_enqueue([...])──────────→ RCON Queue ──→ Minecraft Server
Hook ──────api.enqueue_trigger("name", user)→ Trigger Queue ──→ execute_global_command()
```

## Next Chapter

From here on it gets practical. In the [next chapter](./ch03-00-plugins.md) you will develop your first complete plugin.
