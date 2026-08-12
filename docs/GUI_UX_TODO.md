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

**Abarbeitungsreihenfolge:** Strukturelles zuerst (P1: i18n → Accessibility → Overlay-Vorschau → Kontext-Hilfe), danach Feinschliff (P2: Status-View → Tastenkürzel → Undo → Mobile/LAN), zum Schluss P3-Ideen.

---

## P1 — Fehlend

### 1. Lokalisierung (i18n)

- [ ] **Status:** Offen
- [ ] **Problem:** Die komplette GUI ist auf Englisch (`<html lang="en">` in `index.html`, kein
      i18n-Mechanismus, alle Strings hart im HTML/JS). Die Zielgruppe ist überwiegend deutsch,
      die Doku wird zweisprachig gepflegt (`docs/dev-book-{en,de}/`).
- [ ] **Ziel:** Sprachumschaltung (mind. DE/EN), persistiert in `localStorage`, Standard aus
      System-/Browser-Sprache ableitbar.
- [ ] **Umsetzungsvorschlag:**
  - Kleines i18n-Modul (z. B. `templates/gui/i18n.js`) mit Dictionary `{de, en}` und
    `t(key, params)`-Funktion; HTML-Text über `data-i18n`-Attribute oder JS-Render-Funktionen.
  - Sprachwahl in den Settings oder als Umschalter in der Sidebar.
  - Kein Framework nötig (Projekt ist Vanilla-JS, siehe `AGENTS.md` §5).
- [ ] **Abnahmekriterien:** Alle Views, Modals, Editor-Strings, Wizard und Fehlermeldungen
      sind übersetzbar; Umschaltung wirkt sofort; Wahl bleibt nach Reload erhalten.
- [ ] **Betroffene Dateien:** `index.html`, `launcher.html`, `app.js`, `actions-editor.js`,
      `templates/gui/tests/*`

---

### 2. Accessibility (Barrierefreiheit & Tastaturbedienung)

- [ ] **Status:** Offen
- [ ] **Problem:** Keine `aria-*`-Attribute, keine Tastaturnavigation: Modals sind nicht per
      `Esc` schließbar, kein Fokus-Management/Fokus-Trap in Overlays, Screenreader erhalten
      keine sinnvollen Labels. `keydown`-Handler existieren nur in Tag-Inputs.
- [ ] **Ziel:** Grundlegende WCAG-Konformität (AA) für die Kernflüsse.
- [ ] **Umsetzungsvorschlag:**
  - `Esc` schließt das oberste Modal; Fokus-Trap innerhalb offener Modals; Fokus beim Öffnen
    ins Modal, beim Schließen zurück zum Auslöser.
  - `aria-label`/`aria-labelledby` für Icons ohne Text (Sidebar-Icons, Theme-Toggle, Buttons),
    `role="dialog"` + `aria-modal` für Overlays, `aria-live` für Toasts/Log.
  - `lang` je View dynamisch an die gewählte Sprache anpassen (verknüpft mit Punkt 1).
- [ ] **Abnahmekriterien:** Vollständige Bedienung ohne Maus möglich; Modals per `Esc` +
      Tab-Fokus sicher bedienbar; Lighthouse/axe-Check ohne kritische Fehler.
- [ ] **Betroffene Dateien:** `index.html`, `design-system.css` (Fokus-Styles), `app.js`,
      `actions-editor.js`, `style.css`

---

### 3. Overlay-Vorschau & Overlay-Test

- [ ] **Status:** Offen
- [ ] **Problem:** Der Overlay-Bereich (`view-overlays`, Rendering in `app.js` ab ca. Zeile
      1357) zeigt nur Copy-URLs. Es gibt keine Möglichkeit, das Overlay zu sehen oder einen
      Sample-Trigger auszulösen.
- [ ] **Ziel:** Overlays direkt im Dashboard ansehen und testen.
- [ ] **Umsetzungsvorschlag:**
  - Eingebettete Vorschau (z. B. `<iframe>` mit Chromakey-Parameter) je Overlay.
  - „Test"-Button, der über den bestehenden Event-Tester / `POST` einen Beispieldatensatz
    (z. B. Fake-Gift/Follow) ans Overlay schickt.
  - Optional: Live-Vorschau aktivieren/deaktivieren pro Overlay.
- [ ] **Abnahmekriterien:** Jedes aufgelistete Overlay ist als Vorschau sichtbar; Test-Trigger
      rendert sichtbar im Overlay.
- [ ] **Betroffene Dateien:** `index.html`, `app.js`, ggf. `src/core/api/routes/` (falls neuer
      Test-Endpunkt nötig) + Tests

---

