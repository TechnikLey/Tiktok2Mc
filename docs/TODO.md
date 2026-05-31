# TikTok2Mc — Release TODO (v1.0.0)

> **Goal:** Ship stable v1.0.0.
> v1.0.0 is intentionally incompatible with v0.x.

---

## Completed (Verified in Codebase / Git)

### Core Bridge
- TikTok Live connection (gifts, follows, likes, shares, comments, joins)
- Minecraft command execution via RCON and datapacks
- Action parser (`data/actions.mca`) with vanilla / RCON / script / overlay support
- Webhook server for MinecraftServerAPI (death/respawn detection)
- Comment commands with role-based permissions, cooldowns, user_cooldown, and channel-points integration
- `random_triggers` filter for `$random` action eligibility
- Follow spam protection (`_followed_cache` in `main.py`)

### API & Plugin System
- Central FastAPI server (`127.0.0.1:29185`) with 24+ REST routes
- `API_VERSION` centrally defined; `DEFAULT_PORT` unified across codebase
- Deterministic plugin discovery via `plugin.json` manifests (8 plugins, 1 test plugin excluded)
- `PluginLauncher` API-only (no legacy registry fallback)
- Enable/disable endpoints: `POST /api/v1/plugins/{name}/enable|disable` (atomic — signal written before registry update)
- Discovery endpoint: `GET /api/v1/plugins/discover` (read-only, no side effects)
- Health polling with 10 s timeout before plugin load
- Fallback mode: continues without plugins if API fails to start
- **Plugin health monitoring** — background watchdog in API server checks heartbeats, stale processes marked unhealthy; `start.py` auto-restarts crashed plugins at process level
- **Registry/filesystem sync** — polling daemon auto-registers new plugin directories and auto-unregisters removed ones
- **DELETE endpoint** stops plugin process and cleans up signal files before unregistering
- EventBus in-memory publish/subscribe (`core/api/eventbus.py`) with SSE (`/events/stream`) and WebSocket (`/ws`) endpoints
- Plugin-local configuration API: `GET|PUT /api/v1/plugins/{name}/config`, `GET /api/v1/plugins/{name}/config/schema`
- `PluginUpdateChecker` with semver comparison and download/install/extract/rollback
- Tool update check: `GET /api/v1/updates/check` (GitHub Releases API)
- Dual signaling (file-based `update_signal.tmp` + API `/updater/signal`)

### Plugin Config Architecture
- Self-contained per-plugin `config.yaml` files alongside manifests
- `config_schema` declarations in `plugin.json` drives defaults generation, runtime validation, and GUI rendering
- Schema types supported: `string`, `integer`, `number`, `boolean`, `color`, `select`, `array` (with nested `item_schema`), `object`
- Full validation backend: required fields, min/max bounds, regex color validation, select options, array item validation
- `ruamel.yaml` round-trip system (`core/yaml_utils.py`) preserving comments, quotes, ordering, and formatting on save
- Atomic writes with versioned backups (`*.v1.bak`)
- Schema-driven default generation from field definitions
- **Config validation on load** — `load_plugin_config()` validates and heals invalid values against schema defaults with warnings
- **Framework-managed `enabled`** — `enabled` is a built-in framework field (type `boolean`, default `True`), stripped from plugin schema processing, injected into all configs and schema API responses automatically

### Backup System
- `BackupManager` class (`core/backup.py`) with SHA-256 dedup, retention, coalescing, category management
- Versioned backup files (`*.v<N>.bak`)
- Integrated into registry, plugin config, config.yaml, and actions.mca save paths

### Plugin Decoupling & Port Consolidation
- Timer, DeathCounter, WinCounter, OverlayText, LikeGoal, Spotify, ChannelPoints — all standalone
- Each plugin exposes its own REST API; no cross-plugin hard dependencies
- Timer: `auto_win: false`, `pause_on_death: false`
- WinCounter: `decrement_on_death: false`
- All plugins default to `enabled: true` (framework-managed; registry controls actual enable state)

