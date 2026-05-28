# v1.0.0 — Entwicklungstodo

> **Ziel:** Stabiler v1.0.0-Release mit zentraler FastAPI-Architektur, entkoppelten Plugins.
> v1.0.0 bricht bewusst mit v0.x. Keine Kompatibilität.

---

## ✅ Erledigt (aktueller Stand)

### API & Plugin-System
- ✓ API-Server startet als Daemon-Thread in `start.py` vor Plugin-Discovery
- ✓ Health-Poll (10 s Timeout) vor `PluginLauncher.get_plugins()`
- ✓ Fallback-Modus bei API-Ausfall (startet ohne Plugins)
- ✓ `PluginLauncher` API-only (kein Legacy-Fallback)
- ✓ Alle 12 API-Routes haben konsistentes Error-Handling
- ✓ Port-Konstanten-Vereinheitlichung: `DEFAULT_PORT` aus `server.py` importiert
- ✓ `API_VERSION` in `models.py` zentral definiert (kein Circular Import mehr)
- ✓ Route-Ordering gefixt: `/plugins/updates` vor `/plugins/{name}`
- ✓ `start.py`: Breitere Exception-Behandlung beim Config-Laden + API-Thread-Fehler-Logging
- ✓ Enable/Disable-Endpunkte — `POST /api/v1/plugins/{name}/enable|disable`
- ✓ Plugin-Discovery-Endpunkt — `GET /api/v1/plugins/discover` (read-only, kein Registry-Seiteneffekt)

### Plugin-Manifest (plugin.json)
- ✓ `plugin.json` für alle 8 Plugins
- ✓ `PluginManifest` Pydantic-Modell mit Validierung (kebab-case name, semver, ports)
- ✓ `PluginRegistration.from_manifest()`-Factory
- ✓ `PluginLauncher` liest Manifeste statt `.exe`-Scannen
- ✓ Discovery deterministisch und testbar vor Plugin-Execution
- ✓ `update_url`-Feld für Plugin-Update-Prüfung
- ✓ Zentrales Registrieren über `POST /api/v1/plugins/register`
- ✓ Plugin-Self-Registration aus allen `main.py` entfernt

### Discovery-Service
- ✓ `core/api/services/plugin_discovery.py` — reiner Dateisystem-Scanner, kein Registry-Import
- ✓ `services.py` in Package `services/` umgewandelt (abwärtskompatibel)

### Update-System
- ✓ `PluginUpdateChecker`-Service: Versionsvergleich über `update_url`
- ✓ `GET /api/v1/plugins/updates`-Endpunkt
- ✓ API-Kill-Signal-Endpunkte (`GET/PUT/DELETE /api/v1/updater/signal`)
- ✓ Plugin-Update-Check in `start.py`-Startup
- ✓ Duales Signaling in `update.py` + `start.py` (API + Datei)
- ✓ 45 Tests: 18 Manifest + 22 Updater + 5 Signal-Endpunkt

### Testing & CI
- ✓ Tests: `pytest.ini`, `conftest.py`, 274 Testfälle (4 Skipped SSE/WS)
- ✓ API-Integrationstests: Health, Config CRUD, Plugins CRUD, Events, Discovery
- ✓ Discovery-Tests: 6 Tests — Vollständigkeit, Registry-Merge, leeres Verzeichnis, Determinismus, kein Seiteneffekt
- ✓ API-Fehlertests: Config 404, 500, Event-Validierung
- ✓ API-Validierung: Plugin-Felder (level, port, name) werden korrekt abgewiesen (422)
- ✓ Core-Tests: `normalize_config_version()`, EventBus, PluginAPIClient, PluginLauncher
- ✓ Core-Tests: Validator (44 Tests), Registry Backup, korrupte JSON-Wiederherstellung
- ✓ Core-Tests: Manifest (18 Tests), Updater (22 Tests), Signal (5 Tests)
- ✓ Smoke-Tests: 62 Tests für Manifest-Struktur, Content, Discovery-Integration
- ✓ CI-Workflow: `test.yml` (push/PR auf main)
- ✓ Produktions-Bugs behoben: `write_config()`-Validierung, `normalize_config_version()`

### Legacy-Cleanup
- ✓ `python/registry.py` gelöscht
- ✓ `client.py` ohne Fallback auf Datei-Registry
- ✓ `--register-only` aus CLI entfernt
- ✓ `get_root_dir()` für beliebige Exe-Tiefen gefixt
- ✓ `build.py`/`update.py` ohne `registry`/`plugin_updater`
- ✓ `services.py` ohne `read_plugin_registry()`
- ✓ `models.py` ohne `ImportLegacyResponse`/`validate_config_dict`
- ✓ `gui.py` (alt) entfernt
- ✓ `plugin_updater.py` entfernt (dead code)
- ✓ Dead Code entfernt: `ErrorResponse`, `WSMessage`
- ✓ `build.py`/`upload.py` TOOL_VERSION → `v1.0.0`

