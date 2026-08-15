# TikTok2Mc — Architecture Overview

This document describes the current architecture of TikTok2Mc as of v1.0.0. It is intended as a central reference for developers and contributors.

---

## High-Level Components

```
┌─────────────────────────────────────────────────────────────────────┐
│                        SUPERVISOR (start.py)                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌───────────┐  │
│  │ API Server  │  │   Bridge    │  │    GUI      │  │ Plugins/  │  │
│  │ (FastAPI)   │  │  (main.py)  │  │ (pywebview) │  │  Hooks    │  │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └─────┬─────┘  │
│         │                │                │                │        │
│         └────────────────┼────────────────┼────────────────┘        │
│                          ▼                ▼                         │
│                   ┌─────────────────────────────────┐               │
│                   │         EventBus (in-process)   │               │
│                   └─────────────────────────────────┘               │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 1. Supervisor (`src/python/start.py`)

The entry point that runs the **FastAPI control plane** in-process and spawns supervised subprocesses:

| Process | Source | Purpose |
|---------|--------|---------|
| API Server | `src/core/api/server.py` | REST API, plugin/hook management, health, updater |
| Bridge | `src/python/main.py` | TikTokLive client → event queues → RCON/datapack/overlay/shell/hook |
| GUI | `src/python/gui.py` | pywebview desktop app (loads Dashboard from `templates/gui/`) |
| Plugins | `src/plugins/*/main.py` | Subprocesses, long-poll `/api/v1/plugins/{name}/commands?wait=1` |
| Hooks | `src/hooks/*/main.py` | In-process, `register(api: HookAPI)` |
| Overlay | `src/python/overlay.py` | Standalone overlay renderer (optional) |
| Updater | `src/python/update.py` | Self-update binary |

Supervision is handled by `CrashManager` (`src/core/crash_manager.py`) using `asyncio` tasks with `observe_task` / `supervised_async_task`.

---

## 2. EventBus (`src/core/api/eventbus.py`)

In-process publish/subscribe bus (module-level singleton). Used for:

- Bridge → API: `POST /api/v1/events` (TikTok events, plugin state)
- API → GUI: SSE endpoint `/api/v1/ws` (real-time dashboard updates)
- Internal: overlay state, plugin health, crash notifications

Key topics: `tiktok.*`, `plugin.{name}.state_update`, `overlay.state_update`, `health.*`, `log.*`.

---

## 3. TriggerEngine (`src/core/trigger_engine/`)

**Single source of truth** for trigger execution and validation.

- `models.py` — `TriggerType` enum, `TriggerDefinition`, `EngineConfig`, `ExecutionResult`
- `engine.py` — `TriggerEngine.execute_trigger()`, `execute_comment()`, payload building, validation, bridge HTTP POST
- `validator.py` — `.mca` syntax validation (shared with language server)
- `dispatcher.py` — action dispatch (`/`, `!`, `$`, `>>`, `&`, `@name>>`, `;`, `xN`)

Used by: `send_trigger.py` (CLI), Bridge webhook, Hook `$` actions, Event-Command-Mapper.

---

## 4. Bridge (`src/python/main.py`)

The **most sensitive file** — handles TikTokLive events, queues, retries.

### Flow

```
TikTokLive Client (thread) → on_gift/on_follow/... → _publish_tiktok_event()
    → EventBus.publish("tiktok.{type}", data)
    → enqueue_threadsafe(ctx.trigger_queue, item)
    → trigger_worker() (asyncio loop)
        → execute_global_command()
            → TriggerEngine → POST /webhook (port 29188) → RCON / Datapack / Overlay / Shell / Hook
