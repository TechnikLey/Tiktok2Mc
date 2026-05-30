# TikTok2Mc — v1.0.0 Progress

## Overall Status

About 80% complete. All major systems are implemented. Remaining work is concentrated in GUI polish, end-to-end update validation, and documentation.

---

## Completed since v0.5.0

### Central API Server
- FastAPI backend on `127.0.0.1:29185` with 24+ REST routes at `/api/v1`
- Interactive API documentation at `/docs`
- Plugin management (register, list, enable, disable, discover, update check)
- Configuration CRUD with schema validation and automatic versioned backups
- Tool update check via GitHub Releases API
- Update coordination signals (file-based + API-based, dual mechanism)
- Event system: EventBus with Server-Sent Events (`/events/stream`) and WebSocket (`/ws`)
- CORS restricted to localhost by default
- Security warnings for default RCON password and network exposure

### Plugin System Overhaul
- Manifest-driven plugin discovery via `plugin.json` (name, version, entry point, ports, capabilities, schema)
- `PluginLauncher` replaces legacy self-registration — no more `register_plugin()` calls in plugin code
- All 7 plugins migrated to standalone, fully decoupled mode with no cross-plugin hard dependencies
- Plugin enable/disable is idempotent with signal-file lifecycle management
- All plugins default to `enabled: false` (opt-in)
- Plugin update checker with semver comparison, download, install, extract, rollback
- Plugin port registration and deduplication

### Plugin Config System
- Self-contained per-plugin `config.yaml` files alongside manifests
- `config_schema` in `plugin.json` declares field types, defaults, validation rules
- Schema types: string, integer, number, boolean, color, select, array (nested item_schema), object
- Full validation backend: required fields, min/max bounds, color regex, select options, array items
- `ruamel.yaml` round-trip I/O preserving comments, quotes, ordering, formatting
- Atomic writes with SHA-256-deduplicated, coalesced versioned backups
- Schema-driven default generation from field definitions

### Desktop GUI (entirely new in v1.0.0)
- `gui.py` — pywebview shell opening the SPA dashboard
- `templates/gui/index.html` — single-page dashboard with 4-card layout (System Status, Plugins, Actions, Configuration, Live Log)
- First-Run Setup Wizard — 3-step: TikTok username, RCON password with strength meter, review and save
- Plugin Manager — table showing name, version, port, status; enable/disable toggle per plugin; "Edit Config" button opens Plugin Config Editor
- Overlay URL Helper — OBS Browser Source URLs displayed inside Plugin Manager with copy-to-clipboard buttons
- Actions Editor (`actions-editor.js`) — visual tab (trigger table + detail panel + command editing), raw tab (textarea with live validation, diagnostics, save blocked on errors), Add Event modal (event selector or gift picker with search), script registry integration, gift database with image URLs
- Full `config.yaml` Editor — form-based with 5 categories (Connection, Minecraft, System, Appearance, Chat & Commands), IntersectionObserver scroll-spy, real-time search, validation, diff review modal before save, unknown key preservation
- Plugin Config Editor — schema-driven dynamic form renderer with category sidebar, 9+ field types, raw JSON fallback, plugin restart prompt after save
- Restart system — `POST /api/v1/restart` with dialog, pending banner, background daemon
- Shutdown system — `POST /api/v1/shutdown` with confirmation dialog, countdown, graceful termination

### Backup System
- `BackupManager` class with SHA-256 deduplication, time-based coalescing (60s window), retention (default 10 backups)
- Integrated into main config save, plugin config save, and plugin registry save paths
- Backups stored in `data/backups/` with category subdirectories

### Testing
- Test suite expanded from ~0 (no API tests) to 378 tests (374 passing, 4 skipped)
- Coverage added: API integration (config, plugins, plugin_config, events, updates), plugin registry, manifest validation, EventBus, plugin config system, schema validation, YAML round-trip, theme, overlay utils, actions validator (36 tests), smoke tests for all 8 plugin manifests
- CI workflow `test.yml` runs on every push/PR to `main`
- Test runtime ~7 seconds

