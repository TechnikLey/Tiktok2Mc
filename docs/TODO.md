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
- Enable/disable endpoints: `POST /api/v1/plugins/{name}/enable|disable`
- Discovery endpoint: `GET /api/v1/plugins/discover` (read-only, no side effects)
- Health polling with 10 s timeout before plugin load
- Fallback mode: continues without plugins if API fails to start
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

### Backup System
- `BackupManager` class (`core/backup.py`) with SHA-256 dedup, retention, coalescing, category management
- Versioned backup files (`*.v<N>.bak`)
- Integrated into registry, plugin config, config.yaml, and actions.mca save paths

### Plugin Decoupling
- Timer, DeathCounter, WinCounter, OverlayText, LikeGoal, Spotify, ChannelPoints — all standalone
- Each plugin exposes its own REST API; no cross-plugin hard dependencies
- Timer: `auto_win: false`, `pause_on_death: false`
- WinCounter: `decrement_on_death: false`
- All plugins default to `enabled: false` (opt-in)

### GUI — Implemented
- `src/python/gui.py` — pywebview shell that opens the dashboard served by the API server
- `templates/gui/index.html` — SPA dashboard with system status, plugin list, config summary, actions editor
- API server mounts `/gui` static files (dev + release layouts supported)
- `start.py` launches `gui.exe` when `gui.enabled: true`
- **First-Run Setup Wizard** — 3 steps: TikTok username, RCON password (with strength meter + validation), review & save. Auto-triggers when RCON password is empty.
- **Plugin Manager** — Enable/disable toggles in dashboard, "Edit Config" button per plugin
- **Overlay URL Helper** — Shows OBS Browser Source URLs for active plugins with copy-to-clipboard buttons (inside Plugin Manager)
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
- **Actions Editor** — Full visual editor with:
  - Visual tab: table of triggers, detail panel with inline command editing (vanilla, rcon, script, overlay, named_overlay), add/remove/delete triggers
  - Add Event modal: event type selector (follow/join/comment/likes/like_2/share) or gift picker with search-by-name/ID
  - Script dropdown with search and lazy-loaded script registry
  - Raw tab: textarea with live validation (debounced 400ms), diagnostics panel, save blocked on errors
  - Gift database integration with image URLs and coin cost sorting

### Testing
- **374 tests: 370 passed, 4 skipped** (SSE/WS streaming due to `TestClient` / `httpx` limitations)
- CI workflow `test.yml` on push/PR to `main` (~7s runtime)
- Coverage: API integration, plugin discovery, manifest validation, updater logic, signal handling, config CRUD, event validation, plugin config system, schema validation, YAML round-trip preservation, theme, overlay utils, actions validator (36 tests), smoke tests for all 8 plugin manifests, **hook system (3 event hooks: random, spotify, example_hook)**

### Legacy Cleanup
- `python/registry.py`, `client.py` legacy fallback, `--register-only` CLI flag removed
- `gui.py` (legacy) removed; `plugin_updater.py` dead code removed
- `build.py` / `upload.py` version bumped to `v1.0.0`
- Old self-registration `register_plugin()` calls removed from all plugin `main.py` files

### Documentation
- `README.md` rewritten for v1.0.0
- `GUIDE.md` rewritten with architecture, plugin system, API usage, actions/triggers, update system, troubleshooting
- `CHANGELOG.md` normalized with v1.0.0 section (Keep a Changelog format)
- `config.yaml` inline documentation improved

### Fixed Bugs
- `commands_config` default type mismatch (`[]` → `{}` in `defaults/config.yaml`) — RESOLVED
- Config editor scroll-spy and sidebar order alignment — RESOLVED
- Plugin settings removed from main config editor (moved to plugin-specific editor) — RESOLVED
- Config save restart prompts, plugin UX, release path resolution — RESOLVED
- Shutdown cancel signal race: now checked directly in countdown loop (1s) instead of file watcher (5s) — RESOLVED
- Shutdown countdown UI race: deterministic termination, immediate UI feedback — RESOLVED

---

## In Progress