```

### Key Queues

- `ctx.trigger_queue` — trigger execution (bounded, drops logged)
- `ctx.rcon_queue` — RCON commands (bounded, retries)
- `ctx.webhook_queue` — outgoing webhook calls

### Webhook Server (Flask, port 29188)

Endpoints: `/webhook` (trigger intake), `/health`, `/metrics`, `/test_comment`, `/custom_trigger`.

---

## 5. API Server (`src/core/api/`)

FastAPI app factory in `server.py`. Routes under `/api/v1` (see `routes/__init__.py`).

### Route Groups

| Prefix | Module | Purpose |
|--------|--------|---------|
| `/health`, `/status`, `/health/extended` | `health.py` | Health checks, bridge metrics |
| `/diagnostics/*` | `diagnostics.py` | Full reports, error codes, crash history |
| `/config` | `config.py` | Read/write `config.yaml` (ruamel.yaml, preserves comments) |
| `/actions` | `actions.py` | Read/write `actions.mca`, gift picker |
| `/events` | `events.py` | `POST` TikTok events from Bridge |
| `/ws` | `ws.py` | SSE for GUI real-time updates |
| `/plugins`, `/plugins/{name}/*` | `plugins.py`, `plugin_overlay.py` | Plugin lifecycle, commands, state, overlays |
| `/hooks` | `hooks.py` | Hook enable/disable, registry |
| `/overlay` | `overlay.py` | Core overlay HTML, SSE, preview, display |
| `/backups` | `backups.py` | List/create/restore config backups |
| `/reactions` | `reactions.py` | Event Reactions editor |
| `/event_commands` | `event_commands.py` | Event-Command Mapper |
| `/servers`, `/server_lifecycle` | `servers.py`, `server_lifecycle.py` | Server Manager (PaperMC instances) |
| `/updates` | `updater.py` | Version check, update status |
| `/rcon` | `rcon.py` | RCON test/send |
| `/triggers` | `triggers.py` | Trigger definitions, test execution |
| `/versions` | `versions.py` | PaperMC version list |

### Services (`src/core/api/services/`)

| Service | Purpose |
|---------|---------|
| `ApiService` | Config read/write, uptime, plugin registry |
| `TriggerService` | TriggerEngine wrapper for API |
| `BridgeMetricsService` | Fetch metrics from Bridge `/metrics` |
| `BackupService` | Config/action/plugin backup & restore |
| `ReactionCatalogService` | Event-Reaction catalog |
| `RconService` | RCON connection pool |
| `PluginDiscovery` | Scan `src/plugins/`, `src/hooks/` |
| `RevenueService` | Gift revenue tracking |

---

## 6. Plugin System

### Subprocess Model

- Each plugin runs as a **separate Python subprocess** (`python src/plugins/<name>/main.py`)
- Communication via **HTTP long-poll** to API:
  - `GET /api/v1/plugins/{name}/commands?wait=1` — fetch commands
  - `POST /api/v1/plugins/{name}/command` — enqueue command (from Bridge/hooks/other plugins)
  - `POST/GET /api/v1/plugins/{name}/state` — push/pull overlay state
  - `POST /api/v1/plugins/{name}/overlay-html` — register overlay HTML
  - `GET /api/v1/plugins/{name}/overlay` — serve overlay to OBS
  - `GET /api/v1/plugins/{name}/stream` — SSE for overlay updates

### Manifest (`plugin.json`)

Fields: `name`, `version`, `entry_point`, `display_name`, `min_api_version`, `capabilities`, `depends_on`, `accepted_commands`, `emitted_events`, `config_schema`, `update_url`, `comment_handler`.

### BasePlugin (`src/core/base_plugin.py`)

Provides: `register_handler()`, `push_state()`, `get_overlay_html()`, `run()`, `api_post()`, `send_command()`, `enqueue_trigger()`, config loading with schema validation and healing.

### Built-in Plugins

| Name | Dir | Purpose |
|------|-----|---------|
| timer | `timer/` | Countdown/count-up timer with milestones |
| death-counter | `deathcounter/` | Player death tracking |
| win-counter | `wincounter/` | Win/loss tracking |
| spotify-control | `spotify/` | Spotify playback via chat (OAuth) |

---

## 7. Hook System

### In-Process Model

- Hooks run **in the API process** (not subprocesses)
- `hook.json` manifest (similar to plugin.json but simpler)
- `main.py` exports `register(api: HookAPI)`
- HookAPI (`src/core/hook_api.py`): `register_action()`, `rcon_enqueue()`, `send_overlay_text()`, `get_config()`, `get_hook_config()`, `enqueue_trigger()`, `api_post()`, `log`

### Security

- AST-based import restriction (`src/core/hook_loader.py`, `src/core/sandbox.py`)
- Allowed modules: `core.hook_api`, `core.error_codes`, `logging`, `json`, `dataclasses`, `typing`, `re`, `datetime`, `random`, `math`, `collections`, `itertools`, `functools`, `hashlib`, `hmac`, `base64`, `urllib.parse`, `html`

---

## 8. Configuration System

### User Config (`config/config.yaml`)

- Copied from `defaults/config.yaml` on first run
- Read/written by `ApiService` using **ruamel.yaml** (preserves comments & formatting)
- `auto_update_config: true` merges new keys from defaults on startup (never removes user keys)

### Key Sections

- `api.port` (29185), `server_host` (127.0.0.1)
- `rcon` (enabled, port 25575, password)
- `minecraft_server_api` (api_port 29187, web_server_port 29188)
- `tiktok` (user, reconnect_delay, follow_tracking, like_triggers)
- `comment_commands` (groups with prefix, roles, cooldowns)
- `overlay` (overlays[], display_mode)
- `gui`, `update`, `plugin_sandbox`, `shutdown`

---

## 9. Actions & Triggers (`data/actions.mca`)

Format: `trigger: action1 ; action2 ; action3`

### Action Prefixes

| Prefix | Handler | Example |
|--------|---------|---------|
| `/` | Datapack function | `/give @a diamond` |
| `!` | RCON direct | `!say Hello` |
| `/command !rc` | Vanilla via RCON | `/command !rc say {user}` |
| `$` | Hook script | `$random` |
| `>>` | Core overlay | `>>Title|Subtitle|5` |
| `@name>>` | Named overlay | `@alerts>>Hi|{user}|3` |
| `&` | Shell command | `&notepad.exe` |

### Modifiers

- `;` — chain actions
- `xN` — repeat N times
- `{user}`, `{comment}` — placeholders
- `#` / `##` — comment / disabled trigger

---

## 10. Event-Command Mapper (`data/event_commands.yaml`)

Maps events → plugin commands:

```yaml
event_commands:
  minecraft.player_death:
    - target: timer
      command: pause
  timer.zero:
    - target: win-counter
      command: add_win
      args: {amount: 1}
```

Built-in event types: `minecraft.player_death`, `minecraft.player_respawn`, `timer.*`, `server.started`, `server.stopping`.

Targets: `timer`, `spotify-control`, `death-counter`, `win-counter`.

---

## 11. Overlay System

### Core Overlay (Bridge)

- Served at `GET /api/v1/overlay?overlay={name}&chroma={bool}`
- SSE stream at `GET /api/v1/overlay/stream`
- `POST /api/v1/overlay/display` — trigger from actions.mca (`>>`)
- `POST /api/v1/overlay/preview` — live theme editor preview

### Plugin Overlays

- Plugin provides HTML via `get_overlay_html()` → `POST /api/v1/plugins/{name}/overlay-html`
- Served at `GET /api/v1/plugins/{name}/overlay`
- SSE at `GET /api/v1/plugins/{name}/stream`
- State via `push_state()` → `POST /api/v1/plugins/{name}/state`

---

## 12. Build & Release (`build.py`)

### Build Tasks (PyInstaller)

| Task | Source | Dest | Notes |
|------|--------|------|-------|
| `start` | `src/python/start.py` | root | Supervisor |
| `main` | `src/python/main.py` | root | Bridge |
| `gui` | `src/python/gui.py` | root | Desktop app (Qt) |
| `overlay` | `src/python/overlay.py` | core | Standalone overlay |
| `server` | `src/python/server.py` | root | API-only server |
| `update` | `src/python/update.py` | root | Self-updater |
| `test_trigger` | `src/python/send_trigger.py` | test | CLI trigger tester |

- Qt binaries (gui, overlay, plugins) share a single **PyQt6 runtime** under `core/runtime/`
- Windows: NSIS installer (`installer/install.nsi`)
- Linux: Shell installer (`installer/install_linux.sh`) → `~/.local/share/TikTok2Mc`
- CI builds versioned assets: `TikTok2MC-v1.0.0-Windows-Setup.exe`, `TikTok2Mc-v1.0.0-Linux-Setup.sh`

---

## 13. Data Flow Summary

```
TikTok Live
    │
    ▼
TikTokLive Client (Bridge thread)
    │
    ├──▶ EventBus.publish("tiktok.*") ──▶ API Server ──▶ GUI (SSE)
    │
    ▼
Trigger Queue (asyncio)
    │
    ▼
Trigger Worker → TriggerEngine.execute_trigger()
    │
    ├──▶ / (Datapack) → .mcfunction files
    ├──▶ ! (RCON) → RCON Queue → Minecraft Server
    ├──▶ $ (Hook) → HookAPI → Hook handler
    ├──▶ >> (Overlay) → Overlay Manager → SSE → OBS
    ├──▶ & (Shell) → subprocess
    └──▶ @name>> (Named Overlay) → specific overlay channel

Minecraft Server Events (player_death, etc.)
    │
    ▼
Event-Command Mapper (event_commands.yaml)
    │
    ▼
Plugin Commands (HTTP POST /api/v1/plugins/{name}/command)
```

---

## 14. Key Design Principles

1. **Single TriggerEngine** — all trigger execution logic in one place
2. **API as Control Plane** — Bridge, GUI, Plugins, Hooks all talk via HTTP
3. **EventBus for Decoupling** — in-process pub/sub for real-time updates
4. **Supervised Subprocesses** — CrashManager restarts failed components
5. **Config Preserves Comments** — ruamel.yaml for user-friendly config
6. **Schema-Driven GUI** — plugin/hook config_schema generates forms
7. **No Shared State** — plugins/hooks communicate only via API/EventBus

---

## 15. Version Constants (`src/core/version.py`)

| Constant | Value |
|----------|-------|
| `TOOL_VERSION` | `"v1.0.0"` |
| `API_VERSION` | `"1.0.0"` |
| `UPDATER_VERSION` | `"v1.4.0"` |
| `EXPECTED_CONFIG_VERSION` | `"1.0"` |

---

## 16. Error Codes (`src/core/error_codes.py`)

Structured codes: `SUBSYSTEM-NNNN` (e.g., `TIKTOK-0001`, `HOOK-0005`, `API-0001`).
22 subsystems, 7 severity levels (DEBUG..FATAL).
Available via `GET /api/v1/diagnostics/error-codes`.

---

## 17. Developer Tools

| Tool | Purpose |
|------|---------|
| `create_plugin.py` / `create_hook.py` | Scaffold new plugin/hook |
| `send_trigger.py` | Manual trigger testing (`python send_trigger.py follow --user X`) |
| `check_deps.py` | Verify/install Python + system dependencies |
| `build.py` | Build binaries, installer, VSIX, run tests |
| `tools/diff_test_mca.py` | Python↔JS validator parity test |
| `tools/update_test/` | Updater E2E harness (mock GitHub Releases) |

---

*Generated from code as of v1.0.0. Keep in sync with implementation.*