### 4. Kontext-Hilfe in der GUI

- [ ] **Status:** Offen
- [ ] **Problem:** Keine „?"-Tooltips/Help-Buttons, die auf das mdBook verlinken. Fehlermeldungen
      wirken teils roh (HTTP-Statuscodes statt verständlicher Meldungen mit Handlungsempfehlung).
- [ ] **Ziel:** Nutzer können pro Bereich schnell zur passenden Doku finden; Fehler sind
      verständlich.
- [ ] **Umsetzungsvorschlag:**
  - Help-Button je View/Sektion, der die passende `docs/dev-book-de/...`-Seite öffnet
    (Web-Version der mdBook-Doku).
  - Fehler-Normalisierung im GUI: `_throwResError`/`fetchJSON` sollen Statuscode + Code
    (z. B. `TIKTOK_0001`, siehe `src/core/error_codes.py`) in lesbare Meldungen + ggf. Fix-Hinweis
    übersetzen; Fallback auf generische Meldung.
- [ ] **Abnahmekriterien:** Jeder Hauptbereich hat einen Hilfelink; Fehlermeldungen im UI zeigen
      keine rohen Codes/Stacks an, sondern verständliche Texte.
- [ ] **Betroffene Dateien:** `index.html`, `app.js` (Fehler-Handling), `docs/dev-book-{en,de}`

---

## P2 — UX-Feinschliff

### 5. Status-View ausbauen (Live-Statistiken)

- [ ] **Status:** Offen
- [ ] **Problem:** `view-status` zeigt nur „System Status" + „Plugin Health". Für Streamer fehlen
      die spannenden Live-Zahlen.
- [ ] **Ziel:** Kompaktes Live-Dashboard auf der Status-Seite.
- [ ] **Umsetzungsvorschlag:** Kacheln mit Likes/Follower/Gifts heute, aktueller TikTok-Status,
      RCON-Queue-Länge, Event-Durchsatz (Events/min) über den bestehenden SSE-Stream
      (`/api/v1/ws`) + Revenue-Backend (siehe `feat: revenue viewer`, Commit `58a8fed`).
- [ ] **Abnahmekriterien:** Zahlen aktualisieren sich live ohne Reload; leere Zustände sauber
      dargestellt.
- [ ] **Betroffene Dateien:** `index.html`, `app.js`, `style.css`, ggf. `src/core/api/services/`

---

### 6. Tastenkürzel

- [ ] **Status:** Offen
- [ ] **Problem:** Keine Tastenkürzel außer den impliziten Browser-Standards.
- [ ] **Ziel:** Schnelle Bedienung: `Ctrl+S` speichert im aktiven Editor, `/` fokussiert die
      Suche, `Esc` schließt Modals (verknüpft mit Punkt 2).
- [ ] **Abnahmekriterien:** Kürzel im Dashboard + in den Editoren dokumentiert (z. B. in einem
      „?"-Menü); funktionieren ohne Konflikt mit Eingabefeldern.
- [ ] **Betroffene Dateien:** `app.js`, `actions-editor.js`, `index.html`

---

### 7. Undo nach dem Speichern / Backup-Wiederherstellung

- [ ] **Status:** Offen
- [ ] **Problem:** Editoren haben Review-vor-Speichern, aber nach dem Speichern kein Undo.
      Backups existieren bereits unter `data/backups/` (`AGENTS.md` §3), haben aber kein GUI.
- [ ] **Ziel:** Nutzer können Änderungen an `config.yaml` / `actions.mca` / Plugin-/Hook-Config
      zurückrollen.
- [ ] **Umsetzungsvorschlag:**
  - Backups-View, die `data/backups/` auflistet (Zeitstempel, Quelle, Größe) und Wiederherstellen
    erlaubt.
  - Optional: Undo-Last-Save innerhalb einer Editor-Session (In-Memory-Stack).
- [ ] **Abnahmekriterien:** Backup kann aus der GUI heraus wiederhergestellt werden; Warnung vor
      Überschreiben.
- [ ] **Betroffene Dateien:** `index.html`, `app.js`, `src/core/api/routes/` + `services/`,
      Tests

---

### 8. Mobile / LAN-Nutzung prüfen

- [ ] **Status:** Offen
- [ ] **Problem:** Mit `feat: enable LAN dashboard access` (Commit `e11d6b3`) kann das Dashboard
      aus dem LAN (z. B. Handy) geöffnet werden. Responsive CSS existiert nur teilweise
      (`style.css` `@media (max-width: 960px)` Zeile ~1599, `768px` Zeile ~2401/3008).
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

(Noch nichts abgeschlossen — dieser Bereich wächst beim Abarbeiten.)