- **GUIDE.md rewrite** — Missing: API server docs (`/docs`, event bus, config API), event hooks system (`src/event_hooks/`), config versioning, actions editor. Currently covers user-facing features adequately but omits new v1.0.0 infrastructure.
- **End-to-end update validation** — Update subsystem has 50+ tests but compiled `update.exe` → `start.exe` → restart flow never exercised across actual version boundaries.

---

## Critical Bugs

### GUI
1. **Dashboard overlay URLs not displayed** — `renderOverlayUrls()` in `app.js:227-243` looks for `document.getElementById('overlay-urls')` which does not exist in `index.html`. The overlay URL container `plugin-manager-urls` exists inside the plugin manager modal, so URLs display there but never on the main dashboard.

2. **Dead code in ConfigEditor.collect()** — `app.js:1346-1376` calls `this.content.querySelectorAll('[data-path]')` twice sequentially. The second loop body contains only comments and a no-op conditional. Dead code artifact that wastes a DOM query.

3. **No dismiss button on restart-pending banner** — `_restartPending` flag only clears on actual restart. No "Dismiss" button on the banner (`index.html:19-24`). User must restart to clear visual state.

4. **No WebSocket/SSE client in GUI** — Backend has fully functional EventBus with SSE (`/events/stream`) and WebSocket (`/ws`), plus a `log()` function in `app.js:170-177`. But `app.js` never connects to any streaming endpoint. The log viewer div explicitly says "Log streaming not yet implemented" (`index.html:50`). This means:
   - No real-time log streaming despite both backend and client-side scaffolding existing
   - No real-time status updates (dashboard resorts to 10s polling via `loadHealth()`)
   - Plugin state changes are not pushed

### Plugin System
5. **Registry ↔ filesystem state mismatch** — `/plugins/discover` is read-only. If a plugin directory is deleted from disk, registry still has stale metadata. If a plugin directory appears, it is not auto-registered until restart.

6. **Enable/disable ↔ process state gap** — Enable/disable writes signal files; `start.py` polls async. No confirmation the plugin process actually started or stopped. No heartbeat/health check — registry says `enabled: true` even if the process crashed.

7. **Port staleness** — `PluginRegistration.port` comes from manifest; actual port in `config.yaml` can diverge if user edits config directly (not via API). No cross-validation.

8. **Non-atomic enable/disable** — Registry update and signal file write are separate operations. If signal write fails after registry update, state is inconsistent.

9. **Dead plugin entries** — `DELETE /plugins/{name}` unregisters from registry but does not stop running process or clean up files.

### Restart / Update
10. **3-second sleep race in Windows restart** — `start.py:935` sleeps 3s then checks if new process is alive. Under load, 3s may be insufficient; on fast systems, the check passes but the process could crash immediately after.

11. **Manual restart after update** — Update does not auto-restart. User presses Enter, then re-launches `start.exe` manually.

---

## Architecture Issues

1. **EventBus not adopted by any plugin** — All 8 plugins run independent Flask HTTP servers on their own ports. EventBus with SSE/WS exists (`core/api/eventbus.py`) but zero plugins use it. This defeats the purpose of the pub/sub infrastructure. Plugins communicate via HTTP calls to each other's independent servers, not through the bus.

2. **Plugin dependency ordering not enforced** — `depends_on` declared in manifests but never checked by launcher or API. Plugins start in whatever order `start.py` iterates.

3. **No plugin process health monitoring** — `start.py` launches plugins as subprocesses but never verifies they started successfully or monitors them at runtime. A crashed plugin stays marked as enabled.

4. **7 independent plugin HTTP servers** — Port proliferation (29186, 29189, 29190, 29191, 29193, 29194, 29195). No central reverse proxy or port manager. Risk of port collisions — no detection during registration.

5. **Config schema validation not enforced on load** — `load_plugin_config()` applies defaults but does not validate existing values against schema. Validation only runs on explicit API `PUT`.

6. **Single config version source of truth missing** — `build.py` hardcodes `TOOL_VERSION = "v1.0.0"` and `UPDATER_VERSION = "v1.4.0"`. No single version source of truth. `upload.py` checked into git with stale hardcoded version.

7. **`core_hash` build cache is conservative** — Any change to any file in `src/core/**/*.py` invalidates all cached executables. Correct but wasteful for single-plugin changes.

---

## Testing Gaps