### Port Consolidation — COMPLETED
- **7 plugin ports eliminated** (29186, 29189, 29190, 29191, 29193, 29194, 29195)
- **All Flask servers removed from plugins** — each plugin now communicates exclusively via the Main API (127.0.0.1:29185)
- New infrastructure: `PluginStateStore`, `CommandQueue`, `OverlayHtmlStore` in `src/core/api/plugin_overlay.py`
- 7 new API routes: overlay registration/serving, per-plugin SSE streams, command enqueue/poll, state get/set, generic OAuth callback
- All pywebview windows point to `http://127.0.0.1:29185/api/v1/plugins/{name}/overlay`
- Spotify OAuth callback routed through Main API: `/api/v1/plugins/oauth/callback?name=spotify-control`
- New plugin communication model: plugins poll `GET /api/v1/plugins/{name}/commands` (atomic dequeue), push state via `POST /api/v1/plugins/{name}/state`
- Remaining required ports: Main API (29185), RCON (25575), Minecraft Server (25565)
- `port`/`ports` fields removed from `PluginManifest`, `PluginRegistration`, `AppConfig` models
- Plugin manifests (`plugin.json`) and configs (`config.yaml`) cleaned up — no more port declarations

### GUI — Implemented
- `src/python/gui.py` — pywebview shell that opens the dashboard served by the API server
- `templates/gui/index.html` — SPA dashboard with system status, plugin list, config summary, actions editor
- API server mounts `/gui` static files (dev + release layouts supported)
- `start.py` launches `gui.exe` when `gui.enabled: true`
- **First-Run Setup Wizard** — 3 steps: TikTok username, RCON password (with strength meter + validation), review & save. Auto-triggers when RCON password is empty.
- **Plugin Manager** — Enable/disable toggles in dashboard, overlay URL helper with copy-to-clipboard, "Edit Config" button per plugin
- **Restart System** — `POST /api/v1/restart` writes signal; `start.py` uses background daemon thread with `os._exit(0)`
- **Shutdown System** — `POST /api/v1/shutdown` with confirmation dialog, signal file, graceful countdown, cancel, and immediate "Shutdown Now" button. Cancel signal checked directly in countdown loop (1s polling, no longer reliant on 5s file watcher).
- **Full `config.yaml` Editor** — Form-based editor with:
  - Section-based navigation with categories (Connection, Minecraft, Streaming & Overlays, Chat & Commands, Integrations, Appearance, System)
  - IntersectionObserver scroll-spy for active section highlighting
  - Real-time search across setting names, descriptions, and field help text
  - Java RAM settings (`xms`/`xmx` with pattern validation)
  - Like goal triggers (add/remove/edit interval table)
  - Comment commands (full group editor: prefix, handler, mode, roles, cooldown, user_cooldown, trigger_comment_event)
  - Command overrides (`commands_config`) with dynamic add/remove for points_cost, cooldown, user_cooldown, conditional, url, handler, roles
  - Theme color editor (hex pickers with synced text inputs for every plugin)
  - Auto-update, shutdown, console visibility settings
  - Validation for required fields, patterns, min/max bounds
  - Review Changes modal showing diff before save
  - Unknown settings preservation with raw YAML fallback
  - Toast notifications for success/error feedback
- **Plugin Config Editor** — Schema-driven dynamic form renderer (`PluginConfigEditor` class) with:
  - Category-grouped sidebar navigation
  - Field types: boolean, integer, number, select, color, password, textarea, array (table of objects with add/remove rows, tag editor for strings), object with sub-fields
  - Raw JSON fallback editor when no schema
  - Search/filter, validation, diff review, backup before save
  - Plugin restart prompt after save
- **Actions Editor** — Full visual editor (`templates/gui/actions-editor.js`) with:
  - Visual tab: table of triggers, detail panel with inline command editing (vanilla, rcon, script, overlay, named_overlay), add/remove/delete triggers
  - Add Event modal: event type selector (follow/join/comment/likes/like_2/share) or gift picker with search-by-name/ID
  - Script dropdown with search and lazy-loaded script registry (`GET /actions/scripts`)
  - Raw tab: textarea with live validation (debounced 400ms), diagnostics panel, save blocked on errors
  - Gift database integration (`GET /gifts`) with image URLs and coin cost sorting
- **Unsaved Changes Protection** — `beforeunload` event (browser fallback) + pywebview `_pollCloseRequest()` with 200ms polling. Modal with Save & Exit / Exit Without Saving / Cancel.
- **Live Log Streaming** — Frontend connects to `GET /api/v1/events/stream` via `EventSource` on dashboard load. Displays log events (`log` type), server lifecycle events (`server.started`, `server.stopping`), and plugin events (`plugin.*`) in real-time in the log-view card.

