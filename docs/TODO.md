# TikTok2Mc — Release TODO (v1.0.0)

> **This file only contains unfinished work.**
>
> Completed work, implemented features, and historical changes belong in `docs/CHANGE_HISTORY.md`.
>
> **When editing this file, also update `docs/CHANGE_HISTORY.md` if any items are marked done or removed.**

---

## 🔴 REQUIRED — Release Blockers

### 1. Documentation Rewrite (DO LAST — after all code changes frozen)
- `GUIDE.md` is stale: missing event bus routing, hook system, declarative plugin subscriptions, Event Reactions, Live Dashboard, GUI-first entry point, Setup Wizard, Port Scanner, Backup System, API Key auth, installer docs
- `README.md` should mention API server access, actions editor, Event Reactions, GUI-first, installers
- `CHANGELOG.md` v1.0.0 section missing 12+ recent changes (UI redesign, Event Reactions, Live Dashboard, build fixes); test count needs updating
- `ROADMAP.md` very stale — lists completed features as missing, test counts are wrong (claims 378, actual far higher); should be rewritten or removed
- `AIPrompt.md` references stale file paths (`~/core/gifts.json` → `~/defaults/gifts.json`, `~/config/config.yaml` path ambiguous)
- `docs/dev-book-en/` and `docs/dev-book-de/` reference old plugin system architecture (self-registration, legacy registry) — needs audit

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

### Untested Modules
| Module | Lines | Risk | Notes |
|--------|-------|------|-------|
| `src/python/main.py` | ~622 | HIGH | 0 tests — core TikTok bridge and event loop |
| `src/python/start.py` | ~754 | HIGH | 0 tests — launcher, plugin process management, health checks |
| `src/python/update.py` | ~227 | MEDIUM | Covered by E2E tests but no direct unit tests |
| `src/python/gui.py` | ~347 | LOW | Shell wrapper; hard to test without pywebview |
| `src/core/backup.py` | 265 | MEDIUM | 30 standalone tests exist but no coverage for restore/coalescing edge cases |
| `src/core/hook_api.py` | ~51 | LOW | Simple wrapper, indirect coverage via hook system tests |
| `build.py` | ~615 | MEDIUM | 0 tests — build system, cross-platform caching, installer generation |

### GUI Frontend Coverage
- Vitest + JSDOM tests exist (6 test files) but no **integration tests** with real API backend
- No Playwright/Cypress E2E tests for GUI workflows (config save, plugin toggle, actions edit)

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

## ⚪ TECHNICAL DEBT — Discovered During Analysis

### Priority: High
| Item | Reason | Est. Complexity |
|------|--------|----------------|
| `AIPrompt.md` stale file paths | References `~/core/gifts.json` (moved to `~/defaults/gifts.json`) and ambiguous `~/config/config.yaml` path | Trivial |
| `docs/dev-book-en/` and `docs/dev-book-de/` reference old architecture | Still documents self-registration plugins, legacy registry, old plugin system | Medium |
| `config.yaml` inline comments may reference old port values or removed sections | Template was updated piecemeal; spot-check needed for stale references | Low |

### Priority: Medium
| Item | Reason | Est. Complexity |
|------|--------|----------------|
| No build system tests | `build.py` (615 lines) has 0 tests; cross-platform cache invalidation, installer generation, upload all untested | Large |
| Plugin command handler tests missing | Only manifest smoke tests exist across all 5 plugins — no tests for play, pause, add_win, player_death, player_respawn, reset, volume, shuffle, repeat, etc. | Medium |
| GUI frontend integration tests missing | Vitest unit tests exist (6 files) but no Playwright/Cypress E2E against real API | Large |

### Priority: Low
| Item | Reason | Est. Complexity |
|------|--------|----------------|
| SSE/WS receive tests blocked | httpx TestClient limitation prevents SSE stream receive testing; WebSocket client tests skipped | Small |
| `docs/ROADMAP.md` severely stale | Lists completed features as missing, wrong test counts; consider archiving | Trivial |

---

## 🛠️ REFACTOR OPPORTUNITIES

| Opportunity | Benefit | Risk | Est. Complexity |
|-------------|---------|------|----------------|
| Unify test mocking strategy — heavy deps (TikTokLive, mcrcon, flask) currently mocked in `conftest.py` but pattern isn't documented or enforced across all test files | Faster, more reliable test suite | Low — already partially done | Small |
| Extract `config.yaml` schema validation into dedicated module | Currently mixed into `services/__init__.py`; standalone module would be testable and reusable | Low | Medium |
| Standardize error responses across all API routes | Some routes return `{"detail": ...}`, others return plain strings or `JSONResponse` directly | Low | Medium |
| Remove dead code: `python/overlay.py` is now redundant with `core/overlay.py` | Cleaner codebase | Low (needs verification if any imports remain) | Small |
| `send_trigger.py` in tests/ is a test utility, not a real test — consider promotion or removal | Clearer test boundaries | Low | Trivial |

---

## 🔧 INFRASTRUCTURE IMPROVEMENTS

| Item | Priority | Est. Complexity |
|------|----------|----------------|
| CI build step on PRs — currently build only runs on tags; PRs can break compilation without detection | High | Medium |
| CI step to validate compiled `update.exe` → `start.exe` restart flow | High | Large |
| Automated release notes generation from CHANGELOG/commits | Low | Medium |
| Document test mocking conventions in contributing guide | Low | Trivial |

---

## 📋 Next 3 Steps

1. **Plugin Implementation Tests** — expand command handler tests (play, pause, add_win, player_death, player_respawn, reset, volume, shuffle, repeat, etc.) across all 5 plugins and add BasePlugin edge-case tests.
2. **Documentation Rewrite** — update `GUIDE.md` (event bus routing, hook system, declarative subscriptions, Event Reactions, live dashboard), `README.md` (API server, actions editor, Event Reactions), `CHANGELOG.md` (test counts, dates). **Do last, after all code changes frozen.**
3. **Finalize for v1.0.0 release** — freeze code, run final test pass, compile release binaries, generate checksums, publish.

---

*Last updated: 2026-06-02 — UI/UX Design System shipped, Spotify plugin-local config migrated, Build cache invalidation fixed, Config schema drift fixed, API config save hardening, Comment_commands.groups false-positive fix applied | Current: Plugin Implementation Tests → Overlay Preview + Live Theme Editor → Documentation Rewrite (DO LAST).*