### No Coverage At All
| Module | Lines | Risk |
|--------|-------|------|
| `src/python/main.py` | ~1614 | **CRITICAL** — TikTok bridge core, RCON, webhooks, event dispatch |
| `src/python/start.py` | ~1016 | **CRITICAL** — Process orchestrator, lifecycle management |
| `src/core/backup.py` | 265 | MEDIUM — BackupManager (only indirect test via registry) |
| `src/core/hook_api.py` | 136 | HIGH — Runtime hook API (rcon_enqueue, enqueue_trigger, loop detection) |
| `src/core/hook_loader.py` | 132 | HIGH — AST-based import validation, dynamic module loading |
| `src/core/api/server.py` | 97 | MEDIUM — FastAPI app factory, CORS, static mounts |
| `src/core/api/routes/system.py` | 92 | **HIGH** — restart/shutdown signal endpoints, zero tests |
| `src/core/api/routes/ws.py` | 71 | HIGH — WebSocket (all tests skipped) |
| `src/core/api/routes/events.py` | 80 | MEDIUM — SSE stream (skipped), only POST tested |
| `src/core/api/updater.py` | 382 | MEDIUM — `_download_update()`, `install_update()` untested |
| `src/python/gui.py` | 85 | LOW — pywebview shell |
| `src/python/update.py` | ~500 | **HIGH** — Self-updater compiled binary, no tests |
| `build.py` | 422 | MEDIUM — Build system, no tests |
| `create_plugin.py` | 151 | LOW — Plugin scaffolding |
| `upload.py` | 51 | LOW — Release tagging |
| `run.py` | 72 | LOW — Standalone API server launcher |
| `src/core/validator.py` | — | LOW — 36 tests exist, but line-parser coverage incomplete |
| `src/core/api/services/actions.py` | 421 | MEDIUM — ActionsService (parse/serialize) tested via API only |

### Other Gaps
- **GUI (frontend):** Zero tests across `index.html`, `app.js` (2154 lines), `style.css`, `actions-editor.js` (636 lines)
- **All 8 plugin implementations:** Only manifest smoke tests exist; zero tests for actual plugin logic
- **All 3 event hooks** (`random.py`, `spotify.py`, `example_hook.py`): Hook loader tests exist but no functional tests
- **End-to-end update flow:** No compiled binary test (update.exe → start.exe → restart)
- **SSE/WebSocket:** 4 tests permanently skipped (httpx/TestClient limitation)
- **Test isolation:** Session-scoped fixtures share state across tests; `_clear_registry` fixture not consistently applied

---

## v1.0.0 Release Blockers

### REQUIRED (Release Blockers)

1. **End-to-End Update Validation**
   - Update subsystem has 50+ unit/integration tests, but compiled `update.exe` → `start.exe` → restart flow has never been exercised across actual version boundaries.
   - Must verify: file signaling, API kill signal fallback, config whitelist preservation, rollback on interrupted update, Windows/Linux path correctness.
   - **Risk:** A broken update path on compiled build prevents users from ever receiving fixes and could corrupt installation.

2. **Documentation Rewrite (DO LAST)**
   - `GUIDE.md` is stale: missing API server documentation (`/docs`, event bus, config API), event hooks system, config versioning, actions editor.
   - `CHANGELOG.md` test count stale (285 claimed vs 374 actual), `Unreleased` section empty, no v1.0.0 release date.
   - `README.md` is mostly current but should mention API server access and actions editor.
   - Must be done last after all code changes are frozen.

3. **Log Viewer**
   - Placeholder text exists (`index.html:50`). Backend EventBus provides SSE (`/events/stream`) and WebSocket (`/ws`) — both fully functional. GUI has log infrastructure (`log()` function, log div). Missing: frontend connection to backend streaming endpoint.
   - Without this, GUI-only users who hide the console have no way to see warnings or errors.

### IMPORTANT (Non-Blocking But Should Ship)

4. **Update Check UI**
   - Backend endpoints exist (`GET /api/v1/updates/check`, `GET /api/v1/plugins/updates`). `start.py` already calls plugin updates at startup. Missing: any frontend element to display or trigger update checks.

