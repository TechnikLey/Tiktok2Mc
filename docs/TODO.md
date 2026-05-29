# TikTok2Mc — Release TODO (v1.0.0)

> **Goal:** Ship a stable v1.0.0 release with a working graphical user interface, a validated update path, and a polished out-of-the-box experience.
> v1.0.0 is intentionally incompatible with v0.x.

---

## ✅ Completed (Current State)

### Core Bridge
- TikTok Live connection (gifts, follows, likes, shares, comments, joins)
- Minecraft command execution via RCON and datapacks
- Action parser (`data/actions.mca`) with vanilla / RCON / script / overlay support
- Webhook server for MinecraftServerAPI (death/respawn detection)
- Comment commands with role-based permissions, cooldowns, user_cooldown, and channel-points integration
- `random_triggers` filter for `$random` action eligibility

### API & Plugin System
- Central FastAPI server (`127.0.0.1:29185`) with 15+ consistent REST routes
- `API_VERSION` centrally defined; `DEFAULT_PORT` unified across codebase
- Deterministic plugin discovery via `plugin.json` manifests (8 plugins, 1 test plugin excluded from release)
- `PluginLauncher` API-only (no legacy registry fallback)
- Enable/disable endpoints: `POST /api/v1/plugins/{name}/enable|disable`
- Discovery endpoint: `GET /api/v1/plugins/discover` (read-only, no side effects)
- Health polling with 10 s timeout before plugin load
- Fallback mode: continues without plugins if API fails to start
- EventBus in-memory publish/subscribe (`core/api/eventbus.py`) with SSE (`/events/stream`) and WebSocket (`/ws`) endpoints
- Plugin-local configuration API: `GET|PUT /api/v1/plugins/{name}/config`, `GET /api/v1/plugins/{name}/config/schema`

### Plugin Config Architecture
- Self-contained per-plugin `config.yaml` files alongside manifests
- `config_schema` declarations in `plugin.json` drives defaults generation, runtime validation, and future GUI rendering
- Schema types supported: `string`, `integer`, `number`, `boolean`, `color`, `select`, `array` (with nested `item_schema`), `object`
- Full validation backend: required fields, min/max bounds, regex color validation, select options, array item validation
- `ruamel.yaml` round-trip system (`core/yaml_utils.py`) preserving comments, quotes, ordering, and formatting on save
- Atomic writes with versioned backups (`*.v1.bak`)

### Update System
- `PluginUpdateChecker` with semver comparison
- `GET /api/v1/plugins/updates` endpoint
- Tool update check: `GET /api/v1/updates/check` (GitHub Releases API)
- Dual signaling (file-based `update_signal.tmp` + API `/updater/signal`)
- `update.py` and `start.py` coordinated signal handling

### Security & Configuration
- CORS restricted to local origins
- RCON default password changed to empty string — setup wizard enforces secure password
- Semantic config versioning (`config_version: 1.0`)
- Config normalization, schema validation, and automatic backups
- All plugins default to `enabled: false` (opt-in)

### Plugin Decoupling
- Timer, DeathCounter, WinCounter, OverlayText, LikeGoal, Spotify, ChannelPoints — all standalone
- Each plugin exposes its own REST API; no cross-plugin hard dependencies
- Timer: `auto_win: false`, `pause_on_death: false`
- WinCounter: `decrement_on_death: false`

### GUI — Implemented
- `src/python/gui.py` — pywebview shell that opens the dashboard served by the API server
- `templates/gui/index.html` — SPA dashboard with system status, plugin list, config summary
- API server mounts `/gui` static files (dev + release layouts supported)
- `start.py` launches `gui.exe` when `gui.enabled: true`
- **First-Run Setup Wizard** — 3 steps: TikTok username, RCON password (with strength meter + validation), review & save. Auto-triggers when RCON password is empty.
- **Plugin Manager** — Enable/disable toggles in dashboard that persist to `config.yaml`
- **Overlay URL Helper** — Shows OBS Browser Source URLs for active plugins with copy-to-clipboard buttons
- **Restart System** — `POST /api/v1/restart` writes signal; `start.py` uses a background daemon thread that calls `os._exit(0)` to guarantee clean process termination before the new instance starts
- **Full `config.yaml` Editor** — Form-based editor supporting:
  - Section-based navigation with categories (Connection, Minecraft, Streaming & Overlays, Chat & Commands, Integrations, Appearance, System)
  - IntersectionObserver scroll-spy for active section highlighting
  - Real-time search across setting names, descriptions, and field help text
  - Java RAM settings (`xms`/`xmx` with pattern validation)
  - Like goal triggers (add/remove/edit interval table with `id`, `every`, `function`, `payload`, `enabled`)
  - Comment commands (full group editor: prefix, handler, mode, roles, cooldown, user_cooldown, trigger_comment_event)
  - Command overrides (`commands_config`) with dynamic add/remove for points_cost, cooldown, user_cooldown, conditional, url, handler, roles
  - Theme color editor (hex pickers with synced text inputs for every plugin)
  - Auto-update, shutdown, console visibility settings
  - Validation for required fields, patterns, min/max bounds
  - Review Changes modal showing diff before save
  - Unknown settings preservation with raw YAML fallback
  - Toast notifications for success/error feedback

