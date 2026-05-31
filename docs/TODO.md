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

### 5. GUI Installer *(done)*
Windows NSIS installer (`installer/install.nsi`). Setup wizard, desktop/start menu shortcuts, startup registration, uninstall. Built via `python build.py --installer`. 13 tests.

### 6. Spotify OAuth Flow Helper *(done)*
CLI wizard (`src/python/spotify_setup.py`) that guides users through Spotify OAuth: opens browser, runs local callback server, exchanges code for tokens, saves to config. Also supports `--refresh` mode. 16 tests.

---

## 🟠 PLUGIN REWORK — Refactor Required

### 7. Plugin Code Modernisation *(done — all 5 plugins)*
- ✅ Timer refactored to `BasePlugin` (commit `b5e0f38`)
- ✅ `spotify`, `wincounter`, `deathcounter`, `likegoal` migrated to `BasePlugin` (commit `adb4f28`)
- ✅ Duplicated config load / theme load / `urllib.request` boilerplate removed
- ✅ Using BasePlugin API helpers (`api_post`, `api_get`, `push_state`, `register_handler`)
- ⬜ Move Spotify OAuth tokens from separate file into central `config.yaml` (deferred)

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
- **Test suite stability fix** (`commit 68e9739`): fixed infinite tight-loop in `test_base_plugin.py` (2 tests calling `_command_polling_loop` without exit condition), added `time.sleep(0.1)` safety guard in `BasePlugin._command_polling_loop`, mocked heavy imports (`TikTokLive`, `mcrcon`, `flask`) in `conftest.py` to prevent test hangs, configured `pytest-timeout = 40s`.
- **BasePlugin + Timer refactor** (`src/core/base_plugin.py`, `src/plugins/timer/main.py`, `tests/test_core/test_base_plugin.py`, 18 tests): shared base class with config load, theme, API helpers, command polling, state push, window state, overlay registration. Timer reduced from 275 to 90 lines.
- **End-to-end update validation** (`tests/test_core/test_update_integration.py`, 24 tests): version boundary upgrade, signal lifecycle, restart flow, rollback, platform paths
- **Plugin dependency ordering** (`tests/test_core/test_dependency.py`, 30 tests): topological sort, validation on register/put/enable, `depends_on` in `AppConfig`, timer → win-counter enforced
- **Port Scanner** (`src/core/port_scanner.py`, 28 tests): scans 3 bind ports (29185/29187/29188) on startup, auto-resolves conflicts via env vars + runtime file, `port_policy` config section with `max_offset: -1` for unlimited scanning
- **Declarative Command Handler Registration** (`CommentHandler` model, `PUT/DELETE /plugins/{name}/comment-handler`, `GET /comment-handlers`): Spotify registers `$` prefix in `plugin.json`, bridge dispatches comments to plugin API instead of hardcoded HTTP URLs. Removed `handler`/`url` from `config.yaml` Spotify group.
- **core_hash Build Cache Optimization** (`build.py`): replaced global all-or-nothing `core_hash_changed` flag with per-task dependency tracking via AST import analysis. Changing one core file only invalidates executables that actually import it.
- **EventBus Plugin Integration** (`plugin_overlay.py`, `routes/plugin_overlay.py`, all 5 plugins): replaced 0.5s polling loops with long-polling (`?wait=1`), backed by `asyncio.Event` notification on command enqueue. Zero-latency command delivery, no CPU wasted on idle polling.
- **GUI Installer** (`installer/install.nsi`, `build.py --installer`): NSIS Modern UI 2 script with setup wizard, desktop/start menu shortcuts, startup registration, uninstall. 13 tests.
- **API Authentication** (`server.py`, `config.yaml`, `start.py`): `api_key` config field, middleware on non-localhost, server_host control, 0.0.0.0 warning, 6 tests.
- **Plugin Lifecycle Tests** (`test_lifecycle.py`, `test_auth.py`): 20 tests for signal files, manifest discovery, API enable/disable, health check pattern, bridge init.
- **Spotify OAuth Flow Helper** (`src/python/spotify_setup.py`): CLI wizard for Spotify Developer app setup, browser OAuth, local callback server, token exchange, `--refresh` mode. 16 tests.

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

## 🚀 Next 3 Steps

1. **Plugin Implementation Tests** *(in progress)* — expand command handler tests (play, pause, add_win, player_death, player_respawn, reset, volume, shuffle, repeat, etc.) and add BasePlugin edge-case tests
2. **Documentation Rewrite** — update `GUIDE.md` (event bus routing, hook system, declarative subscriptions), `README.md` (API server, actions editor), `CHANGELOG.md` (test counts, dates)
3. **Spotify OAuth Centralisation** — move tokens from `data/spotify_token.json` into `config.yaml` `spotify` section (aligns with `spotify_setup.py` output)

---

*Last updated: 2026-05-31 — 678 Python tests + 226 GUI frontend = 904 total | Current: Plugin Implementation Tests → Documentation Rewrite (DO LAST).*
