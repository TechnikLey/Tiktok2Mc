# TikTok2Mc — GUI & UX Verbesserungsplan

> Ausgangslage: Die Web-Dashboard-GUI (`templates/gui/`) ist funktional bereits sehr komplett
> (Status, Plugins/Hooks, Actions/Reactions-Editoren, Konsole, Server-Manager, Revenue,
> Event-Tester, First-Run-Wizard, Live-Log). Dieser Plan sammelt die verbleibenden Lücken
> rund um Bedienbarkeit und Nutzerfreundlichkeit.
>
> **So nutzt du die Datei:** Punkte von oben nach unten abarbeiten. Offene Punkte mit `- [ ]`,
> erledigte mit `- [x]` markieren. Vorrangig „Fehlend" (P1), dann „Feinschliff" (P2).

---

## Legende

| Kennung | Priorität | Bedeutung |
|---------|-----------|-----------|
| **P1** | Hoch | Klare Lücke, die aktuell fehlt |
| **P2** | Mittel | UX-Feinschliff / Verbesserung |
| **P3** | Niedrig | Nice-to-have, später |

**Abarbeitungsreihenfolge:** Strukturelles zuerst (P1: ~~i18n~~ ✅ → Accessibility → ~~Overlay-Vorschau~~ ✅ → ~~Kontext-Hilfe~~ ✅), danach Feinschliff (P2: Status-View → ~~Tastenkürzel~~ ✅ → ~~Undo~~ ✅ → Mobile/LAN), zum Schluss P3-Ideen.

---

## P1 — Fehlend

### 1. Lokalisierung (i18n)

- [x] **Status:** **ERLEDIGT** (im Code implementiert)
- [x] **Problem:** Die komplette GUI war auf Englisch (`<html lang="en">` in `index.html`, kein
      i18n-Mechanismus, alle Strings hart im HTML/JS). Die Zielgruppe ist überwiegend deutsch,
      die Doku wird zweisprachig gepflegt (`docs/dev-book-{en,de}/`).
- [x] **Ziel:** Sprachumschaltung (mind. DE/EN), persistiert in `localStorage`, Standard aus
      System-/Browser-Sprache ableitbar.
- [x] **Umsetzung:** `templates/gui/i18n.js` mit Dictionary `{de, en}`, `t(key, params)`,
    `apply(document)`, `setLang(lang)`, `init()`. HTML nutzt `data-i18n`, `data-i18n-placeholder`,
    `data-i18n-title`, `data-i18n-aria-label`. Sprachumschalter in Sidebar-Footer.
- [x] **Abnahmekriterien:** Alle Views, Modals, Editor-Strings, Wizard und Fehlermeldungen
      sind übersetzbar; Umschaltung wirkt sofort; Wahl bleibt nach Reload erhalten; Tests in
      `templates/gui/tests/i18n.test.js`.
- [x] **Betroffene Dateien:** `i18n.js`, `index.html`, `launcher.html`, `app.js`, `actions-editor.js`,
      `style.css` (Language-Switcher), `design-system.css`

---

### 2. Accessibility (Barrierefreiheit & Tastaturbedienung)

- [ ] **Status:** Offen (teilweise: `aria-label` via i18n implementiert)
- [ ] **Problem:** Keine `aria-*`-Attribute (außer `aria-label` via i18n), keine Tastaturnavigation:
      Modals sind nicht per `Esc` schließbar, kein Fokus-Management/Fokus-Trap in Overlays,
      Screenreader erhalten keine sinnvollen Labels. `keydown`-Handler existieren nur in
      Tag-Inputs.
- [ ] **Ziel:** Grundlegende WCAG-Konformität (AA) für die Kernflüsse.
- [ ] **Umsetzungsvorschlag:**
  - `Esc` schließt das oberste Modal; Fokus-Trap innerhalb offener Modals; Fokus beim Öffnen
    ins Modal, beim Schließen zurück zum Auslöser.
  - `aria-label`/`aria-labelledby` für Icons ohne Text (Sidebar-Icons, Theme-Toggle, Buttons),
    `role="dialog"` + `aria-modal` für Overlays, `aria-live` für Toasts/Log.
  - `lang` je View dynamisch an die gewählte Sprache anpassen (verknüpft mit Punkt 1 —
    bereits via `I18N.apply()` implementiert).