### Testing & CI
- **363 tests passing, 4 skipped** (SSE/WS stability due to `TestClient` / `httpx` limitations)
- CI workflow `test.yml` on push/PR to `main`
- Coverage: API integration, plugin discovery, manifest validation, updater logic, signal handling, config CRUD, event validation, **plugin config system**, **schema validation**, **YAML round-trip preservation**, **comment command overrides**

### Legacy Cleanup
- `python/registry.py`, `client.py` legacy fallback, `--register-only` CLI flag removed
- `gui.py` (legacy) removed; `plugin_updater.py` dead code removed
- `build.py` / `upload.py` version bumped to `v1.0.0`

### Documentation
- `README.md` rewritten for v1.0.0
- `GUIDE.md` rewritten with architecture, plugin system, API usage, actions/triggers, update system, troubleshooting
- `CHANGELOG.md` normalized with v1.0.0 section (Keep a Changelog format)
- `config.yaml` inline documentation improved

---

## v1.0.0 — REQUIRED (RELEASE BLOCKERS)

> **These must be resolved before v1.0.0 can be tagged. No exceptions.**
> **Execution order matters:** Work on blockers in the order listed below. Do **NOT** jump to the documentation rewrite until all code, GUI, and validation tasks are frozen.

### 1. End-to-End Update Validation
> **Status: IMPLEMENTED BUT NOT VALIDATED IN A REAL BUILD.**
>
> The update subsystem has 56+ unit/integration tests, but the compiled `update.exe` → `start.exe` → restart flow has never been exercised across actual version boundaries.

- [ ] **RELEASE BLOCKER** — End-to-end update test: compiled v1.0.0 → v1.0.1
  - Verify `update.exe` performs file-based signaling (`update_signal.tmp`) correctly
  - Verify API-based kill signal fallback (`GET/PUT/DELETE /api/v1/updater/signal`) works
  - Verify config whitelist preserves user settings across update
  - Verify rollback / recovery behavior on interrupted update
  - Verify Windows and Linux paths (tmux/screen session cleanup)

### 2. Complete Documentation Rewrite
> **Status: OUTDATED. Previous rewrites exist but are stale due to massive architecture changes (plugin config system, schema validation, ruamel.yaml round-trip, GUI expansion, EventBus, per-plugin configs).**
>
> **Critical rule:** This blocker MUST be tackled **last**, after all other code changes, GUI additions, and non-blocking items below are completed and frozen. Rewriting docs while code is still moving guarantees immediate stale docs on release day.

- [ ] **RELEASE BLOCKER (DO LAST)** — Rewrite `GUIDE.md` from scratch
  - Cover the new plugin config architecture (per-plugin `config.yaml`, `config_schema`, manifest system)
  - Document the schema validation and YAML round-trip behavior
  - Update API usage examples to match current 15+ route surface (plugin config endpoints, EventBus, SSE/WebSocket)
  - Replace old architecture diagrams/descriptions with current decoupled plugin model
  - Add troubleshooting for new GUI flows (wizard, config editor, plugin enable/disable)
- [ ] **RELEASE BLOCKER (DO LAST)** — Rewrite `README.md` from scratch
  - Quick-start must reflect empty default RCON password + wizard enforcement (remove stale `ABC1234` references)
  - Include plugin config editor, log viewer, and actions editor status honestly ("edit files by hand" where GUI is missing)
  - Update OBS source URLs, port list, and feature matrix
  - Add minimum system requirements and migration notice for v0.x users
