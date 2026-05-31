# TikTok2Mc — Release TODO (v1.0.0)

> **This file only contains unfinished work.**
>
> Completed work, implemented features, and historical changes belong in `docs/CHANGE_HISTORY.md`.
>
> **When editing this file, also update `docs/CHANGE_HISTORY.md` if any items are marked done or removed.**

---

## 🔴 REQUIRED — Release Blockers

### 1. Documentation Rewrite (DO LAST — after all code changes frozen)
- `GUIDE.md` is stale: missing event bus routing, hook system, declarative plugin subscriptions
- `CHANGELOG.md` test count and date need updating
- `README.md` should mention API server access and actions editor

---

## 🟡 HIGH — Should Ship Before v1.0.0

### 2. Plugin Implementation Tests
Only manifest smoke tests exist for plugins. No tests for command handlers (play, pause, add_win, player_death, etc.) across all 5 plugins. High regression risk.

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

---

## 🟠 IMPORTANT — Plugin Coupling & Unfinished Work

> These are **not** out-of-scope ideas. They are real structural issues that need to be addressed before v1.0.0, tracked here because they span multiple plugins.

### Plugin Cross-Coupling
Some plugins are not fully decoupled and still depend on each other's internal behaviour:
- ✅ **Timer** — rewritten to publish `timer.*` events to the EventBus via `POST /api/v1/events`. No `depends_on`, no `send_command()` to other plugins. Consumers (hooks, plugins, dashboard) subscribe via EventBus or state polling. Configurable direction, loop, milestones, reset triggers, and signal events.
- ⬜ **DeathCounter → Timer** coupling exists in pause-on-death logic. Timer no longer has built-in death handling; this should be moved to a hook or the death-counter plugin should send timer commands via API.
- ⬜ **LikeGoal** emits events that other plugins may implicitly rely on; no formal contract documented.

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

## 📋 Next 3 Steps

1. **Plugin Implementation Tests** — expand command handler tests (play, pause, add_win, player_death, player_respawn, reset, volume, shuffle, repeat, etc.) across all 5 plugins and add BasePlugin edge-case tests.
2. **Documentation Rewrite** — update `GUIDE.md` (event bus routing, hook system, declarative subscriptions), `README.md` (API server, actions editor), `CHANGELOG.md` (test counts, dates). **Do last, after all code changes frozen.**
3. **Plugin Cross-Coupling Refactor** — remove hardcoded inter-plugin dependencies (Timer→WinCounter `send_command()`, DeathCounter→Timer pause-on-death logic). Replace with declarative `depends_on` + EventBus subscriptions. Document LikeGoal event contracts.

---

*Last updated: 2026-05-31 — 678 Python tests + 226 GUI frontend = 904 total | Current: Plugin Implementation Tests → Documentation Rewrite (DO LAST).*