### Testing
- **750 total: 524 passed, 3 skipped, 0 failures** (524 Python + 226 GUI frontend; WS streaming tests active, SSE endpoint tested via POST)
- **GUI frontend (Vitest + JSDOM):** 226 tests across 5 test files:
  - `helpers.test.js` — 43 utility function tests (escapeHtml, toTitle, formatUptime, getPluginStatus, validatePassword, etc.)
  - `config-editor.test.js` — 44 ConfigEditor method tests (open/close, getValue/setValue, validate, computeDiff, etc.)
  - `plugin-config-editor.test.js` — 47 PluginConfigEditor tests (schema-driven validation, groupByCategory, field search, etc.)
  - `actions-editor.test.js` — 36 ActionsEditor tests (add/remove commands, trigger management, gift picker, raw editor, etc.)
  - `dashboard.test.js` — 56 dashboard/API helper tests (fetchJSON, log, loadHealth, wizard flow, update checking, log streaming, etc.)
- CI workflow `test.yml` on push/PR to `main` (~9s runtime)
- Coverage: API integration, plugin discovery, manifest validation, updater logic, signal handling, config CRUD, event validation, plugin config system, schema validation, YAML round-trip preservation, theme, overlay utils, actions validator (44 tests), smoke tests for all 8 plugin manifests, **hook system (3 event hooks: random, spotify, example_hook)**
- **BackupManager** (core/backup.py): 30 standalone tests covering create, restore, list, dedup, coalescing, retention, category detection, edge cases
- **TikTok bridge core** (main.py): 38 tests covering `sanitize_filename`, `validate_like_triggers`, `get_safe_username`, `load_shell_actions`, duplicate config detection, webhook event handling
- **Update lifecycle** (update/restart flow): 24 tests covering signal file mechanism, API kill signal, polling-based restart, updater replacement logic, return code handling
- **End-to-end update** (update.py): 34 tests covering config migration, whitelist copy, version I/O, extract_version regex, full `run_update()` orchestration, signal cleanup, platform paths

### Legacy Cleanup
- `python/registry.py`, `client.py` legacy fallback, `--register-only` CLI flag removed
- `gui.py` (legacy) removed; `plugin_updater.py` dead code removed
- `build.py` / `upload.py` version bumped to `v1.0.0`
- Old self-registration `register_plugin()` calls removed from all plugin `main.py` files
- Legacy fallback `EditableResponse`, `ImportLegacyResponse`, `validate_config_dict`, `read_plugin_registry()` removed

### Documentation
- `README.md` rewritten for v1.0.0
- `GUIDE.md` rewritten with architecture, plugin system, API usage, actions/triggers, update system, troubleshooting
- `CHANGELOG.md` normalized with v1.0.0 section (Keep a Changelog format)
- `config.yaml` inline documentation improved

### Fixed Bugs (Git History)
- `commands_config` default type mismatch (`[]` → `{}` in `defaults/config.yaml`) — RESOLVED
- Config editor scroll-spy and sidebar order alignment — RESOLVED
- Plugin settings removed from main config editor (moved to plugin-specific editor) — RESOLVED
- Config save restart prompts, plugin UX, release path resolution — RESOLVED
- Shutdown cancel signal race: now checked directly in countdown loop (1s) instead of file watcher (5s) — RESOLVED
- Shutdown countdown UI race: deterministic termination, immediate UI feedback — RESOLVED
- Overlay X layout, script dropdown/search — RESOLVED
- Script registry lazy-load on first access — RESOLVED
- Test relocation (split test_api/test_core) — RESOLVED
- ShutdownNow race condition (UI freeze on API error) — RESOLVED
- Overlay URLs missing dashboard container — RESOLVED
- Dismiss button on restart-pending banner — RESOLVED
- Dead code in ConfigEditor.collect() — RESOLVED
- Live log viewer connected via SSE — RESOLVED
- Registry/filesystem state mismatch (auto-sync via polling watcher) — RESOLVED
- Enable/disable ↔ process state gap (health monitoring + heartbeat) — RESOLVED
- Non-atomic enable/disable (signal file written before registry update) — RESOLVED
- Dead plugin entries on DELETE (process stopped, signals cleaned) — RESOLVED
- No plugin process health monitoring (watchdog + auto-restart) — RESOLVED
- Config schema validation not enforced on load (load-time healing) — RESOLVED
- Single version source of truth (`core/version.py` as canonical source) — RESOLVED
- 11 pre-existing test failures caused by module-level `from core.paths import` capturing references before monkey-patching — RESOLVED (import → module attribute access pattern)
- `update.py` module-level side effects (`load_config`, `input()`) crashing pytest on import — RESOLVED (moved to `_init()` guarded by `__name__`)
- `server/` directory incorrectly whitelisted — RESOLVED (only root `server.exe`/`server.bin` is whitelisted via WHITELIST_FILES, not the `server/` dir)

