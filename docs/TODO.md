# v1.0.0 — Entwicklungstodo

> **Ziel:** Stabiler v1.0.0-Release mit zentraler FastAPI-Architektur, entkoppelten Plugins und neuer GUI.
> v1.0.0 bricht bewusst mit v0.x. Keine Kompatibilität.
>
> | Prio | Bedeutung |
> |------|-----------|
> | **Kritisch** | Blockiert das Release. Muss vor v1.0.0 fertig sein. |
> | **Hoch** | Sollte drin sein, ohne geht es mit Risiko. |
> | **Mittel** | Wichtig, aber kein Release-Blocker. |
> | **Niedrig** | Nice-to-have für v1.0.0. |

---

## 1. Architektur — API als Rückgrat

> Die FastAPI-API (`src/core/api/`) ist grundlegend gebaut (Server, EventBus, PluginRegistry,
> alle REST-Endpunkte, Client, Launcher). Jetzt muss sie zur zentralen Steuerungseinheit werden.
> Plugins laufen aktuell noch als eigenständige Flask-Prozesse auf eigenen Ports.

- [ ] **Kritisch** — API-Integration in `start.py`
  - `run.py` (API-Server starten) ist ein separater Einstiegspunkt. `start.py` startet nur die
    gebauten Exes. Für v1.0.0 muss der API-Server direkt von `start.py` gemanagt werden.
  - Der API-Server sollte als *erstes* starten (noch vor den Plugins), damit Plugin-Registrierung
    beim Start funktioniert.
  - **Warum:** Aktuell muss `run.py` separat gestartet werden. Die API ist nicht im Orchestrierungs-Flow.

- [ ] **Kritisch** — Plugin-Kommunikation über API zentralisieren
  - Plugins kommunizieren untereinander per HTTP (z.B. Timer → WinCounter). Das muss über die
    zentrale API laufen statt Direktaufrufe.
  - REST/EventBus als Vermittler zwischen Plugins, kein harterodierter `http://localhost:29xxx` mehr.
  - **Warum:** Reduziert Port-Konflikte, entkoppelt Plugins voneinander, ermöglicht das Plugin-Worker-Modell.

- [ ] **Hoch** — Port-Manager (Port-Nutzung reduzieren)
  - Aktuell: 1 API-Port + 7 Plugin-Ports + Minecraft + RCON = 10+ Ports.
  - Ziel: Plugin-Kommunikation über API routen. Ausnahme: Minecraft (25565), RCON (25575), API (29185).
  - **Warum:** "Address already in use" ist eine der häufigsten Fehlerquellen.

- [ ] **Hoch** — EventBus in Plugin-Kommunikation einbinden
  - Der EventBus (async pub/sub) existiert, wird aber nur von der API selbst genutzt (SSE, WebSocket).
  - Plugins sollten Events publizieren und abonnieren können (z.B. `timer.expired` → WinCounter).
  - **Warum:** Lose Kopplung statt harterodierter HTTP-Aufrufe.

- [ ] **Niedrig** — CLI-Modus beibehalten (API-Client)
  - Headless-Betrieb (Linux-Server ohne GUI) muss weiterhin möglich sein.
  - `start.py` bleibt als CLI-Orchestrator erhalten, ruft aber die API auf.
  - **Warum:** v1.0.0 darf keine GUI-Zwang sein.

---

## 2. GUI (komplett neu)

> Die bestehende `gui.py` ist ein Legacy-Überbleibsel (~110 Zeilen).
> Für v1.0.0 wird eine vollwertige Desktop-GUI entwickelt.

- [ ] **Kritisch** — Tech-Stack festlegen
  - Electron, Tauri, Vue.js + pywebview (neu), oder React + Backend.
  - Bundle-Größe, Wartbarkeit, Update-Fähigkeit, Plattform-Unterstützung.

- [ ] **Kritisch** — First-Run-Setup-Wizard
  - TikTok-Username, RCON-Passwort, Plugin-Auswahl, Config speichern + starten.
  - Ohne Setup tut sich nach der Installation nichts (alle Plugins disabled).

- [ ] **Kritisch** — Config-Editor (GUI-Formular)
  - Alle `config.yaml`-Sektionen als Tabs/Accordion.
  - Dynamische Listen hinzufügen/löschen. YAML-Validierung + Backup.

- [ ] **Kritisch** — Actions-Editor (.mca)
  - Trigger-Tabelle mit Inline-Validierung (Validator live).
  - Command-Chain-Editor (semikolon-getrennte Befehle als Karten).

- [ ] **Kritisch** — Dashboard mit Status-Übersicht
  - Minecraft-Server, TikTok-Connection, aktive Plugins, Overlay-URLs.

- [ ] **Kritisch** — Live-Log-Viewer
  - Echtzeit-Logs via WebSocket/SSE. Filterbar nach Level.