5. **GUI Bugs (see Critical Bugs section)**
   - `#1` Overlay URLs not displayed on dashboard (workaround: they show in Plugin Manager)
   - `#2` Dead loop in ConfigEditor.collect()
   - `#3` No dismiss button on restart-pending banner
   - `#4` No WebSocket/SSE client (ties into log viewer blocker)

6. **Plugin Health Monitoring**
   - No health checking after plugin launch. No auto-restart on crash. Plugin marked `enabled: true` even when process is dead.

7. **Build System Hardening**
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
- Port consolidation: reverse-proxy plugin HTTP servers through main API or reduce to fewer ports
- Centralized port manager to prevent collisions
- EventBus integration into plugin-to-plugin communication (replace independent Flask servers)
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
- Actions editor frontend tests

### Build & Packaging
- Dedicated test build step in CI (on PRs, not just tags)
- Identify and strip dead modules from PyInstaller builds
- Automated release notes generation from CHANGELOG
- Single version source of truth (version file or constant)

---

## Recommended Next Steps

Ordered by: (1) highest release impact, (2) lowest implementation risk, (3) greatest stability improvement.

### 1. Add dismiss button to restart-pending banner
- **Why next:** Trivial 2-line fix. Users cannot clear the banner without restarting. Low risk, high UX impact.
- **Complexity:** 1 (very simple)
- **Blocks v1.0.0?** No, but should ship.

### 2. Add `#overlay-urls` container to dashboard
- **Why next:** ~5 minute fix. Add the missing DOM element referenced by `renderOverlayUrls()`. Low risk, visible improvement.
- **Complexity:** 1
- **Blocks v1.0.0?** No.

### 3. Remove dead code loop in ConfigEditor.collect()
- **Why next:** 5 minute cleanup. The second `querySelectorAll('[data-path]')` does nothing but waste CPU. Easy win.
- **Complexity:** 1
- **Blocks v1.0.0?** No.

### 4. Connect log viewer to SSE endpoint
- **Why next:** Highest user impact among remaining blockers. GUI-only users have no way to see errors without showing the console. Backend SSE endpoint already exists and works. Frontend needs ~50 lines of JavaScript to connect and display log entries.
- **Complexity:** 3 (moderate)
- **Blocks v1.0.0?** Yes. Without this, users who hide the console are blind to errors.

### 5. Update CHANGELOG.md test count and add unreleased section
- **Why next:** Quick documentation fix. Test count is stale (285 → 374). Missing unreleased section for recent actions editor, hook system, and shutdown fixes.
- **Complexity:** 1
- **Blocks v1.0.0?** Yes — release docs must be accurate.

### 6. End-to-end update test with compiled binaries
- **Why next:** Highest risk item. A broken update permanently damages user installations. Requires creating a mock release on GitHub or locally and running `update.exe` → `start.exe` → restart through a full cycle.
- **Complexity:** 5 (complex — requires build + mock server)
- **Blocks v1.0.0?** Yes. Must be done before release.

### 7. Add update-check UI to dashboard
- **Why next:** Backend endpoints exist and work. Frontend just needs a "Check Updates" button that calls `GET /api/v1/updates/check` and displays results. ~1 hour of work.
- **Complexity:** 2
- **Blocks v1.0.0?** Important but not blocking.

### 8. Fix registry/filesystem mismatch with filesystem watcher
- **Why next:** Plugin discovery is currently read-only. A user who manually deletes a plugin directory will have stale registry entries until restart. A simple `inotify`/`ReadDirectoryChangesW` watcher on the plugins directory could auto-sync.
- **Complexity:** 4 (moderate-complex)
- **Blocks v1.0.0?** Important for plugin system integrity.

### 9. Plugin health monitoring
- **Why next:** Currently no way to detect crashed plugins. Add a watchdog thread that pings plugin health endpoints every N seconds and updates registry state on failure.
- **Complexity:** 4 (moderate-complex)
- **Blocks v1.0.0?** Important for reliability.

### 10. Single version source of truth
- **Why next:** `build.py` hardcodes versions. Extract to `core/version.py` or `version.txt` that all modules read. Prevents version drift between build, API, and updater.
- **Complexity:** 2
- **Blocks v1.0.0?** Important for release engineering.

---

*Last updated: 2026-05-30*