- [ ] **RELEASE BLOCKER (DO LAST)** — Rewrite / create dev-books and internal architecture docs
  - `docs/` should contain accurate developer onboarding for the new schema system, `ruamel.yaml` conventions, and plugin manifest format
  - Document the build pipeline (`build.py` parallel compilation, core dependency hashing, PyInstaller cache logic)
  - Remove or archive any docs referencing legacy registry, `python/registry.py`, or old `client.py` flows

---

## v1.0.0 — IMPORTANT (NON-BLOCKING BUT REQUIRED)

> **These must be completed before release, but they do not block tagging on their own if the blocker above is resolved. They represent the remaining gaps between "functional" and "polished."**

### GUI — Remaining Components
> **Rationale:** The main config editor was the primary GUI blocker and is now complete. Users can edit `config.yaml` fully through the GUI. The items below are important missing pieces, but manual alternatives exist (edit files by hand or view logs in `logs/`). They are prioritized for the "polished out-of-the-box experience" goal, yet they do not make the tool unstable.

- [ ] **High** — Plugin Config Editor GUI frontend
  - The API endpoints (`GET|PUT /plugins/{name}/config`, `GET /plugins/{name}/config/schema`) and backend validation are complete.
  - Missing: a GUI panel that fetches a plugin's `config_schema`, renders auto-generated forms, validates input, and saves to the plugin's local `config.yaml`.
  - Required for: Spotify `client_id`/`client_secret`, Timer `start_time`/`auto_win`, LikeGoal `initial_goal`, and all other plugin-specific settings that are NOT in the main `config.yaml`.

- [ ] **High** — Real-time log viewer
  - Missing: backend endpoint to tail/read `logs/` files (or EventBus integration publishing log records) and a GUI frontend to display, filter by level (INFO/WARNING/ERROR), search, and auto-scroll.
  - The GUI dashboard currently shows: "Log streaming not yet implemented."

- [ ] **High** — `data/actions.mca` editor with syntax validation
  - Missing: backend endpoint to read/write/validate `actions.mca` content, and a GUI frontend.
  - The validation engine (`core/validator.py`) is complete and well-tested; it only needs to be wired into an API endpoint and a visual editor (textarea with line numbers, real-time validation, visual trigger list).

### Data Consistency
- [ ] **High** — Fix `comment_commands.groups[].commands_config` default type mismatch
  - `defaults/config.yaml` sets `commands_config: []` (empty list) for the first example group, but the GUI and backend expect a dict `{}`.
  - The GUI currently coerces arrays to `{}` as a workaround. The default template should use `{}` for consistency, and any migration logic should handle legacy `[]` values.

### User Experience Polish
- [ ] **Medium** — Console/log visibility for GUI-only users
  - `console.log_level` levels exist (0–5), but without a working log viewer in the GUI, users who hide the terminal have no way to see warnings or errors.
  - Resolution is tied to the log viewer item above.

### Build & Deployment Finalization
- [ ] **High** — Migration notice for v0.x users (config/plugins are incompatible)
- [ ] **High** — Document minimum system requirements in release notes
- [ ] **Medium** — Document manual rollback procedure
- [ ] **Medium** — Final troubleshooting expansion (common first-start errors)

### API & Plugin Hardening
- [ ] **Medium** — Final consistency review of all REST routes (error messages, status codes, pagination)
- [ ] **Medium** — Validate graceful degradation when individual plugin processes crash
- [ ] **Low** — Verify CORS behavior is correct for all local-origin scenarios

### Documentation Prep (Pre-Rewrite)
> These are lightweight data-gathering tasks that make the final documentation rewrite faster. Do **not** write final prose yet — code is still moving.

- [ ] **Medium** — Audit `README.md` for stale references (e.g. `rcon.password: ABC1234`, old plugin counts, missing ports)
- [ ] **Low** — Collect log file locations and safe cleanup procedures (ready to paste into final docs)
- [ ] **Low** — Draft migration notice bullet points for v0.x users (config/plugins incompatible, manual steps)

---

## POST v1.0.0

> **Explicitly deferred. Do not work on these until v1.0.0 is shipped.**

### Security
- [ ] **Medium** — API authentication (API-Key) for deployments using `server_host: 0.0.0.0`
- [ ] **Low** — Spotify `client_secret` validation and encrypted storage

