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

### GUI
- Integrated Minecraft server console (RCON terminal)

### Testing
- Frontend/GUI integration tests (Playwright or similar)

---

## ⚪ TECHNICAL DEBT — Discovered During Analysis

### Priority: High
| Item | Reason | Est. Complexity |
|------|--------|----------------|
| `config.yaml` inline comments may reference old port values or removed sections | Template was updated piecemeal; spot-check needed for stale references | Low |

### Priority: Medium
| Item | Reason | Est. Complexity |
|------|--------|----------------|
| No build system tests | `build.py` (615 lines) has 0 tests; cross-platform cache invalidation, installer generation, upload all untested | Large |
| GUI frontend integration tests missing | Vitest unit tests exist (6 files) but no Playwright/Cypress E2E against real API | Large |

### Priority: Low
| Item | Reason | Est. Complexity |
|------|--------|----------------|
| SSE/WS receive tests blocked | httpx TestClient limitation prevents SSE stream receive testing; WebSocket client tests skipped | Small |

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

*Last updated: 2026-06-02 — Cleaned: removed completed sections (Plugin Cross-Coupling, Security, Architecture, Stability & Logging, Overlay Preview), removed stale "Plugin Implementation Tests" section and TECHNICAL DEBT row, removed "Completed Since Last Update" and "Next Steps" sections.*