- [ ] **Abnahmekriterien:** Vollständige Bedienung ohne Maus möglich; Modals per `Esc` +
      Tab-Fokus sicher bedienbar; Lighthouse/axe-Check ohne kritische Fehler.
- [ ] **Betroffene Dateien:** `index.html`, `design-system.css` (Fokus-Styles), `app.js`,
      `actions-editor.js`, `style.css`

---

### 3. Overlay-Vorschau & Overlay-Test

- [x] **Status:** **ERLEDIGT** (2026-08-14)
- [x] **Problem:** Der Overlay-Bereich (`view-overlays`, Rendering in `app.js`,
      `renderOverlayUrls()`) zeigte nur Copy-URLs. Es gab keine Möglichkeit, das Overlay
      zu sehen oder einen Sample-Trigger auszulösen.
- [x] **Ziel:** Overlays direkt im Dashboard ansehen und testen.
- [x] **Umsetzung:**
  - Jedes Overlay (Built-in: `default` + alle `overlay.overlays[].name`; Plugin-Overlays)
    erhält eine `.card.overlay-item` mit Namen, Copy-URL und `<iframe class="overlay-preview">`
    (transparenter Hintergrund, `chroma=0`). Die kopierte OBS-URL behält `chroma=1`.
  - „Test"-Button (nur für Built-in-Overlays) ruft `testOverlay(name, btn)` → `POST
    /api/v1/overlay/display` mit Beispiel-Titel/-Untertitel (`overlays.testTitle/testSubtitle`)
    und `duration: 3`; die Nachricht erscheint sofort im Preview-Iframe und in OBS.
    Buttons werden während des Sendens deaktiviert; Erfolg/Fehler per Toast.
  - Abschnitts-Überschriften nutzen jetzt die vorhandenen i18n-Keys
    `overlays.builtin`/`overlays.plugins` statt hartkodierter englischer Texte; neue Keys
    `overlays.preview/test/testing/testTitle/testSubtitle/testSent/testFailed` (DE/EN).
  - `help.js`-Topic `overlays` um Abschnitt „Preview & Test" / „Vorschau & Test" erweitert.
  - `style.css`: `.overlay-item`, `.overlay-preview`, `.btn-test`, `.overlay-section-title`.
- [x] **Abnahmekriterien:** Jedes aufgelistete Overlay ist als Vorschau sichtbar; Test-Trigger
      rendert sichtbar im Overlay.
- [x] **Betroffene Dateien:** `app.js` (`renderOverlayUrls()`, `testOverlay()` neu),
      `i18n.js`, `help.js`, `style.css`, `tests/overlays.test.js` (neu, 9 Tests)

---

### 4. Kontext-Hilfe in der GUI

- [x] **Status:** **ERLEDIGT** (2026-08-14)
- [x] **Problem:** Keine „?"-Tooltips/Help-Buttons, die auf das mdBook verlinken. Fehlermeldungen
      wirken teils roh (HTTP-Statuscodes statt verständlicher Meldungen mit Handlungsempfehlung).
- [x] **Ziel:** Nutzer können pro Bereich schnell Hilfe finden; Fehler sind verständlich.
- [x] **Umsetzung:**
  - Neues `templates/gui/help.js`: eigenständige, zweisprachige (DE/EN) Hilfetexte je Hauptbereich
    (Status, Plugins, Hooks, Overlays, Actions, Reactions, Settings, Log, Console, Server-Manager,
    Revenue, Event-Tester, Updates) — **keine** Verweise auf die Dev-Doku
    (`docs/dev-book-{en,de}/`), Inhalt liegt direkt in der GUI.
  - „?"-Button (`Help.openHelp(...)`) in jedem View-Header + Editor-Topbar, Hilfe-Modal
    (`#help-modal`) mit Schließen per Button, Backdrop-Klick und `Esc`; reagiert auf
    Sprachwechsel (`i18n:changed`).
  - Fehler-Normalisierung: `Help.formatApiError(status, detail)` übersetzt HTTP-Statuscodes und
    Backend-Fehlercodes (z. B. `TIKTOK-0001`, `src/core/error_codes.py`) in lesbare Meldungen mit
    Hinweis (Auth-Hint bei 401, Live-Log-Hinweis bei 5xx); `_throwResError` in `app.js` nutzt sie —
    rohe Codes/Validierungs-Details werden nicht mehr angezeigt.
