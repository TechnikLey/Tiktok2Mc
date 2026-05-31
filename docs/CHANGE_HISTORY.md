# TikTok2Mc — Project History

> This file only contains completed work and historical project changes.
>
> Open tasks, release blockers, and unfinished work belong in `docs/TODO.md`.

---

## v1.0.0-dev (Current Development)

### Plugin Decoupling & Architecture
- **Declarative Event Routing** — `main.py` no longer hardcodes plugin names. Events are published to EventBus; `_event_bridge_worker()` reads `event_subscriptions` from every `plugin.json` and routes automatically. Third-party plugins receive events the same way as official ones.
- **Removed ChannelPoints Plugin** — `src/plugins/channelpoints/` deleted entirely (281 lines). The main system no longer manages economy/points.
- **Removed hardcoded `like-goal` coupling** — `validate_like_triggers()` and `likegoal_queue` removed from `main.py`. Like events go through EventBus → EventBridge.
- **Removed hardcoded `overlay-text` coupling** — `overlay_utils.py` made plugin-agnostic with optional `plugin_name` parameter.
- **Removed `points_cost` from comment commands** — was a ChannelPoints-specific leak into the core command framework.
- **Removed `random_triggers` from main config** — moved to `hooks/random/config.yaml` where it belongs.
- **Removed hardcoded Spotify URLs** — `{spotify_port}` placeholders and direct HTTP endpoints removed from `defaults/config.yaml`.

### Hook System Redesign
- `HookManifest` (`hook.json`) with name, version, config_schema, update_url
- `HookRegistry` (persistent JSON, thread-safe, backup-managed)
- `HookLoader` rewritten: scans `hooks/` + `plugins/*/hooks/` by manifest, loads per-hook config, syncs registry, filters by enabled state
- Per-hook config via `api.get_hook_config(name)`
- Hook management API: list, discover, enable/disable, config CRUD (8 REST endpoints)
- `create_hook.py` scaffolding script (mirrors `create_plugin.py`)
- Hooks restructured from flat `.py` to subdirectories (`hook.json` + `main.py`)
- Spotify hook absorbed into `plugins/spotify/hooks/spotify_control/`
- Folder renamed `event_hooks/` → `hooks/`

### Build & Release Structure
- `gui`, `update`, `server` exes moved into `core/` (only `start.exe` at root)
- Plugin hooks in `plugins/*/hooks/` no longer compiled to `.exe` (stay as raw `.py` for in-process import)
- `example_hook` excluded from release build

### EventBus Adoption
- `EventBridge` worker added: subscribes to EventBus, translates `tiktok.*` events to plugin commands via `command_queue.enqueue()`
- `event_subscriptions` field added to `PluginManifest` model
- `channel-points` and `like-goal` manifests updated with `event_subscriptions`

---

## Pre-v1.0.0 Milestones

### Port Consolidation
- **7 plugin ports eliminated** (29186, 29189, 29190, 29191, 29193, 29194, 29195)
- All Flask servers removed from plugins
- New infrastructure: `PluginStateStore`, `CommandQueue`, `OverlayHtmlStore`
- 7 new API routes: overlay registration/serving, per-plugin SSE streams, command enqueue/poll, state get/set, generic OAuth callback
- Plugin communication model: plugins poll `GET /api/v1/plugins/{name}/commands`, push state via `POST /api/v1/plugins/{name}/state`
- Spotify OAuth callback routed through Main API

### GUI (Complete Feature Set)
- pywebview shell + SPA dashboard
- First-Run Setup Wizard (TikTok username, RCON password with strength meter)
- Plugin Manager (enable/disable toggles, overlay URL helper, config edit)
- Restart System (`POST /api/v1/restart` with signal file)
- Shutdown System (confirmation dialog, graceful countdown, cancel, immediate "Shutdown Now")
- Full `config.yaml` Editor (section-based nav, search, validation, diff review)
- Plugin Config Editor (schema-driven dynamic forms, all field types)
- Actions Editor (visual + raw mode, gift picker, script dropdown, live validation)
- Unsaved Changes Protection (`beforeunload` + pywebview polling)
- Live Log Streaming (SSE `/api/v1/events/stream`)