---

## Critical Bugs — RESOLVED

All previously identified critical bugs are now resolved in the codebase.

### GUI (Resolved in commit `75d1b6c`)
1. **Dashboard overlay URLs not displayed** — DOM element `#overlay-urls` added to `index.html:37`.
2. **Dead code in ConfigEditor.collect()** — Second `querySelectorAll('[data-path]')` loop removed.
3. **No dismiss button on restart-pending banner** — Dismiss button added to `index.html:24`, backed by `dismissRestartBanner()` in `app.js:588`.
4. **No WebSocket/SSE client in GUI** — `connectLogStream()` added in `app.js:2363`, connects to `/api/v1/events/stream` via `EventSource`. Log viewer displays "Connecting to log stream..." instead of placeholder.
5. **ShutdownNow race condition** — `_shutdownNowClicked = true` moved to success path after API call; UI re-enabled on error (catch block at `app.js:118-123`).

### Restart / Update (Resolved in this session)
11. **3-second sleep race in Windows restart** — Replaced `time.sleep(3)` with polling loop (`_wait_for_processes_stopped`, `_wait_for_process_started` in `start.py`). Configurable `_RESTART_POLL_INTERVAL` (0.5s) and `_RESTART_POLL_TIMEOUT` (10s).
12. **Manual restart after update** — Update now auto-restarts by spawning a new process and exiting the current one, instead of prompting "Press Enter to exit...".

---

## Architecture Issues

1. **EventBus not adopted by any plugin** — All 7 plugins poll the Main API for commands and push state. EventBus with SSE/WS exists (`core/api/eventbus.py`) but zero plugins publish through it directly. The Main API pipes events to SSE clients, but the EventBus subscriber pattern is unused by plugins themselves.

2. **Plugin dependency ordering not enforced** — `depends_on` declared in manifests but never checked by launcher or API. Plugins start in whatever order `start.py` iterates.

3. **Plugin system tightly coupled with main system** — ChannelPoints has config options inside `comment_commands` (main system config), Spotify integrates with cooldown/points systems. Plugins aren't fully self-contained — they reach into main config structures and depend on main system behavior. A proper rework should fully decouple plugins so they own their config and behavior independently.

4. **Hook system needs rework before testing** — The hook system is too tightly integrated into the main system. Hooks have no updater, no version info, no manifest. Dev experience is poor. Questions to resolve:
   - Should hooks be removed and replaced with direct plugin implementation?
   - Does the Hook API need more power (or less) for devs?
   - Is the Hook API up to date with the current system?
   - Without answers here, writing tests for hooks is premature — the interface will change.

7. **`core_hash` build cache is conservative** — Any change to any file in `src/core/**/*.py` invalidates all cached executables. Correct but wasteful for single-plugin changes.

---

## Testing Gaps

