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

*Last updated: 2026-07-04 — Refactor items und config.yaml-Kommentarprüfung abgeschlossen; nur noch 🔴 Documentation Rewrite offen.*