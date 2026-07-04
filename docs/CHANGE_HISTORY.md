# TikTok2Mc — Project History

> This file only contains completed work and historical project changes.
>
> Open tasks, release blockers, and unfinished work belong in `docs/TODO.md`.

---

## v1.0.0-dev (Current Development)

### Server Manager Overhaul
- **Create Server UI** — new `+ Create Server` button in Server Manager header with modal (name/version/port fields). Backend `create_instance` validates port/name conflicts.
- **Console Instance Selector** — dropdown to pick which Minecraft server instance to watch. SSE events filtered by `instance_id`. RCON auto-disconnects on switch. Auto-selects single server if only one exists.
- **Server Lifecycle UX** — disable buttons during transitions (start/stop/restart), validate create form on every input/change event, live uptime display, `_serverActionInProgress` guard prevents double actions.
- **Restored Server Manager features** — Open Folder button (calls `POST /servers/instances/{id}/open`), Delete button for non-default instances, Version Library now shows only installed versions without active/current indicator. Removed `active` flag from `ServerVersionInfo`.
- **Server validation fixes** — `active_version` undefined crash in `list_servers` (HTTP 500) fixed; `safe_versions` fallback for 1.21.11 display.
- **Instance-based server paths** — all server directories now instance-aware.
- **Sidebar simplified** — removed dropdown menus for Plugins and Hooks from GUI sidebar.
- **Datapack source-of-truth** — moved to `server/datapack/`; Setup Wizard skips already-configured steps.

### Hook System & Trigger Simulator
- **Trigger Simulator (Event Tester) API** — new `GET/POST /api/v1/triggers/*` endpoints (`/types`, `/execute`, `/tiktok-connection`, `/comment`, `/history`). GUI test trigger card for simulating follow/like/gift/share/join/comment events through the full pipeline (EventBus, reactions).
- **Hook management enhancements** — hook caching (avoids redundant FS scans), auto-discovery on first list request, clean-stale mechanism for removed hook directories.
- **Hook auto-discovery at startup** — `_discover_hooks_at_startup()` called in server lifespan so hooks appear in GUI immediately without waiting for bridge process.
- **Test trigger GUI fix** — corrected executable paths (`text_trigger.exe` → `test_trigger.exe`) and orphaned subprocess cleanup on timeout.

### RCON Console
- **Connection timeout** — RCON connect and MCRcon constructor wrapped in `asyncio.wait_for(..., timeout=5.0)` to prevent indefinite hangs.
- **RCON pre-configuration** — server startup reads RCON settings from `config.yaml` and pre-configures `RconService` so console works on first request.

### Infrastructure
- **CancelledErrorMiddleware** — suppresses `asyncio.CancelledError` spam on client disconnect, returns proper HTTP 499 status.
- **Gift images static mount** — `/gifts-pictures` mounted from `core/assets/gifts_picture/`.
- **GUI dashboard static mount** — `/gui` mounted from `templates/gui/`.

### Test & Build Hardening
- **Test isolation violations fixed** — `document.body.innerHTML +=` destroying DOM references causing `connectLogStream` test failures; test setup isolation improved.
- **TestServerLifecycle** — added server-related test coverage for launcher and lifecycle.
- **Build.py fix** — `version/` → `versions/` path correction.

### Fixed Bugs
- `active_version` undefined in `list_servers` causing HTTP 500
- SSE `ConnectionResetError` not handled gracefully
- Server paths not instance-aware (multi-server conflict)
- Test isolation violations (DOM references, `document.body.innerHTML +=`)
- `1.21.11` showing as unsafe version (via `safe_versions` fallback)
- Orphaned subprocesses on trigger dispatch timeout
- Sidebar dropdown for Plugins/Hooks removed (was confusing with new Hook system)
- Wizard skipping configured steps (datapack path)

### Plugin Decoupling & Architecture
- **Declarative Event Routing** — `main.py` no longer hardcodes plugin names. Events are published to EventBus; `_event_bridge_worker()` reads `event_subscriptions` from every `plugin.json` and routes automatically. Third-party plugins receive events the same way as official ones.
- **Removed ChannelPoints Plugin** — `src/plugins/channelpoints/` deleted entirely (281 lines). The main system no longer manages economy/points.
- **Removed LikeGoal Plugin entirely** — `src/plugins/likegoal/` deleted (3 files, 192+ lines). All event subscriptions, theme defaults, configuration schemas, test coverage, overlay templates, GUI catalog entries, and documentation references removed.
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
- `channel-points` manifests updated with `event_subscriptions`