- [ ] **Kritisch** — Plugin-Manager
  - Erkannte Plugins listen, enable/disable, Config editieren.

- [ ] **Hoch** — Spotify-Setup-Assistent
  - Schritt-für-Schritt: Client-ID/Secret, OAuth-Login.

- [ ] **Hoch** — Overlay-Vorschau + Test-Notification
  - Embedded Viewer, Overlay testen.

- [ ] **Hoch** — Theme-Editor (visuell)
  - Farbwähler, Live-Vorschau.

- [ ] **Mittel** — Test-Tool in GUI integrieren (Trigger simulieren)
- [ ] **Mittel** — Minecraft-Server-Console in GUI (RCON manuell)

---

## 3. Plugin-Architektur & Entkopplung

> Timer, DeathCounter und WinCounter sind über MinecraftServerAPI-Events fest verdrahtet.
> Jedes Plugin muss standalone lauffähig sein. Das alte Datei-Registry-System ist entfernt,
> die API-Registrierung funktioniert. Plugin-eigene Flask-Server bleiben vorerst.

- [ ] **Kritisch** — Timer von Death/Respawn-Events entkoppeln
  - Timer muss OHNE MinecraftServerAPI/Deathcounter laufen.
  - HTTP-API (Start/Pause/Reset) als primäre Schnittstelle.
  - Death/Respawn optional per Event-Hook.

- [ ] **Kritisch** — Timer/WinCounter-Kopplung lösen
  - Timer=0 incrementiert aktuell automatisch den WinCounter.
  - Config-Option `auto_win: true/false` oder Event-Hook.

- [ ] **Hoch** — WinCounter von Death-Event entkoppeln
  - WinCounter decrementiert bei Death. Per API steuerbar.
  - Hook-Event `on_death` als lose Kopplung.

- [ ] **Hoch** — Plugin-Manifest (`plugin.json`) einführen
  - name, version, description, required_apis, default_enabled, ports.
  - **Warum:** API und Plugin-Manager brauchen verlässliche Plugin-Metadaten.

- [ ] **Hoch** — Plugin-Discovery über Manifest
  - Statt `.exe`-Scannen in `plugins/` über `plugin.json` registrieren.
  - Erlaubt Metadaten vor dem Start.

- [ ] **Niedrig** — Plugin-Lifecycle dokumentieren
  - States: installed → disabled → enabled → running → error.

---

## 4. Konfiguration & Schema

- [ ] **Erledigt** ✓ — Config-Schema für v1.0.0 eingefroren
  - `config_version: v1.0.0` (String statt Int). Breaking Changes nur mit Major-Sprung.
  - Alle Keys abschließend in `_CONFIG_SCHEMA` in `services.py` definiert.

- [ ] **Erledigt** ✓ — Alle Plugins standardmäßig deaktiviert (opt-in)
  - Jedes Plugin `enabled: false` in der Default-Config.
  - Fallback-Defaults in allen 8 Plugin-`main.py` von `True` auf `False` geändert.
  - `minecraft_server_api` bleibt `true` (Core-Infrastruktur, kein Plugin).

- [ ] **Erledigt** ✓ — Config-Validierung in der API
  - `_validate_config_schema()` in `services.py`: Typ-Prüfung, Pflichtfelder, `enabled`-Bool-Prüfung pro Plugin-Sektion, Warnung bei unbekannten Keys.
  - Wird vor jedem `write_config()` aufgerufen.
  - Fehlerhafte Configs werden mit `400 Bad Request` abgewiesen.

- [ ] **Erledigt** ✓ — Config-Backup versioniert
  - `config.yaml.v1.bak`, `config.yaml.v2.bak`, … (automatisch hochzählend).
  - Überschreibt nicht mehr einfach `.bak`.

- [ ] **Niedrig** — Hinweistext für v0.x-User (keine Migration)
  - v0.x-Configs/Plugins inkompatibel. Neuinstallation empfohlen.

---

## 5. Update-System (v1.x → v1.x)

> v0.x → v1.0.0 = Neuinstallation. Der Updater wird erst für v1.x.x-Updates gebraucht.
> Achtung: `update.py` referenziert noch REST-API-Endpunkte des alten Systems.

- [ ] **Kritisch** — Updater mit neuer API-Architektur kompatibel machen
  - Der Updater muss mit der API kommunizieren können (Current-Status, Update-Signal).
  - `update.py`-Anpassungen an die API-Architektur.

- [ ] **Hoch** — Update-Pfad v1.0.0 → v1.0.1 testen
  - Config-Whitelist, Version-Check, Signal-Handling.

- [ ] **Mittel** — Rollback-Mechanismus dokumentieren

---

## 6. Sicherheit

