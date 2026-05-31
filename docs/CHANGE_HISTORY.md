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
- **Promoted `overlay-text` to built-in core subsystem** — `src/plugins/overlaytxt/` deleted entirely. New `src/core/overlay.py` manages config (global `config.yaml`), circuit breakers, HTML rendering, and direct EventBus dispatch. New `src/python/overlay.py` standalone window process. Dedicated API routes at `/api/v1/overlay/*`. Removed plugin manifest, config schema, and lifecycle indirection.
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

### Plugin Architecture Modernisation
- **`BasePlugin` base class** (`src/core/base_plugin.py`) — shared config load, theme, API helpers (`api_post`, `api_get`, `push_state`, `register_handler`), command polling, state push, window state, overlay registration. 18 tests.
- **Timer completely rewritten** — fully decoupled. Publishes `timer.*` events to EventBus. Removed `depends_on`, `auto_win`, `pause_on_death`.
- **WinCounter rewritten** — fully decoupled. Publishes `win.milestone` and `win.record_low` events. Removed `decrement_on_death` (was DeathCounter coupling). Config: `initial_needed`, `milestone_increment`, `signal_on`.
- **DeathCounter rewritten** — fully decoupled. Publishes `death.milestone` events. Config: `milestones`, `signal_on`.
- **LikeGoal rewritten** — fully decoupled. Publishes `likegoal.milestone` and `likegoal.progress` events. Removed direct TikTok event dependency; now consumes `add_likes` commands via API.
- **SpotifyControl modernised** — publishes `spotify.track_changed`, `spotify.play`, `spotify.pause` events. Config: `signal_on`.
- **Plugin dependency ordering** — topological sort in `AppConfig`, `depends_on` field, enforced on register/put/enable. 30 tests.

### Core Infrastructure Improvements
- **Declarative Command Handler Registration** — `CommentHandler` model, `PUT/DELETE /plugins/{name}/comment-handler`, `GET /comment-handlers`. Spotify registers `$` prefix in `plugin.json`; bridge dispatches comments to plugin API instead of hardcoded HTTP URLs. Removed `handler`/`url` from `config.yaml` Spotify group.
- **Port Scanner** (`src/core/port_scanner.py`, 28 tests) — scans 3 bind ports (29185/29187/29188) on startup, auto-resolves conflicts via env vars + runtime file. `port_policy` config section with `max_offset: -1` for unlimited scanning.
- **core_hash Build Cache Optimization** — replaced global all-or-nothing `core_hash_changed` flag with per-task dependency tracking via AST import analysis. Changing one core file only invalidates executables that actually import it.
- **EventBus Plugin Integration** — replaced 0.5s polling loops with long-polling (`?wait=1`), backed by `asyncio.Event` notification on command enqueue. Zero-latency command delivery, no CPU wasted on idle polling.
- **Spotify OAuth Centralisation** — tokens moved from `data/spotify_token.json` into `config.yaml` `spotify` section. `SpotifyClient` reads/writes via `core.yaml_utils` (`load_yaml` / `save_yaml`) instead of a separate JSON file, aligning with `spotify_setup.py` output.
- **Event-Command Mapper** (`src/core/event_command_mapper.py`, 8 tests) — central background task that listens to EventBus events and dispatches plugin commands via `CommandQueue`. Reads mapping config from `data/event_commands.yaml`. Eliminates all hardcoded plugin-to-plugin coupling. Minecraft bridge now publishes `minecraft.player_death` and `minecraft.player_respawn` to EventBus instead of only pausing the comment queue locally.

### New Features
- **API Authentication** — `api_key` config field, middleware checks `X-API-Key` header on non-localhost requests. `start.py` warns when exposed without key. 6 tests.
- **GUI Installer** — Windows NSIS installer (`installer/install.nsi`). Setup wizard, desktop/start menu shortcuts, startup registration, uninstall. Built via `python build.py --installer`. 13 tests.
- **Spotify OAuth Flow Helper** — CLI wizard (`src/python/spotify_setup.py`) guiding users through Spotify OAuth: opens browser, runs local callback server, exchanges code for tokens, saves to config. Also supports `--refresh` mode. 16 tests.