### Legacy Cleanup
- `python/registry.py` deleted (legacy file-based plugin registry)
- `python/client.py` deleted (legacy API client)
- `python/gui.py` deleted (legacy GUI module)
- `python/plugin_updater.py` deleted (replaced by PluginUpdateChecker)
- All `register_plugin()` calls removed from plugin `main.py` files
- `ErrorResponse`, `WSMessage`, `ImportLegacyResponse`, `validate_config_dict`, `read_plugin_registry()` removed
- `--register-only` CLI flag removed
- `build.py` / `upload.py` version bumped to `v1.0.0`

### Documentation
- `README.md` rewritten for v1.0.0
- `GUIDE.md` rewritten with architecture, plugin system, API usage, actions/triggers, update system, troubleshooting
- `CHANGELOG.md` normalized with v1.0.0 section (Keep a Changelog format)
- `config.yaml` inline documentation improved

---

## In Progress

- **GUIDE.md** — needs updates covering the API server (`/docs`, event bus, config API), event hooks system, config versioning. Currently accurate for user-facing features but missing new v1.0.0 infrastructure documentation.

- **End-to-end update validation** — update subsystem has 50+ tests but compiled `update.exe` → `start.exe` → restart flow has never been tested with actual compiled binaries. Update runs at console startup before GUI.

---

## Missing / Blocking v1.0.0

### GUI Gaps
- **Log viewer** — dashboard has a placeholder reading "Log streaming not yet implemented." Backend EventBus with SSE and WebSocket endpoints exists but is not connected from the frontend.
- **Actions editor** — visual editor is implemented (`templates/gui/actions-editor.js`) with both Visual and Raw tabs, gift picker, script registry integration, and live validation. Backend routes (GET/PUT `/actions`, `/actions/raw`, `/gifts`, `/actions/scripts`) all exist and are functional.
- **Update check UI** — backend endpoints `GET /api/v1/updates/check` and `GET /api/v1/plugins/updates` exist, but the frontend never calls them. No "Check for Updates" button, no update notification banner.
- **Overlay URLs not on main dashboard** — `renderOverlayUrls()` targets a non-existent element `#overlay-urls`. URLs only appear inside the Plugin Manager popup.
- **No WebSocket/SSE client** — backend streaming endpoints are fully functional but the frontend never connects to them. All status updates rely on polling.

### Plugin System Gaps
- **No process health monitoring** — plugins are launched as subprocesses but never checked for liveness. A crashed plugin remains marked as `enabled: true` in the registry.
- **No auto-restart on crash** — if a plugin process dies, there is no watchdog to restart it.
- **Registry/filesystem state mismatch** — `/plugins/discover` is read-only. Plugins deleted from disk leave stale registry entries. New plugin directories are not auto-registered until restart.
- **Port conflicts not detected** — no validation when two plugins declare the same port.
- **Non-atomic enable/disable** — registry update and signal file write are separate operations; failure mid-way leaves inconsistent state.

### Build & Release
- **End-to-end update flow untested on compiled builds** — all update tests mock HTTP and run on Python source. No CI step compiles and exercises `update.exe` against a real version boundary.
- **Hardcoded versions** — `TOOL_VERSION` and `UPDATER_VERSION` hardcoded in `build.py` with no single source of truth.
- **`upload.py` stale in git** — checked in with hardcoded `v1.0.0`.
- **No CI build step on PRs** — build only runs on tags. PRs can break compilation without detection.

### Testing Gaps (Untested Modules)
- `src/python/main.py` (~1614 lines) — 0 tests
- `src/python/start.py` (~919 lines) — 0 tests
- `src/core/backup.py` (265 lines) — 0 standalone tests (only indirect via registry)
- `src/core/hook_api.py` / `hook_loader.py` — 0 tests
- `src/core/api/routes/system.py` (restart/shutdown) — 0 tests
- `src/core/api/routes/ws.py` (WebSocket) — all tests skipped (httpx limitation)
- `src/core/api/updater.py` (download/install logic) — untested
- `templates/gui/` (2022 lines of JS + HTML + CSS) — 0 tests
- All 7 plugin implementations — 0 tests beyond manifest smoke tests
- `build.py` / `create_plugin.py` / `upload.py` — 0 tests

### Documentation
- `GUIDE.md` needs updates for: API server documentation, event hooks, config versioning
- `CHANGELOG.md` test count stale (285 claimed vs 369 actual), `Unreleased` section empty

---

*Last updated: 2026-05-29*