- [ ] **Kritisch** — API-Authentifizierung
  - API steuert Minecraft-Server und RCON. Lokaler Zugriff reicht, aber absichern.
  - Localhost-Binding + optionaler API-Key.

- [ ] **Kritisch** — RCON-Passwort-Warnung prominent (GUI-Banner)
- [ ] **Hoch** — `server_host: 0.0.0.0`-Sicherheitshinweis (exponiert API+RCON)
- [ ] **Hoch** — Spotify `client_secret`-Validierung
- [ ] **Mittel** — Secret-Management (Secrets nicht im Klartext in der Config)

---

## 7. Build & Deployment

- [ ] **Kritisch** — Build-System an neue GUI-Architektur anpassen
  - SPA + PyInstaller kombinieren (npm/bun + Python).

- [ ] **Kritisch** — CI/CD: Smoke-Test nach Build
  - Binary starten, API antwortet, GUI öffnet sich.

- [ ] **Hoch** — Plattform-spezifische Builds (Windows: InnoSetup/MSI, Linux: AppImage)
- [ ] **Hoch** — `version.txt` automatisch prüfen (Konsistenz mit git-tag)
- [ ] **Niedrig** — Mindestanforderungen dokumentieren (Python 3.12+, RAM, Java)

---

## 8. Tests

- [ ] **Kritisch** — API-Integrationstests
  - Jeder Endpunkt muss getestet sein. Die API ist der zentrale Vertrag.

- [ ] **Kritisch** — Validator-Tests (aus v0.5.0 übernommen)
  - Unit-Tests für die Validator-Logik (Brackets, Prefix, Placeholder).

- [ ] **Hoch** — Plugin-Smoke-Tests (jedes Plugin starten + API bereitstellen)
- [ ] **Hoch** — Config-Validierungs-Tests (v1.0.0-Schema)
- [ ] **Mittel** — GUI-Smoke-Tests (GUI starten, Editor öffnet, Status anzeigen)
- [ ] **Mittel** — End-to-End-Test (simulierter Stream: TikTok-Event → API → Plugin → Minecraft)

---

## 9. Cleanup — Legacy entfernt, aber nicht vergessen

> Das alte `python/registry.py`, `PLUGIN_REGISTRY.json`, `--register-only`, `read_plugin_registry()`,
> `validate_config_dict()` und `import-legacy` wurden bereits entfernt.

- [ ] **Erledigt** ✓ — `python/registry.py` gelöscht
- [ ] **Erledigt** ✓ — `PluginLauncher` API-only (kein Legacy-Fallback)
- [ ] **Erledigt** ✓ — `client.py` ohne Fallback auf Datei-Registry
- [ ] **Erledigt** ✓ — `--register-only` aus CLI entfernt
- [ ] **Erledigt** ✓ — Alle Plugin-`main.py`-Imports auf `core.api.client` umgestellt
- [ ] **Erledigt** ✓ — `get_root_dir()` für beliebige Exe-Tiefen gefixt
- [ ] **Erledigt** ✓ — `build.py`/`update.py` ohne `registry`/`plugin_updater`
- [ ] **Erledigt** ✓ — `services.py` ohne `read_plugin_registry()`
- [ ] **Erledigt** ✓ — `models.py` ohne `ImportLegacyResponse`/`validate_config_dict`

- [ ] **Erledigt** ✓ — `gui.py` (alt) entfernt
  - Legacy, kollidiert mit neuer GUI. Funktionale Obsolet.

- [ ] **Erledigt** ✓ — `plugin_updater.py` entfernt (dead code, keine Runtime-Referenzen mehr)
- [ ] **Erledigt** ✓ — `build.py` TOOL_VERSION auf `v1.0.0` aktualisiert

- [ ] **Niedrig** — Weitere Totmodule identifizieren
  - Nach API-Migration: Welche Teile von `start.py`, `main.py`, `server.py` werden durch die API abgelöst?

---

## 10. Dokumentation

- [ ] **Kritisch** — README.md + GUIDE.md für v1.0.0 neu schreiben
  - GUI-Screenshots, Setup-Wizard, neue Architektur.

- [ ] **Kritisch** — Entwicklerdokumentation (dev-book EN+DE) überarbeiten
  - API-Referenz statt Prozess-Orchestrierung.
  - Plugin-Manifest und Lifecycle dokumentieren.

- [ ] **Kritisch** — CHANGELOG für v1.0.0 (Breaking Changes v0.5.x → v1.0.0)
- [ ] **Hoch** — API-Dokumentation (OpenAPI/Swagger automatisch generieren)
- [ ] **Hoch** — Plugin-Entwickler-Dokumentation (Manifest, API, Lifecycle)
- [ ] **Niedrig** — Troubleshooting-Sektion erweitern (API-Fehler, Port-Konflikte)