### Architecture & Performance
- [ ] **Medium** — Port consolidation: reduce 7+ plugin ports to fewer endpoints or reverse-proxy through API
- [ ] **Medium** — EventBus integration into plugin-to-plugin communication (bus and SSE/WS endpoints exist; plugins still use independent HTTP servers)
- [ ] **Medium** — Centralized port manager to prevent collisions

### Testing
- [ ] **Low** — Stabilize SSE/WS integration tests (currently 4 skipped due to `TestClient` / `httpx` limitations)
- [ ] **Low** — Add frontend/GUI integration tests (currently none; all tests are backend Python)

### GUI Enhancements (v1.1.0+)
- [ ] **Low** — Plugin config GUI auto-rendering from `config_schema` (generic form generator so new plugins get editors for free)
- [ ] **Low** — Spotify setup assistant (OAuth flow helper)
- [ ] **Low** — Overlay preview + live theme editor
- [ ] **Low** — Integrated Minecraft server console (RCON terminal)
- [ ] **Low** — Mobile-responsive web dashboard variant

### Build & Packaging
- [ ] **Low** — Identify and strip dead modules from PyInstaller builds
- [ ] **Low** — Automated release notes generation from CHANGELOG

---

## Summary of Changes in This Rewrite

### Major Changes
1. **GUI status completely re-evaluated.** The full `config.yaml` editor is no longer a blocker — it is implemented and tested. The GUI section now accurately lists what is done (wizard, plugin manager, overlay URLs, restart, config editor) and what remains (plugin config editor, log viewer, actions editor).
2. **Test count corrected:** 363 passed (was 285 in the old TODO). The 4 skipped SSE/WS tests remain accurately noted.
3. **Plugin Config System recognized as complete.** The backend (schema parsing, validation, ruamel.yaml round-trip, API routes) is fully implemented and covered by tests. What is missing is only the GUI frontend for it.
4. **Actions editor reclassified.** The validation engine (`core/validator.py`) is complete and well-tested. The missing piece is the API endpoint and GUI integration, not the engine itself.
5. **Release-critical scope redefined.** Two blockers remain: (a) unvalidated compiled update flow (must be fixed first) and (b) complete documentation rewrite (must be done last). The remaining GUI gaps are important for polish but do not compromise stability.

### Removed as Obsolete
- "Full `config.yaml` editor" as a release blocker → moved to **Completed**.
- "285 tests passing" → corrected to **363 tests passing**.
- "12 consistent REST routes" → removed the hard count; the API has grown to 15+ routes including plugin config and event endpoints.
- "Automated verification that `version.txt` matches `TOOL_VERSION` in `build.py`" → removed; `build.py` generates `version.txt` dynamically at build time, so this verification is obsolete.
- Old "Documentation Finalization" (minor final-pass tasks) → replaced by **Complete Documentation Rewrite** release blocker. A light final pass is insufficient because the docs are structurally stale.

### Added Based on Code Analysis
- **Complete Documentation Rewrite** elevated to release blocker (user request). GUIDE.md, README.md, and dev-books are stale after massive architecture changes.
- **Plugin Config Editor GUI frontend** (discovered gap: API exists, no frontend).
- **Real-time log viewer** (discovered gap: placeholder text exists in GUI, no backend or frontend implementation).
- **`data/actions.mca` editor** (already listed, but clarified that `core/validator.py` is done; missing piece is API/GUI wiring).
- **`ruamel.yaml` round-trip preservation** (completed architecture not previously mentioned).
- **Self-contained per-plugin config files with schemas** (completed architecture not previously mentioned).
- **`commands_config` default type mismatch bug** (discovered in `defaults/config.yaml` vs. GUI expectation).
- **Frontend/GUI integration tests** (discovered gap: zero frontend tests exist).

### What Is Now Considered Release-Critical
Two items are release-blocking, with a strict execution order:

1. **End-to-End Update Validation** — a broken update path on a compiled build would prevent users from ever receiving fixes and could corrupt their installation. Must be resolved **first**.
2. **Complete Documentation Rewrite** — shipping v1.0.0 with stale docs (referencing old architecture, wrong RCON defaults, missing plugin config system) would create support chaos and erode trust. Must be resolved **last**, after all code changes are frozen.

Everything else (GUI editors, data consistency fixes, hardening) is important for the v1.0.0 experience but does not make the tool unstable or unusable if shipped without it.

---

*Last updated: 2026-05-29* — Synchronized to repository state at commit `cc06859`.