- [x] **Abnahmekriterien:** Jeder Hauptbereich hat einen Hilfelink; Fehlermeldungen im UI zeigen
      keine rohen Codes/Stacks an, sondern verständliche Texte.
- [x] **Betroffene Dateien:** `help.js` (neu), `index.html`, `app.js` (Fehler-Handling),
      `style.css`, `i18n.js`, `tests/help.test.js` (neu), `tests/setup.js`, `tests/dashboard.test.js`,
      `eslint.config.js`

---

## P2 — UX-Feinschliff

### 5. Status-View ausbauen (Live-Statistiken)

- [x] **Status:** **ERLEDIGT**
- [x] **Problem:** `view-status` zeigte nur „System Status" + „Plugin Health". Für Streamer fehlten
      die spannenden Live-Zahlen.
- [x] **Ziel:** Kompaktes Live-Dashboard auf der Status-Seite.
- [x] **Umsetzung:**
  - Neuer `/metrics` Endpoint im Bridge Flask App (`src/python/main.py`) liefert: RCON-Queue-Größe, Trigger-Queue-Größe, Events/Min (rolling 60s), Geschenk-Wert heute.
  - `BridgeMetricsService` (`src/core/api/services/bridge_metrics.py`) holt Metriken vom Bridge.
  - `/status` Endpoint erweitert um `rcon_queue_size`, `trigger_queue_size`, `events_per_minute`, `gift_value_usd_today`.
  - GUI zeigt neue Sektion "Live Statistics" mit farblich kodierten Karten (grün/gelb/rot für Queue-Größen).
  - i18n Keys für DE/EN hinzugefügt.
- [x] **Abnahmekriterien:** Zahlen aktualisieren sich live ohne Reload; leere Zustände sauber dargestellt; Tests grün.
- [x] **Betroffene Dateien:** `src/python/main.py`, `src/core/api/services/bridge_metrics.py`, `src/core/api/routes/health.py`, `src/core/api/models.py`, `templates/gui/index.html`, `templates/gui/app.js`, `templates/gui/i18n.js`

---

### 6. Tastenkürzel

- [x] **Status:** **ERLEDIGT** (2026-08-14)
- [x] **Problem:** Keine Tastenkürzel außer den impliziten Browser-Standards.
- [x] **Ziel:** Schnelle Bedienung: `Ctrl+S` speichert im aktiven Editor, `/` fokussiert die
      Suche, `Esc` schließt Modals (verknüpft mit Punkt 2).