### Sicherheit (non-blocking Warnings)
- ✓ CORS-Standard von `["*"]` auf lokale Origins geändert
- ✓ Security-Warning bei `--host 0.0.0.0` in `run.py` + `start.py`
- ✓ CORS-Hinweis im API-Startup-Log
- ✓ RCON-Warnung im Log bei Standard-Passwort `ABC1234`

### Plugin-Entkopplung
- ✓ Timer: REST-API (`/start`, `/pause`, `/reset`, `/status`)
- ✓ Timer: `auto_win: false`, `pause_on_death: false`
- ✓ WinCounter: `decrement_on_death: false`
- ✓ Alle Plugins standalone mit `false`-Defaults

### Konfiguration & Schema
- ✓ `config_version: 1.0` (semantische Versionierung MAJOR.MINOR)
- ✓ `normalize_config_version()` in `core/utils.py`
- ✓ API normalisiert on Read, upgraded on Write
- ✓ `update.py` verwendet `packaging.version.parse()`
- ✓ Alle Plugins standardmäßig deaktiviert (opt-in)
- ✓ Schema-Validierung in der API
- ✓ Versionierte Config-Backups
- ✓ Warnung bei unbekannten Top-Level-Keys

---

## 🔜 Für v1.0.0

### 1. Tool-Update-Prüfung (Hoch)
- [ ] **Tool-Update-Prüfung** — `GET /api/v1/updates/check`
  - Prüft das Haupt-Repo (`TechnikLey/Tiktok2Mc`) auf neue Releases.
  - Liefert `tag_name`, `version`, `release_url`, `published_at`.

### 2. Update-Pfad testen (Hoch)
> `PluginUpdateChecker` und API-Signal-Endpunkte sind implementiert.

- [ ] **End-to-End-Update-Test** v1.0.0 → v1.0.1
  - Config-Whitelist, Version-Check, Signal-Handling (Datei + API).
  - Prüfen ob compiled `update.exe` noch file-basiertes Signaling verwendet.

### 3. Dokumentation (Hoch)
> Aktuelle README/GUIDE reflektieren noch v0.x-Architektur.

- [ ] **README.md für v1.0.0 aktualisieren**
- [ ] **GUIDE.md für v1.0.0 aktualisieren**
- [ ] **CHANGELOG für v1.0.0 finalisieren**

---

## 🔮 Post-v1.0.0

### Sicherheit (Mittel)
> API läuft standardmäßig auf localhost. Authentifizierung ist erst
> bei Netzwerk-Exposition nötig.

- [ ] **Mittel** — API-Authentifizierung (API-Key)
  - Localhost-Binding (bereits Default) + optionaler API-Key.
  - Wichtig bei `server_host: 0.0.0.0`, kein Release-Blocker.
- [ ] **Niedrig** — Spotify `client_secret`-Validierung

### Port-Konsolidierung & EventBus (Mittel)
> Plugins laufen noch als eigene Flask-Prozesse auf 7 Ports.

- [ ] **Mittel** — Plugin-Kommunikation über API zentralisieren
- [ ] **Mittel** — EventBus in Plugin-Kommunikation einbinden
- [ ] **Mittel** — Port-Manager (Port-Nutzung reduzieren)

### GUI (Mittel)
> GUI ist ein eigenes Projekt. Setzt stabile API voraus.

- [ ] **Mittel** — Tech-Stack festlegen (Tauri, Electron, pywebview)
- [ ] **Mittel** — First-Run-Setup-Wizard
- [ ] **Mittel** — Config-Editor (Formular)
- [ ] **Mittel** — Actions-Editor (.mca)
- [ ] **Mittel** — Dashboard (Status, Logs)
- [ ] **Mittel** — Plugin-Manager (enable/disable)
- [ ] **Niedrig** — Spotify-Setup-Assistent
- [ ] **Niedrig** — Overlay-Vorschau + Theme-Editor
- [ ] **Niedrig** — Minecraft-Server-Console (RCON)

### Build & Deployment (Niedrig)
- [ ] **Niedrig** — Totmodule identifizieren
- [ ] **Niedrig** — Hinweistext für v0.x-User
- [ ] **Niedrig** — `version.txt` automatisch prüfen
- [ ] **Niedrig** — Mindestanforderungen dokumentieren
- [ ] **Niedrig** — Rollback-Mechanismus dokumentieren
- [ ] **Niedrig** — Troubleshooting-Sektion erweitern

### Testing (Niedrig)
- [ ] **Niedrig** — SSE/WS-Integrationstests stabilisieren (blockiert durch TestClient)