### Plugin Architecture Modernisation
- **`BasePlugin` base class** (`src/core/base_plugin.py`) — shared config load, theme, API helpers (`api_post`, `api_get`, `push_state`, `register_handler`), command polling, state push, window state, overlay registration. 18 tests.
- **Timer completely rewritten** — fully decoupled. Publishes `timer.*` events to EventBus. Removed `depends_on`, `auto_win`, `pause_on_death`.
- **WinCounter rewritten** — fully decoupled. Publishes `win.milestone` and `win.record_low` events. Removed `decrement_on_death` (was DeathCounter coupling). Config: `initial_needed`, `milestone_increment`, `signal_on`.
- **DeathCounter rewritten** — fully decoupled. Publishes `death.milestone` events. Config: `milestones`, `signal_on`.
<!-- LikeGoal was rewritten but has since been removed entirely -->
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

### GUI: Event Reactions Redesign & Live Dashboard
- **Event Reactions (redesigned Event-Command Mapper)** — replaced the technical "Mappings/Actions" UI with a guided 3-step wizard:
  - Visual reaction cards with category filters, search, and templates
  - Human-readable event/plugin/command catalogs with icons
  - Live preview bar and contextual descriptions
  - Test button on every reaction card
  - Backend data model unchanged (YAML compat preserved via `data/event_commands.yaml`)
- **TikTok EventBus publishing fix** — `tiktok.follow`, `tiktok.like`, `tiktok.gift`, `tiktok.join`, `tiktok.comment`, `tiktok.share` now publish as distinct event types (e.g. `tiktok.follow`) instead of all being bundled under `tiktok.event`. Makes them usable in Event-Command Mapper / Event Reactions.
- **Live Dashboard** — new `DashboardPublisher` (`src/core/api/dashboard_publisher.py`) pushes `plugin_states`, `ecm_diagnostics`, and `reactions_activity` every 5s via the existing SSE stream. New "Live Plugin Health" card with color-coded status pills and "Recent Activity" card with live reaction feed.
- **Save-button state sync** — Config Editor, Plugin Config Editor, and Actions Editor: dynamic Save button enabled only when dirty, real-time input listeners with debounce, unsaved-changes dialog on close.
- **Single-instance guard** — GUI prevents multiple instances via named mutex; auto-switches to dashboard on second launch.
- **Improved event_bus GUI** — better visualization of EventBus activity in the dashboard.
- **Overlay Preview + Live Theme Editor** — `POST /api/v1/overlay/preview` endpoint accepts `theme_overrides` for live preview rendering. Dashboard preview iframe card with Refresh + Send Test buttons. Config editor "Overlay Text" section live preview with 600ms debounced auto-refresh on color input changes. In-editor test message form (title, subtitle, duration). Built-in overlay URLs shown alongside plugin URLs in dashboard.