### Shell Command Integration (actions.mca)
- **Merged `shell_actions.txt` into `actions.mca`** — shell commands now use the `&` prefix inside `actions.mca` instead of a separate file. Unified parser, validator, serializer, and execution path.
  - New `&` prefix: `12345:&curl -X POST http://localhost:29191/add`
  - Full support in `ActionsService` parser/serializer (`shell` command type)
  - Validator accepts `&` as valid prefix
  - `generate_datapack()` parses `&` into `ctx.shell_actions_cache` (list-based, supports chaining via `;` and repetition via `xN`)
  - `execute_global_command()` schedules shell commands alongside vanilla/RCON/script/overlay actions
  - GUI Actions Editor supports `shell` type in dropdown with plain text input
  - Removed legacy `load_shell_actions()` and `_migrate_shell_actions()` (v1.0.0 has no prior users to migrate)
  - Removed `shell_actions.txt` from build release files and documentation
  - Added `tests/test_core/test_actions_service.py` (9 tests) and expanded existing test coverage for shell parsing

### Test & Build Hardening
- **Test suite stability fix** — fixed infinite tight-loop in `test_base_plugin.py` (2 tests calling `_command_polling_loop` without exit condition). Added `time.sleep(0.1)` safety guard in `BasePlugin._command_polling_loop`. Mocked heavy imports (`TikTokLive`, `mcrcon`, `flask`) in `conftest.py` to prevent test hangs. Configured `pytest-timeout = 40s`.
- **End-to-end update validation** (`tests/test_core/test_update_integration.py`) — version boundary upgrade, signal lifecycle, restart flow, rollback, platform paths. 24 tests.

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
- **608 Python tests + 228 GUI frontend tests = 836 total**
- GUI frontend (Vitest + JSDOM): 228 tests across helpers, config-editor, plugin-config-editor, actions-editor, dashboard
- CI workflow `test.yml` on push/PR to `main`
- BackupManager: 30 standalone tests
- TikTok bridge core: 38 tests
- Update lifecycle: 24 tests
- Hook system: 13 tests
- Smoke tests for all plugin manifests
- BasePlugin: 18 tests
- Plugin dependency ordering: 30 tests
- Port Scanner: 28 tests
- Plugin lifecycle + auth: 26 tests (20 lifecycle + 6 auth)
- GUI installer: 13 tests
- Spotify OAuth helper: 16 tests
- Timer plugin: 12 tests (direction, tick, loop, milestones, signals, formatting)
- Event-Command Mapper: 8 tests (config loading, dispatch, lifecycle)
- Test suite stability: infinite loop fix, `pytest-timeout = 40s`, heavy-import mocking

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

### Security
- **Spotify client_secret validation and encrypted storage** — `validate_spotify_client_secret()` enforces length/format checks. `core/secure_storage.py` provides Fernet-encrypted storage for `client_secret`, `access_token`, and `refresh_token` in `config.yaml`. Fallback XOR obfuscation when `cryptography` is unavailable.
- **Download integrity verification** — `core/checksum.py` provides `compute_sha256`, `verify_checksum`, `fetch_checksum`, and `find_checksum_asset_url`. Plugin updater (`core/api/updater.py`) and tool updater (`src/python/update.py`) now verify SHA-256 checksums after download and abort on mismatch. CI workflow generates `.sha256` companion files for release archives.

### Architecture
- **Plugin sandboxing / resource limits** — `core/sandbox.py` introduces `PluginSandbox` with cross-platform resource restriction:
  - Linux: `RLIMIT_AS` (memory), `RLIMIT_CPU`, `RLIMIT_NOFILE`, `RLIMIT_NPROC` via `preexec_fn`, plus lowered niceness.
  - Windows: `BELOW_NORMAL_PRIORITY_CLASS` / `IDLE_PRIORITY_CLASS` via `creationflags`, plus optional job-object memory limits via `apply_post_spawn()`.
  - Configurable via new `plugin_sandbox` section in `config.yaml`.
  - Integrated into `start.py` `start_plugin_process()` for direct-spawn plugins.

---

*Last updated: 2026-06-01*
