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
All plugins now use the EventBus for communication. No hardcoded inter-plugin dependencies remain:
- ✅ **Timer** — publishes `timer.*` events (started, paused, zero, milestone, tick).
- ✅ **WinCounter** — publishes `win.milestone` and `win.record_low` events. Removed `decrement_on_death` (was DeathCounter coupling).
- ✅ **DeathCounter** — publishes `death.milestone` events with configurable milestones.
- ✅ **LikeGoal** — publishes `likegoal.milestone` and `likegoal.progress` events. Removed direct TikTok event dependency; now consumes `add_likes` commands via API.
- ✅ **SpotifyControl** — publishes `spotify.track_changed`, `spotify.play`, `spotify.pause` events.
- ✅ **Event-Command Mapper** — central wiring via `data/event_commands.yaml` maps any EventBus event to plugin commands without coupling.
  - ✅ **TikTok EventBus publishing fix** — `tiktok.follow`, `tiktok.like`, `tiktok.gift`, `tiktok.join`, `tiktok.comment`, `tiktok.share` now publish as distinct event types (e.g. `tiktok.follow`) instead of all being bundled under `tiktok.event`. This makes them actually usable in Event-Command Mapper / Event Reactions.
  - ✅ **Event Reactions GUI redesign** — complete UX overhaul of the Event-Command Mapper frontend. Replaced technical "Mappings/Actions" UI with a guided 3-step wizard, visual reaction cards, category filters, search, templates, and contextual descriptions. First-time users can now understand the system without documentation.

### Security
- ~~Spotify `client_secret` validation and encrypted storage~~ ✅ Done (see CHANGE_HISTORY.md)
- ~~Download integrity verification (checksummed artifacts)~~ ✅ Done (see CHANGE_HISTORY.md)

### Architecture
- ~~Plugin sandboxing / resource limits~~ ✅ Done (see CHANGE_HISTORY.md)

### GUI
- ~~WebSocket/SSE client for real-time dashboard updates (beyond log streaming)~~ ✅ Done — DashboardPublisher pushes `dashboard.plugin_states`, `dashboard.ecm_diagnostics`, and `dashboard.reactions_activity` every 5s via the existing SSE stream.
- ~~Event-Command Mapper UX overhaul~~ ✅ Done — replaced with Event Reactions wizard + visual cards.
- ~~Save-button state sync across all editors~~ ✅ Done.
- Overlay preview + live theme editor
- Integrated Minecraft server console (RCON terminal)
- Mobile-responsive web dashboard variant

### Testing
- Frontend/GUI integration tests (Playwright or similar)

### Stability & Logging
- ~~Plugin registry backup spam~~ ✅ Done — removed per-save backup from `PluginRegistry._save()`. Now only one startup backup is created when the registry file already exists.
- ~~Built-in app health-check noise~~ ✅ Done — `start.py` health-check loop now skips built-in apps (`App`, `Minecraft Server`, `GUI`, `Overlay`) instead of trying to update them in the plugin registry. Also URL-encodes all plugin names in API calls to prevent "control characters in URL" errors.

---

## 📋 Next 3 Steps

1. **Plugin Implementation Tests** — expand command handler tests (play, pause, add_win, player_death, player_respawn, reset, volume, shuffle, repeat, etc.) across all 5 plugins and add BasePlugin edge-case tests.
2. **Overlay Preview + Live Theme Editor** — add an in-dashboard preview for overlay text and a quick colour editor tied to the live overlay system.
3. **Documentation Rewrite** — update `GUIDE.md` (event bus routing, hook system, declarative subscriptions, Event Reactions, live dashboard), `README.md` (API server, actions editor, Event Reactions), `CHANGELOG.md` (test counts, dates). **Do last, after all code changes frozen.**

---

*Last updated: 2026-06-01 — Event Reactions GUI shipped, TikTok EventBus fix merged, Save-button state sync applied to all editors, Live Dashboard shipped, Registry backup spam fixed, Built-in app health-check noise fixed | Current: Plugin Implementation Tests → Overlay Preview + Live Theme Editor → Documentation Rewrite (DO LAST).*