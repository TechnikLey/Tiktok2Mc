# TikTok2Mc — Release TODO (v1.0.0)

> **This file only contains unfinished work.**
>
> Completed work, implemented features, and historical changes belong in `docs/CHANGE_HISTORY.md`.
>
> **When editing this file, also update `docs/CHANGE_HISTORY.md` if any items are marked done or removed.**

---

## 🔴 REQUIRED — Release Blockers

### 1. Documentation Rewrite (DO LAST — after all code changes frozen)

#### `GUIDE.md` — Lücken nach Rewrite
Wurde als User-facing-Dokumentation umgeschrieben (`d862c87`), deckt aber folgende Themen noch nicht ab:
- Event Bus Routing (internes Pub/Sub)
- Hook System (wie Hooks funktionieren, erstellen)
- Trigger Engine / Trigger Simulator
- Deklarative Plugin-Subscriptions (`event_subscriptions` in `plugin.json`)
- API-Key-Auth
- Installer-Dokumentation (Windows NSIS, Linux Shell)
- Server Manager (Create Server, Console Instance Selector, Lifecycle)
- MCA Language Server (VS Code Extension)
- Error Codes / Diagnostics / Health Monitoring
- Setup Wizard (GUI-Ersteinrichtung)
- Port Scanner (Detailfunktionsweise)

#### `README.md` — GUI-Features fehlen
Erwähnt weder API Server Access, Actions Editor, Event Reactions, GUI-first-Ansatz, Installer noch Server Manager.

#### `CHANGELOG.md` — v1.0.0-Sektion unvollständig
Fehlende Einträge: UI Redesign, Event Reactions, Live Dashboard, Server Manager, Trigger Engine, MCA Language Server, Error Codes/Diagnostics/Health Monitoring, Hook System, Build Fixes, Plugin-Architektur-Modernisierung. Detail-Chronik existiert in `CHANGE_HISTORY.md` — CHANGELOG.md muss nur die Highlights übernehmen. Testzahl veraltet (475 → 849 Python + 228 GUI = 1077).

#### `ROADMAP.md` — teilweise aktualisiert, aber noch nicht final
Wurde überarbeitet (`bea789c`, `a12b7b0`), listet jetzt korrekte Features. Fehlt: "In Progress"-Items sind teils erledigt (Overlay Preview/Live Theme Editor ist implementiert). Letztes Update 2026-06-02.

#### `AIPrompt.md` — veraltete Pfade
- `~/config/config.yaml` → `defaults/config.yaml`
- `~/core/gifts.json` → `defaults/gifts.json`
- Referenziert noch `event_hooks/` (umbenannt zu `hooks/`)

#### Dev-Books (`docs/dev-book-en/`, `docs/dev-book-de/`)
Beide wurden vollständig neu geschrieben (DE: Phase 3 Rewrite `8dfb042`, EN: 1:1-Übersetzung `a08fb03`). Alte Architektur-Verweise (Self-Registration, Legacy Registry) sind bereinigt. Ein `documentation_clarity_review.md` identifiziert 3 P1-Probleme (Naming-Konvention, `comment_handler` undokumentiert, Error-Code-Format). Status: Basis solide, aber nicht fehlerfrei.

---

## 🟡 SECONDARY — Before Release

### 2. Testzahlen harmonisieren
- `CHANGE_HISTORY.md` spricht von 1197 Tests (inkl. 228 GUI-Vitest), pytest findet 849 Python-Tests.
- `CHANGELOG.md` sagt 475 — weit unter aktuellen Zahlen.
- Einmalige, verlässliche Gesamtzahl ermitteln und überall eintragen.

### 3. `documentation_clarity_review.md`-Fundstellen abarbeiten
- P1: Naming-Konvention in Quickstart vs. Plugin-Structure-Kapitel angleichen
- P1: `comment_handler`-Feld in `plugin.json` dokumentieren
- P1: Error-Code-Format vereinheitlichen (underscore vs. hyphen)

### 4. GUI: Overlay Preview & Live Theme Editor
- Feature ist implementiert, fehlende Punkte prüfen (ggf. Issues in `CHANGE_HISTORY.md` ergänzen)

*Last updated: 2026-07-05 — Umfassendes Review aller Dokumente; dev-books als erledigt markiert; Lücken in GUIDE.md konkretisiert; neue Secondary-Items ergänzt.*