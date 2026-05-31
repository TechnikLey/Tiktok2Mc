# TikTok2Mc — Release TODO (v1.0.0)

> **This file only contains unfinished work.**
>
> Completed work, implemented features, and historical changes belong in `docs/CHANGE_HISTORY.md`.

---

## 🔴 REQUIRED — Release Blockers

### 1. Documentation Rewrite (DO LAST — after all code changes frozen)
- `GUIDE.md` is stale: missing event bus routing, hook system, declarative plugin subscriptions
- `CHANGELOG.md` test count and date need updating
- `README.md` should mention API server access and actions editor

---

## 🟡 HIGH — Should Ship Before v1.0.0

### 2. Plugin Lifecycle Tests
No e2e tests for the startup/bridge/plugin-spawn orchestration (`start.py`, `main.py`). The entire launch-to-ready flow is untested — high risk for regressions.

### 3. API Authentication
Implement API-Key auth for `server_host: 0.0.0.0` deployments. Dashboard and API endpoints should require a configurable key when exposed beyond localhost.

## 🟢 MEDIUM — Nice to Have

### 4. `core_hash` Build Cache Optimization
Any change to any file in `src/core/**/*.py` invalidates all cached executables. Correct but wasteful for single-plugin changes. Refined to only invalidate dependent exes via per-task dependency tracking (static import analysis).

### 5. EventBus Plugin Integration
Replace plugin command-polling loop with EventBus push model. Plugins subscribe to events they care about instead of polling `/commands` on a timer. Real-time, lower latency, less wasted CPU.

---

## 🔵 TEST COVERAGE — Known Gaps

| Module | Lines | Risk | Status |
|--------|-------|------|--------|
| `src/core/api/updater.py` | 382 | MEDIUM | `_download_update()`, `install_update()` untested |
| `src/core/api/server.py` | 97 | MEDIUM | FastAPI app factory, CORS, static mounts |
| `build.py` | 422 | MEDIUM | Build system, no tests |
| `src/core/api/services/actions.py` | 421 | LOW | ActionsService line-parser coverage incomplete |

### SSE/WS Test Limitations
- SSE stream **receive** tests cannot use TestClient (httpx blocking limitation)
- WebSocket endpoint (`/api/v1/ws`) is fully implemented but has no client tests

### Recently Completed
- **End-to-end update validation** (`tests/test_core/test_update_integration.py`, 24 tests): version boundary upgrade, signal lifecycle, restart flow, rollback, platform paths
- **Plugin dependency ordering** (`tests/test_core/test_dependency.py`, 30 tests): topological sort, validation on register/put/enable, `depends_on` in `AppConfig`, timer → win-counter enforced
- **Port Scanner** (`src/core/port_scanner.py`, 28 tests): scans 3 bind ports (29185/29187/29188) on startup, auto-resolves conflicts via env vars + runtime file, `port_policy` config section with `max_offset: -1` for unlimited scanning
- **Declarative Command Handler Registration** (`CommentHandler` model, `PUT/DELETE /plugins/{name}/comment-handler`, `GET /comment-handlers`): Spotify registers `$` prefix in `plugin.json`, bridge dispatches comments to plugin API instead of hardcoded HTTP URLs. Removed `handler`/`url` from `config.yaml` Spotify group.

---

## 📋 Post-v1.0.0 Ideas

> These are explicitly out of scope for v1.0.0. Listed here so they are not lost.

### Security
- Spotify `client_secret` validation and encrypted storage
- Download integrity verification (checksummed artifacts)

### Architecture
- Plugin sandboxing / resource limits

### GUI
- WebSocket/SSE client for real-time dashboard updates (beyond log streaming)
- Spotify setup assistant (OAuth flow helper)
- Overlay preview + live theme editor
- Integrated Minecraft server console (RCON terminal)
- Mobile-responsive web dashboard variant

### Testing
- Frontend/GUI integration tests (Playwright or similar)
- Plugin implementation tests (beyond manifest smoke tests)

### Build & Packaging
- Identify and strip dead modules from PyInstaller builds
- Automated release notes generation from CHANGELOG
- GUI installer (Setup Wizard, shortcuts, startup, install location)

---

*Last updated: 2026-05-31 — 588 Python tests + 226 GUI frontend = 814 total | Current: core_hash Build Cache Optimization. Next: Plugin Lifecycle Tests → API Authentication → EventBus Integration.*