- [x] **Umsetzung:**
  - Neues Modul `templates/gui/shortcuts.js` (Kürzel-Runtime): `Ctrl+S` speichert den
    aktiven Editor (Konfig-, Plugin-, Hook-, Reaktions- und Actions-Editor inkl. Inline-Sektionen;
    übersprungen, solange ein Overlay offen ist), `/` fokussiert das Suchfeld der aktiven Ansicht
    bzw. des offenen Editors, `Esc` schließt das oberste Modal (Topmost-Reihenfolge; `Esc` wirkt
    auch in Eingabefeldern), `?` öffnet das Kürzel-Hilfethema. Kürzel werden beim Tippen in
    Eingabefeldern ignoriert (außer `Ctrl+S`/`Esc`), `unsaved-changes-modal` wird bewusst nicht
    per `Esc` geschlossen.
  - `app.js`: `showConfirmDialog` bestätigt per `Esc` mit `false` (Listener wird bei Cleanup entfernt).
  - `index.html`: „?"-Help-Button in der Sidebar-Footer, `<span class="kbd-hint">Ctrl+S</span>`
    an allen Save-Buttons, `shortcuts.js` in den Script-Tags.
  - `help.js`: neues Topic `shortcuts` (Globale Kürzel + Eingabe-Sicherheit) sowie Kürzel-Hinweis-
    Abschnitte in den Topics `plugins`, `hooks`, `actions`, `reactions`, `settings`.
  - `style.css`: Styles für `.help-modal-body kbd`, `.kbd-hint` und den Sidebar-Footer-Button.
  - `eslint.config.js` (appGlobals + classic files), `tests/setup.js` (lädt `shortcuts.js`),
    neue GUI-Tests in `tests/shortcuts.test.js` (19 Tests: Bindings, `/`-Fokus, `Ctrl+S`,
    `Esc`-Schließen inkl. Confirm-Dialog, Typing-Safety).
