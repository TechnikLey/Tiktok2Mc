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
- Comment commands with role-based permissions, cooldowns, and channel-points integration

### API & Plugin System
- Central FastAPI server (`127.0.0.1:29185`) with 12 consistent REST routes
- `API_VERSION` centrally defined; `DEFAULT_PORT` unified across codebase
- Deterministic plugin discovery via `plugin.json` manifests (8 plugins)
- `PluginLauncher` API-only (no legacy registry fallback)
- Enable/disable endpoints: `POST /api/v1/plugins/{name}/enable|disable`
- Discovery endpoint: `GET /api/v1/plugins/discover` (read-only, no side effects)
- Health polling with 10 s timeout before plugin load
- Fallback mode: continues without plugins if API fails to start

### Update System
- `PluginUpdateChecker` with semver comparison
- `GET /api/v1/plugins/updates` endpoint
- Tool update check: `GET /api/v1/updates/check` (GitHub Releases API)
- Dual signaling (file-based `update_signal.tmp` + API `/updater/signal`)
- `update.py` and `start.py` coordinated signal handling

### Security & Configuration
- CORS restricted to local origins (was `["*"]`)
- Warnings for default RCON password (`ABC1234`) and `server_host: 0.0.0.0`
- Semantic config versioning (`config_version: 1.0`)
- Config normalization, schema validation, and automatic backups
- All plugins default to `enabled: false` (opt-in)

### Plugin Decoupling
- Timer, DeathCounter, WinCounter, OverlayText, LikeGoal, Spotify, ChannelPoints — all standalone
- Each plugin exposes its own REST API; no cross-plugin hard dependencies
- Timer: `auto_win: false`, `pause_on_death: false`
- WinCounter: `decrement_on_death: false`

### Testing & CI
- 285 tests passing, 4 skipped (SSE/WS stability)
- CI workflow `test.yml` on push/PR to `main`
- Coverage: API integration, plugin discovery, manifest validation, updater logic, signal handling, config CRUD, event validation

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

### 1. GUI — HIGHEST PRIORITY / RELEASE BLOCKER
> **Status: SCAFFOLDED — CORE SHELL EXISTS, FEATURES MISSING.**
>
> A minimal GUI now exists:
> - `src/python/gui.py` — pywebview shell that opens the dashboard served by the API server
> - `templates/gui/index.html` — minimal SPA dashboard (status, plugin list, config summary)
> - API server mounts `/gui` static files
> - `start.py` launches `gui.exe` when `gui.enabled: true`
> - `build.py` compiles `gui.py` into the release package
>
> **Why it still blocks release:** The current dashboard is read-only and lacks the interactive features non-technical users need. The README promise of "No programming required" is not fully realized without a first-run wizard and visual editors.

- [x] Tech stack decision and scaffolding (pywebview + API-served SPA)
- [x] Graceful integration with existing `start.py` launcher
- [x] Minimal live dashboard (connection status, plugin list, config summary)
- [ ] **RELEASE BLOCKER** — First-run setup wizard (TikTok username, RCON password, feature selection)
- [ ] **RELEASE BLOCKER** — `config.yaml` editor with live validation and inline help
- [ ] **RELEASE BLOCKER** — `data/actions.mca` editor with syntax highlighting / validation
- [ ] **RELEASE BLOCKER** — Real-time log viewer
- [ ] **RELEASE BLOCKER** — Plugin manager with enable/disable toggles that persist to config
- [ ] **RELEASE BLOCKER** — Overlay URL helper (copy-paste OBS browser sources)

### 2. End-to-End Update Validation
> **Status: IMPLEMENTED BUT NOT VALIDATED IN A REAL BUILD.**
>
> The update subsystem has 56 unit/integration tests, but the compiled `update.exe` → `start.exe` → restart flow has never been exercised across actual version boundaries.

- [ ] **RELEASE BLOCKER** — End-to-end update test: compiled v1.0.0 → v1.0.1
  - Verify `update.exe` performs file-based signaling (`update_signal.tmp`) correctly
  - Verify API-based kill signal fallback (`GET/PUT/DELETE /api/v1/updater/signal`) works
  - Verify config whitelist preserves user settings across update
  - Verify rollback / recovery behavior on interrupted update
  - Verify Windows and Linux paths (tmux/screen session cleanup)

---

## v1.0.0 — IMPORTANT (NON-BLOCKING BUT REQUIRED)

> **These must be completed before release, but they do not block tagging on their own if the blockers above are resolved.**

### Build & Deployment Finalization
- [ ] **High** — Migration notice for v0.x users (config/plugins are incompatible)
- [ ] **High** — Automated verification that `version.txt` matches `TOOL_VERSION` in `build.py`
- [ ] **Medium** — Document minimum system requirements in release notes
- [ ] **Medium** — Document manual rollback procedure
- [ ] **Medium** — Final troubleshooting expansion (common first-start errors)

### API & Plugin Hardening
- [ ] **Medium** — Final consistency review of all 12 API routes (error messages, status codes, pagination)
- [ ] **Medium** — Validate graceful degradation when individual plugin processes crash
- [ ] **Low** — Verify CORS behavior is correct for all local-origin scenarios

### Documentation Finalization
- [ ] **Medium** — Final pass: ensure `GUIDE.md` matches actual v1.0.0 behavior exactly
- [ ] **Medium** — Final pass: ensure `README.md` quick-start works on a clean Windows install without Python
- [ ] **Low** — Document log file locations and safe cleanup procedures

---

## POST v1.0.0

> **Explicitly deferred. Do not work on these until v1.0.0 is shipped.**

### Security
- [ ] **Medium** — API authentication (API-Key) for deployments using `server_host: 0.0.0.0`
- [ ] **Low** — Spotify `client_secret` validation and encrypted storage

### Architecture & Performance
- [ ] **Medium** — Port consolidation: reduce 7+ plugin ports to fewer endpoints or reverse-proxy through API
- [ ] **Medium** — EventBus integration into plugin-to-plugin communication
- [ ] **Medium** — Centralized port manager to prevent collisions

### Testing
- [ ] **Low** — Stabilize SSE/WS integration tests (currently 4 skipped due to `TestClient` limitations)

### GUI Enhancements (v1.1.0+)
- [ ] **Low** — Spotify setup assistant (OAuth flow helper)
- [ ] **Low** — Overlay preview + live theme editor
- [ ] **Low** — Integrated Minecraft server console (RCON terminal)
- [ ] **Low** — Mobile-responsive web dashboard variant

### Build & Packaging
- [ ] **Low** — Identify and strip dead modules from PyInstaller builds
- [ ] **Low** — Automated release notes generation from CHANGELOG

---

*Last updated: 2026-05-28*