### No Coverage At All
| Module | Lines | Risk |
|--------|-------|------|
| `src/python/main.py` | ~1580 | **COVERED** — 38 tests for sanitize_filename, validate_like_triggers, get_safe_username, load_shell_actions, dup config detection |
| `src/python/start.py` | ~1112 | **PARTIAL** — 24 update lifecycle tests (signal files, restart polling, updater replacement); restart flow helpers not directly importable |
| `src/core/backup.py` | 265 | **COVERED** — 30 standalone tests for BackupManager |
| `src/core/hook_api.py` | 136 | HIGH — **BLOCKED:** Hook system needs rework first (see Architecture Issues #4). Test surface will change. |
| `src/core/hook_loader.py` | 132 | HIGH — **BLOCKED:** Hook system needs rework first (see Architecture Issues #4). Test surface will change. |
| `src/core/api/server.py` | 97 | MEDIUM — FastAPI app factory, CORS, static mounts |
| `src/core/api/routes/system.py` | 92 | **COVERED** — 8 tests for restart/shutdown/cancel/status endpoints |
| `src/core/api/routes/ws.py` | 71 | **COVERED** — 3 tests: event injection, ordering, disconnect cleanup |
| `src/core/api/routes/events.py` | 80 | MEDIUM — SSE stream (skipped), only POST tested |
| `src/core/api/updater.py` | 382 | MEDIUM — `_download_update()`, `install_update()` untested |
| `src/python/gui.py` | 85 | LOW — pywebview shell |
| `src/python/update.py` | ~500 | **COVERED** — 34 E2E tests (config migration, whitelist, version I/O, run_update orchestration, signals, platform paths) |
| `build.py` | 422 | MEDIUM — Build system, no tests |
| `create_plugin.py` | 151 | LOW — Plugin scaffolding |
| `upload.py` | 51 | LOW — Release tagging |
| `run.py` | 72 | LOW — Standalone API server launcher |
| `src/core/validator.py` | — | LOW — 36 tests exist, but line-parser coverage incomplete |
| `src/core/api/services/actions.py` | 421 | MEDIUM — ActionsService (parse/serialize) tested via API only |

### Other Gaps
- **GUI (frontend):** **COVERED** — 226 Vitest+JSDOM tests across `app.js` (2154 lines), `actions-editor.js` (636 lines), `index.html`
- **All 7 plugin implementations:** **BLOCKED** — Plugin system needs decoupling rework first (see Architecture Issues #3). Only manifest smoke tests exist; zero tests for actual plugin logic (command polling, state push, overlay registration).
- **All 3 event hooks** (`random.py`, `spotify.py`, `example_hook.py`): **BLOCKED** — Hook system needs rework first (see Architecture Issues #4). Hook loader tests exist but no functional tests.
- **Compiled binary update flow:** `update.py` has 34 E2E tests but no compiled binary test (update.exe → start.exe → restart)
- **SSE:** SSE stream receive tests cannot use TestClient (httpx blocking limitation); emit tests work via POST endpoint
- **Test isolation:** Session-scoped fixtures share state across tests; `_clear_registry` fixture not consistently applied

---

## v1.0.0 Release Blockers

### REQUIRED (Release Blockers)

1. **End-to-End Update Validation**
   - Update subsystem has 50+ unit/integration tests, but compiled `update.exe` → `start.exe` → restart flow has never been exercised across actual version boundaries.
   - Must verify: file signaling, API kill signal fallback, config whitelist preservation, rollback on interrupted update, Windows/Linux path correctness.
   - **Risk:** A broken update path on compiled build prevents users from ever receiving fixes and could corrupt installation.

2. **Documentation Rewrite (DO LAST AFTER ALL POINTS IN THIS DOCUMENT ARE FINISHED)**
   - `GUIDE.md` is stale: missing API server documentation (`/docs`, event bus, config API), event hooks system, config versioning, actions editor.
   - `CHANGELOG.md` test count stale (285 claimed vs 374 actual), `Unreleased` section empty, no v1.0.0 release date.
   - `README.md` is mostly current but should mention API server access and actions editor.
   - Must be done last after all code changes are frozen.

### IMPORTANT (Non-Blocking But Should Ship)

3. **ShutdownNow Race Condition (Critical Bug #5)**
   - User gets permanently stuck in "Shutting down..." state if `POST /api/v1/shutdown/now` returns an error.
   - Fix: move `_shutdownNowClicked = true` into the success path and re-enable UI on error. **RESOLVED**

5. **Update Check UI**
   - Backend endpoints exist (`GET /api/v1/updates/check`, `GET /api/v1/plugins/updates`). `start.py` already calls plugin updates at startup. Missing: any frontend element to display or trigger update checks.

6. **GUI Bugs**
   - `#1` Overlay URLs not displayed on dashboard
   - `#2` Dead loop in ConfigEditor.collect()
   - `#3` No dismiss button on restart-pending banner
   - `#4` No WebSocket/SSE client (ties into log viewer blocker)
   - `#5` ShutdownNow race condition

7. **Plugin Health Monitoring**
   - No health checking after plugin launch. No auto-restart on crash. Plugin marked `enabled: true` even when process is dead.

8. **Build System Hardening**
   - Hardcoded versions in `build.py` — no single source of truth
   - No CI build step on PRs (only on tags)
   - `upload.py` checked into git with stale version

---

## Post-v1.0.0 Ideas

### Security
- API authentication (API-Key) for `server_host: 0.0.0.0` deployments
- Spotify `client_secret` validation and encrypted storage
- Download integrity verification (checksummed artifacts)

### Architecture
- EventBus integration into plugin-to-plugin communication (plugins push events to EventBus instead of polling commands)
- Plugin sandboxing / resource limits

### GUI Enhancements
- Log viewer with live streaming, level filter, search, auto-scroll
- WebSocket/SSE client for real-time dashboard updates
- Spotify setup assistant (OAuth flow helper)
- Overlay preview + live theme editor
- Integrated Minecraft server console (RCON terminal)
- Mobile-responsive web dashboard variant
- "Check for Updates" button + notification badge

### Testing
- Stabilize SSE/WS integration tests (replace TestClient with httpx.AsyncClient or dedicated test helpers)
- Frontend/GUI integration tests (Playwright or similar)
- Plugin implementation tests (beyond manifest smoke tests)
- Lifecycle tests (start.py, main.py orchestration)
- BackupManager standalone tests
- build.py compilation tests
- End-to-end update test with mock GitHub server

### Build & Packaging
- Dedicated test build step in CI (on PRs, not just tags)
- Identify and strip dead modules from PyInstaller builds
- Automated release notes generation from CHANGELOG
- Single version source of truth (version file or constant)

### GUI installer
- GUI can run without the API server you can start all over the GUI (same as you start over start.exe)
- Installer.exe that run as a Setup Wizard so you can create shortcuts, add to startup, choose install location, etc.
- The Installer.exe should be optional, you can still run the portable version by downloading the zip and running start.exe or the GUI directly. But for users that want a more traditional installation experience or dont have much knowledge of PC they are more comfortable when they have a setup wizard and a desktop shortcut, the installer would be a nice addition.

### Plugin system
→ Moved to Architecture Issues #3 (Plugin system tightly coupled with main system). This is now a pre-release priority, not a post-v1.0.0 idea.

### Hook system
→ Moved to Architecture Issues #4 (Hook system needs rework before testing). This is now a pre-release priority, not a post-v1.0.0 idea.

---

## Recommended Next Steps

> **All 13 pre-release fixes are DONE.** The remaining work is architecture rework (blocks meaningful testing) and release validation.

### Next Step 1: End-to-End Update Validation 🔴 REQUIRED BLOCKER
The single highest-risk item. Update has 58 unit/integration tests but the compiled `update.exe → start.exe → restart` flow has never been exercised across actual version boundaries. If this breaks on release, users can never receive fixes and could corrupt their installation.
- Test with real compiled binaries across a simulated v0.x → v1.0.0 upgrade
- Verify: file signaling, API kill signal fallback, config whitelist preservation, rollback on interruption, Windows/Linux paths

### Next Step 2: Architecture Rework — Plugin Decoupling + Hook System Redesign
Testing hooks or plugins is premature — both need rework first (see Architecture Issues #3, #4).
- **Plugin decoupling:** Pull ChannelPoints config out of `comment_commands`, remove Spotify's hard dependency on main cooldown/points. Each plugin should own its config and behavior without reaching into main system internals.
- **Hook system redesign:** Decide whether hooks become standalone plugins (with manifests, updaters, versioning) or get absorbed into the plugin system entirely. Resolve the Hook API surface questions before any test effort.

### Next Step 3: Build System Hardening
- Single version source of truth (`core/version.py` — stop hardcoding in `build.py`)
- Add CI build step on PRs (not just tags)
- Clean up `upload.py` stale version

### Step 4 (continuous / whenever): Low-Risk Test Coverage
Independent of the rework above, these modules can be tested now:
- `src/core/api/updater.py` — `_download_update()`, `install_update()` untested (MEDIUM risk)
- `src/core/api/server.py` — FastAPI app factory, CORS, static mounts (MEDIUM)
- `build.py` — Build system, no tests (MEDIUM)
- `src/core/api/services/actions.py` — line-parser coverage incomplete

### Step 5 (LAST): Documentation Refresh
Only after all code changes are frozen.

---

*Last updated: 2026-05-31* (updated for v1.0.0-dev — 750 total tests: 524 Python + 226 GUI frontend; all Green)