- [x] **Abnahmekriterien:** Kürzel im Dashboard + in den Editoren dokumentiert (z. B. in einem
      „?"-Menü); funktionieren ohne Konflikt mit Eingabefeldern.
- [x] **Betroffene Dateien:** `shortcuts.js` (neu), `app.js`, `help.js`, `index.html`, `style.css`,
      `eslint.config.js`, `tests/setup.js`, `tests/shortcuts.test.js` (neu)

---

### 7. Undo nach dem Speichern / Backup-Wiederherstellung

- [x] **Status:** **ERLEDIGT** (2026-08-14)
- [x] **Problem:** Editoren haben Review-vor-Speichern, aber nach dem Speichern kein Undo.
      Backups existieren bereits unter `data/backups/` (`AGENTS.md` §3, `src/core/backup.py`),
      haben aber kein GUI. API-Routen für `list_backups`/`restore_backup` fehlten.
- [x] **Ziel:** Nutzer können Änderungen an `config.yaml` / `actions.mca` / Plugin-/Hook-Config
      zurückrollen.
- [x] **Umsetzung:**
  - Neue API-Endpunkte: `GET /api/v1/backups` (listet Kategorien + Einträge mit Zeitstempel,
    Dateiname, Größe, `restorable`), `POST /api/v1/backups/restore` (mit Sicherheits-Backup des
    aktuellen Ziels vorher), `POST /api/v1/backups/create` (Manuelles Snapshot von config/actions/
    plugin_registry). `BackupService` in `src/core/api/services/backups.py` (Pfadauflösung via
    `core.paths` zur Laufzeit), Router in `src/core/api/routes/backups.py`, Modelle in
    `src/core/api/models.py`.
  - Neue GUI-View „Backups" (Nav-Item + `view-backups`): Kategorien-Gruppierung mit Zähl-Badge,
    Tabelle (Zeit/Datei/Größe/Aktion), „Wiederherstellen"-Button mit Bestätigungsdialog
    (Warnung vor Überschreiben, Sicherheits-Backup wird zuerst erstellt), „Backup Now"-Button,
    Refresh. „?"-Hilfe-Button mit `backups`-Topic in `help.js`. i18n DE/EN.
- [x] **Abnahmekriterien:** Backup kann aus der GUI heraus wiederhergestellt werden; Warnung vor
      Überschreiben; manuelles Backup erstellbar; alle Tests grün (Backend
      `tests/test_api/test_backups.py`, GUI `tests/backups.test.js`).
- [x] **Betroffene Dateien:** `index.html`, `app.js`, `i18n.js`, `help.js`, `style.css`,
      `tests/backups.test.js` (neu), `src/core/api/routes/backups.py` (neu),
      `src/core/api/routes/__init__.py`, `src/core/api/services/backups.py` (neu),
      `src/core/api/models.py`, `src/core/backup.py` (`backup_root`), `tests/conftest.py`,
      `tests/test_api/test_backups.py` (neu)

---

### 8. Mobile / LAN-Nutzung prüfen

- [ ] **Status:** Teilweise implementiert (responsive CSS vorhanden, aber unvollständig getestet)
- [ ] **Problem:** Mit `feat: enable LAN dashboard access` (Commit `e11d6b3`) kann das Dashboard
      aus dem LAN (z. B. Handy) geöffnet werden. Responsive CSS existiert teilweise
      (`style.css` `@media (max-width: 960px)` Zeile ~1633, `768px` Zeile ~2435/3042).
      Sidebar wird zu horizontaler Leiste, Tabellen werden zu Cards, Editor-Layouts stacken.
- [ ] **Ziel:** Dashboard auch auf kleineren Bildschirmen gut bedienbar (Sidebar, Tabellen,
      Editoren, Server-Manager-Modals).
- [ ] **Umsetzungsvorschlag:** Gezieltes Mobile-Review (mind. 375 px und 768 px breite), Seitenleiste
      zu Drawer, Tabellen responsiv, Modals scrollbar & zentriert.
- [ ] **Abnahmekriterien:** Alle Hauptviews sind auf ~375 px nutzbar; keine horizontalen
      Überläufe in Kernflüssen.
- [ ] **Betroffene Dateien:** `style.css`, `index.html`, `app.js`

---

## P3 — Nice-to-have / Ideen

- [ ] **Status:** Ideensammlung
- [ ] Beispiele für weitere Verbesserungen (noch nicht priorisiert):
  - Tab-Autocomplete + History für MC-Befehle in der Konsole (`view-console`).
  - Konfigurierbare Log-Level-Standardansicht pro Sitzung (persistiert).
  - Dashboard „Aufgeräumt/Profi"-Modus (Dichte der Info-Kacheln).
  - Export/Import von kompletten Konfigurationen (Bundle aus `config.yaml` + `actions.mca` +
    Plugin-Configs) als Datei.
  - Session-Zusammenfassung am Stream-Ende (analog Revenue, aber als Bericht).

---

## Erledigt

- **Lokalisierung (i18n)** — `templates/gui/i18n.js` implementiert mit DE/EN, `localStorage`-Persistenz, `data-i18n`-Attribute im HTML, Sprachumschalter in Sidebar, Tests in `templates/gui/tests/i18n.test.js`. (P1)
- **Status-View Live-Statistiken** — Bridge `/metrics` Endpoint, `BridgeMetricsService`, erweiterter `/status` Response, GUI "Live Statistics" Sektion mit RCON/Trigger Queue, Events/Min, Gift Value Today. i18n DE/EN. Tests grün. (P2)
- **Undo nach dem Speichern / Backup-Wiederherstellung** — Neue Backups-API (`GET /api/v1/backups`, `POST /api/v1/backups/restore`, `POST /api/v1/backups/create`) mit `BackupService`, neue GUI-View „Backups" mit Liste, Wiederherstellen-Dialog und „Backup Now", i18n DE/EN, Help-Topic. Backend- + GUI-Tests grün. (P2)
- **Tastenkürzel** — Neues `templates/gui/shortcuts.js` (`Ctrl+S` speichert im aktiven Editor, `/` fokussiert die Suche, `Esc` schließt das oberste Modal, `?` öffnet das Kürzel-Hilfethema; Eingabe-Safety), `Esc`-Bestätigen im Confirm-Dialog (`showConfirmDialog`), Kürzel-Doku in `help.js` + `kbd`-Hints an den Save-Buttons, 19 neue GUI-Tests. GUI-Tests grün. (P2)
- **Overlay-Vorschau & Overlay-Test** — `renderOverlayUrls()` rendert pro Overlay eine Card mit Live-`<iframe>`-Vorschau (`chroma=0`) und „Test"-Button, der `POST /api/v1/overlay/display` mit Beispielnachricht sendet (Toast-Feedback, Button-Deaktivierung); i18n DE/EN (inkl. Abschnitts-Überschriften `overlays.builtin/plugins`), Help-Topic „Vorschau & Test", 9 neue GUI-Tests. GUI-Tests grün. (P1)

---