### API & Plugin System
- Central FastAPI server (`127.0.0.1:29185`) with 24+ REST routes
- `API_VERSION` centrally defined; `DEFAULT_PORT` unified
- Deterministic plugin discovery via `plugin.json` manifests
- `PluginLauncher` API-only
- Enable/disable endpoints (atomic — signal written before registry update)
- Discovery endpoint (`GET /api/v1/plugins/discover`)
- Health polling with 10s timeout
- Plugin health monitoring (watchdog + auto-restart)
- Registry/filesystem sync (polling daemon)
- DELETE endpoint (stops process + cleans signals)
- EventBus in-memory pub/sub with SSE and WebSocket endpoints
- Plugin-local configuration API (`GET|PUT /api/v1/plugins/{name}/config`)
- `PluginUpdateChecker` with semver, download, install, extract, rollback
- Tool update check (`GET /api/v1/updates/check`)
- Dual signaling (file-based `update_signal.tmp` + API `/updater/signal`)

### Plugin Config Architecture
- Self-contained per-plugin `config.yaml` alongside manifests
- `config_schema` in `plugin.json` drives defaults, validation, GUI rendering
- Schema types: `string`, `integer`, `number`, `boolean`, `color`, `select`, `array` (nested `item_schema`), `object`
- Full validation backend (required, min/max, regex, select options, array items)
- `ruamel.yaml` round-trip system preserving comments, quotes, ordering
- Atomic writes with versioned backups (`*.v1.bak`)
- Config validation on load (heals invalid values against schema defaults)
- Framework-managed `enabled` (built-in boolean field, stripped from plugin schema)

### Backup System
- `BackupManager` (`core/backup.py`) with SHA-256 dedup, retention, coalescing, category management
- Versioned backup files (`*.v<N>.bak`)
- Integrated into registry, plugin config, config.yaml, and actions.mca

### Testing
- **506 Python tests + 226 GUI frontend tests = 732 total**
- GUI frontend (Vitest + JSDOM): 226 tests across helpers, config-editor, plugin-config-editor, actions-editor, dashboard
- CI workflow `test.yml` on push/PR to `main`
- BackupManager: 30 standalone tests
- TikTok bridge core: 38 tests
- Update lifecycle: 24 tests
- End-to-end update: 34 tests
- Hook system: 13 tests
- Smoke tests for all plugin manifests

### Documentation
- `README.md` rewritten for v1.0.0
- `GUIDE.md` rewritten (architecture, plugin system, API, actions/triggers, update system)
- `CHANGELOG.md` normalized (Keep a Changelog format)
- `config.yaml` inline documentation improved

### Legacy Cleanup
- `python/registry.py`, `client.py`, `--register-only` CLI flag removed
- Legacy `gui.py`, `plugin_updater.py` removed
- Old self-registration `register_plugin()` calls removed from all plugins
- Legacy fallback `EditableResponse`, `ImportLegacyResponse`, `validate_config_dict`, `read_plugin_registry()` removed

### Fixed Bugs
- `commands_config` default type mismatch (`[]` → `{}`)
- Config editor scroll-spy and sidebar order alignment
- Plugin settings removed from main config editor (moved to plugin-specific)
- Shutdown cancel signal race (1s polling instead of 5s file watcher)
- Shutdown countdown UI race
- ShutdownNow race condition
- Overlay X layout, script dropdown/search
- Registry/filesystem state mismatch (auto-sync via polling watcher)
- Enable/disable ↔ process state gap (health monitoring + heartbeat)
- Non-atomic enable/disable (signal file written before registry update)
- Dead plugin entries on DELETE
- Config schema validation not enforced on load
- Single version source of truth (`core/version.py`)
- 11 pre-existing test failures (module-level `from core.paths import` before monkey-patching)
- `update.py` module-level side effects crashing pytest on import
- `server/` directory incorrectly whitelisted

---

*Last updated: 2026-05-31*
