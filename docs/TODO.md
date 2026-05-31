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

### 2. API Authentication *(done)*
API-Key auth for `server_host: 0.0.0.0` deployments: `api_key` config field, middleware checks `X-API-Key` header on non-localhost requests, `start.py` warns when exposed without key. 6 tests.

## 🟢 MEDIUM — Nice to Have

### 3. Plugin Lifecycle Tests *(done)*
20 tests covering signal file concept, manifest discovery, API registration/enable/disable, health check pattern, bridge config loading, comment handler fetch.

### 4. Plugin Implementation Tests
Only manifest smoke tests exist for plugins. No tests for command handlers (play, pause, add_win, player_death, etc.) across all 5 plugins. High regression risk.

### 5. GUI Installer *(in progress)*
Windows NSIS installer (`installer/install.nsi`). Setup wizard, desktop/start menu shortcuts, startup registration, uninstall. Built via `python build.py --installer`.

### 6. Spotify OAuth Flow Helper
GUI assistant that walks users through Spotify Developer app creation, redirect URI setup, and token exchange. Most complex plugin, most painful setup.

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
- **core_hash Build Cache Optimization** (`build.py`): replaced global all-or-nothing `core_hash_changed` flag with per-task dependency tracking via AST import analysis. Changing one core file only invalidates executables that actually import it.
- **EventBus Plugin Integration** (`plugin_overlay.py`, `routes/plugin_overlay.py`, all 5 plugins): replaced 0.5s polling loops with long-polling (`?wait=1`), backed by `asyncio.Event` notification on command enqueue. Zero-latency command delivery, no CPU wasted on idle polling.
- **GUI Installer** (`installer/install.nsi`, `build.py --installer`): NSIS Modern UI 2 script with setup wizard, desktop/start menu shortcuts, startup registration, uninstall.
- **API Authentication** (`server.py`, `config.yaml`, `start.py`): `api_key` config field, middleware on non-localhost, server_host control, 0.0.0.0 warning, 6 tests.
- **Plugin Lifecycle Tests** (`test_lifecycle.py`, `test_auth.py`): 20 tests for signal files, manifest discovery, API enable/disable, health check pattern, bridge init.

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
- Overlay preview + live theme editor
- Integrated Minecraft server console (RCON terminal)
- Mobile-responsive web dashboard variant

### Testing
- Frontend/GUI integration tests (Playwright or similar)

### Build & Packaging
- Identify and strip dead modules from PyInstaller builds
- Automated release notes generation from CHANGELOG

---

*Last updated: 2026-05-31 — 609 Python tests + 226 GUI frontend = 835 total | Current: Plugin Implementation Tests. Next: GUI Installer → Spotify OAuth Flow Helper.*