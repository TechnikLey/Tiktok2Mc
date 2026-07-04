# TikTok2Mc — Release TODO (v1.0.0)

> **This file only contains unfinished work.**
>
> Completed work, implemented features, and historical changes belong in `docs/CHANGE_HISTORY.md`.
>
> **When editing this file, also update `docs/CHANGE_HISTORY.md` if any items are marked done or removed.**

---

## 🔴 REQUIRED — Release Blockers

### 1. Documentation Rewrite (DO LAST — after all code changes frozen)
- `GUIDE.md` is stale: missing event bus routing, hook system, Trigger Engine, Trigger Simulator, declarative plugin subscriptions, Event Reactions, Live Dashboard, GUI-first entry point, Setup Wizard, Port Scanner, Backup System, API Key auth, installer docs, Server Manager (Create Server, Console Instance Selector, lifecycle), MCA language server, error codes/diagnostics/health monitoring
- `README.md` should mention API server access, actions editor, Event Reactions, GUI-first, installers, Server Manager
- `CHANGELOG.md` v1.0.0 section missing recent changes (UI redesign, Event Reactions, Live Dashboard, Server Manager, Trigger Engine, MCA language server, error codes/diagnostics/health monitoring, hook system, build fixes); test count needs updating
- `ROADMAP.md` very stale — lists completed features as missing, test counts are wrong (claims 378, actual 1197); should be rewritten or removed
- `AIPrompt.md` references stale file paths (`~/core/gifts.json` → `~/defaults/gifts.json`, `~/config/config.yaml` path ambiguous)
- `docs/dev-book-en/` and `docs/dev-book-de/` reference old plugin system architecture (self-registration, legacy registry) — needs audit

---

## ⚪ TECHNICAL DEBT — Discovered During Analysis

### Priority: High
| Item | Reason | Est. Complexity |
|------|--------|----------------|
| `config.yaml` inline comments may reference old port values or removed sections | Template was updated piecemeal; spot-check needed for stale references | Low |

---

## 🛠️ REFACTOR OPPORTUNITIES

| Opportunity | Benefit | Risk | Est. Complexity |
|-------------|---------|------|----------------|
| Standardize error responses across all API routes | `plugin_overlay.py` returns HTML for OAuth errors (browser redirect — intentional); rest uses `HTTPException` consistently | Low | Small |

---

*Last updated: 2026-07-04 — Refactor: config.yaml schema validation in `validation_framework.py` (statt `services/__init__.py`); error responses standardisiert (plugin_config.py, actions.py); python/overlay.py als nicht-tot erkannt und entfernt.*