### UI/UX Redesign (Unified Design System)
- **Design system tokens** — new `templates/gui/design-system.css` with centralized CSS custom properties for colors, spacing, typography, radius, shadows, transitions, z-index, animations, focus-visible, and reduced-motion.
- **Style.css refactor** — 1912 lines rewritten to use design system tokens with BEM-style class naming (`btn--primary`, `card--status`, etc.).
- **Launcher redesign** — unified accent color from blue (#60a5fa) to amber (#f5c518), replaced all inline CSS with proper classes, added pulse animation on status dots, subtle gradient background.
- **Legacy compatibility** — CSS variable aliases (--bg, --surface, etc.) and button class aliases (.btn-primary, .btn-secondary) maintained for backward compatibility with dynamically generated HTML.
- **Overlay refinements** — Inter font stack, antialiasing, smoother transitions applied to deathcounter, timer, wincounter, spotify, and core overlay templates.
- **Modal z-index fix** — raised modal z-indices from 250 to 350-500 so they always appear above editor overlays.
- **Translation cleanup** — German labels in HTML templates translated to English.
- **False-positive diff fix** — `comment_commands.groups` diff detection: `setValue` now creates arrays (not objects) for numeric-index paths, `computeDiff` detects type mismatches properly, `buildGroupCard` no longer mutates `commands_config` from array to object.

### Build System Improvements
- **Core_hash cache scoping** — build cache now invalidates on any `src/core/` change instead of only when specific files change, preventing stale builds from partial cache hits.
- **Config schema drift detection** — `_validate_config_schema` in `src/core/api/services/__init__.py` now skips missing keys during validation instead of raising `ValueError` (HTTP 500), allowing legacy configs to save without error.
- **Increased build parallelism** — `ThreadPoolExecutor` max_workers increased for faster PyInstaller compilation.

### Spotify: Plugin-Local Config Migration
- Removed `spotify` section from `defaults/config.yaml` — Spotify tokens, client_id, and client_secret now live in `src/plugins/spotify/config.yaml`.
- `SpotifyClient` updated to read/write tokens from plugin-local config via `core.yaml_utils`.
- `spotify_setup.py` updated to write to plugin-local config path.
- GUI updated: added `plugin_sandbox`, `port_policy`, and `api_key` sections to `SECTION_ORDER`, `CATEGORIES`, and `SECTION_META` with corresponding `FIELD_META` and `HELP_TEXT`.
- `unknownKeys` tracking fix: preserved `originalUnknownKeys` across state resets.

### Stability & Logging
- **Plugin registry backup spam eliminated** — removed per-save backup from `PluginRegistry._save()`. Only one startup backup is created when the registry file already exists.
- **Built-in app health-check noise fixed** — `start.py` health-check loop now skips built-in apps (`App`, `Minecraft Server`, `GUI`, `Overlay`) instead of trying to update them in the plugin registry. URL-encodes all plugin names in API calls to prevent "control characters in URL" errors.
- **API config save hardening** — missing config keys (e.g. `api_key` in legacy configs) no longer cause HTTP 500. `_validate_config_schema` skips missing keys instead of raising `ValueError`.

### Test & Build Hardening
- **Test suite stability fix** — fixed infinite tight-loop in `test_base_plugin.py` (2 tests calling `_command_polling_loop` without exit condition). Added `time.sleep(0.1)` safety guard in `BasePlugin._command_polling_loop`. Mocked heavy imports (`TikTokLive`, `mcrcon`, `flask`) in `conftest.py` to prevent test hangs. Configured `pytest-timeout = 40s`.
- **End-to-end update validation** (`tests/test_core/test_update_integration.py`) — version boundary upgrade, signal lifecycle, restart flow, rollback, platform paths. 24 tests.
- **Spotify test migration** — `test_spotify_setup.py` updated for plugin-local config path.

### Error Handling & Diagnostics Framework
- **Structured error code system** (`src/core/error_codes.py`, 1333 lines) — every error receives a stable, documented error code with subsystem prefixes (CORE, PLUGIN, API, CONFIG, LIFECYCLE, MC, TIKTOK, HOOK, DIAG, etc.). `list_all_codes()`, `get_error_code()` lookup API.
- **CrashManager** (`src/core/crash_manager.py`) — centralized crash capture for main thread, worker threads, asyncio tasks, futures, and plugin crashes. Every crash assigned an error code, logged with structured context, preserves stack traces, notifies health monitor.
- **HealthMonitor** (`src/core/health_monitor.py`) — health state machine with 8 states (UNKNOWN → STARTING → RUNNING → DEGRADED → FAILED → RECOVERING → STOPPING → STOPPED) and valid transition enforcement. Every major subsystem exposes a health state.
- **Diagnostics report** (`src/core/diagnostics.py`) — comprehensive runtime snapshot including component states, recent errors, crash history, queue/thread/async task statistics.
- **ValidationFramework** (`src/core/validation_framework.py`) — structured validation for startup, shutdown, runtime, and operation timeouts; every step produces a clear result with error code.
- **Diagnostics API routes** — `GET /api/v1/diagnostics` and `GET /api/v1/health` endpoints for runtime introspection.
- **Integration** — EventBus, base_plugin, lifecycle, hook_loader, plugin_watcher, backup, logger, overlay, update, and start.py all wired into health monitoring and crash reporting.

### Trigger Engine Redesign
- **Shared `trigger_engine/` module** — extracted from `trigger_service.py` into dedicated package (`models.py`, `engine.py`, `dispatcher.py`, `validator.py`)
- **TriggerEngine** — orchestrates trigger execution with timeout, payload validation, and dispatch
- **PayloadValidator** — validates trigger payloads against expected schemas per trigger type
- **BridgeDispatcher** — handles subprocess dispatch to the TikTok bridge executable with proper cleanup and orphan prevention
- **Trigger models** — `TriggerType` enum (FOLLOW, LIKE, JOIN, SHARE, COMMENT, GIFT, CUSTOM), `ExecutionStatus`, `TriggerResult`, `TriggerDefinition`, `EngineConfig`
- **Standalone CLI tool** — `src/python/send_trigger.py` replaces `tests/send_trigger.py` as a proper utility; `test_send_trigger_cli.py` covers CLI parsing and execution paths
- **Tests** — 435+ tests in `test_trigger_engine.py`, `test_trigger_service.py` expanded to 244 lines

### MCA Language Server (VS Code Extension)
- **Complete language server redesign** — new VS Code extension (`mca-language-server/`) with IntelliSense (completions, hover, go-to-definition), diagnostics (validator with error codes), syntax highlighting (TextMate grammar), symbol navigation (document symbols, outline), and code snippets
- **VSIX build integration** — `build.py` gains `--build-vsix` flag; generates, validates, and differential-tests the VSIX package as part of the build pipeline
- **Spec-driven build system** — `src/core/mca_spec.py` as single source of truth; `tools/generate_mca_spec.py` exports Python runtime definitions (command prefixes, diagnostic codes, trigger types, overlay syntax) to `mca-spec.json`
- **Differential testing** — `tools/diff_test_mca.py` validates spec output consistency across builds; catches regressions in language definition exports
- **MCA definition migration** — language definitions migrated from ad-hoc JavaScript to spec-driven; `src/core/validator.py` enhanced with exportable constants for spec generation
- **9 test suites** — parser, validator, completions, hover, spec, benchmark across ~1000 lines of JS tests
- **Removed `defaults/shell_actions.txt`** — was empty and fully superseded by actions.mca

### Test Expansion
- **1197 total tests green** (Python + GUI) — 17 new test suites added, test ordering fixed, production bugs resolved
- **New test suites:**
  - `test_crash_manager.py`, `test_diagnostics.py`, `test_error_codes.py`
  - `test_health_monitor.py`, `test_validation_framework.py`
  - `test_hook_api.py`, `test_hook_manifest.py`, `test_hook_registry.py`
  - `test_console_capture.py`, `test_core_models.py`
  - `test_dashboard_publisher.py`, `test_gui_launcher.py`
  - `test_minecraft_readiness.py`, `test_plugin_discovery.py`
  - `test_plugin_health_monitor.py`, `test_plugin_overlay_stores.py`
  - `test_rcon_service.py`

### Heartbeat & Process Lifecycle Fixes
- **Heartbeat monitoring scoped** — only running processes are monitored for heartbeats; disabled/stopped processes are skipped to avoid false degradation
- **STARTING→STOPPING transition allowed** — health monitor permits transition from STARTING to STOPPING; heartbeats recorded for all supervised processes including those still in STARTING state

### Build System Improvements
- **`test --all` flag** — `build.py test --all` runs the complete test suite (Python + GUI) in a single command
- **Live pytest output** — `test --all` streams pytest output in real time instead of silent capture, improving CI debugging
- **`--installer` default fix** — set to `False` when `cmd_app` invoked from composed commands to prevent accidental installer builds during routine operations
- **Better default actions.mca comments** — improved inline documentation in `defaults/actions.mca`

### MCA Language Server Fixes
- **Simplified completions** — removed redundant `dollarPrefixes`, `customPrefixes`, and snippet logic from `completions.js`; completion items are now derived directly from the MCA spec
- **Removed inline snippets** — `snippets/mca.code-snippets` deleted (57 lines); snippets are no longer needed as completions provide equivalent functionality
- **Cleaned up packaging** — removed `.vscodeignore`, simplified `package.json` scripts and metadata

### Refactoring
- **Config schema validation extracted** — `_CONFIG_SCHEMA` and `validate_config_schema()` moved from `services/__init__.py` into `validation_framework.py` for reusability and testability
- **Error responses standardised** — `plugin_config.py` changed from dict to string `detail`; `actions.py` replaced `JSONResponse` with `HTTPException` for consistency across API routes (`plugin_overlay.py` OAuth HTML responses kept as browser-facing endpoints by design)

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
- **969 Python tests + 228 GUI frontend tests = 1197 total**
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

*Last updated: 2026-07-04 — Added MCA Language Server Fixes section; added Refactoring section (config schema validation extraction, error response standardisation).*
