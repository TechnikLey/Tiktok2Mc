# v1.0.0 — Entwicklungstodo

> **Ziel:** Stabiler v1.0.0-Release mit zentraler FastAPI-Architektur, entkoppelten Plugins.
> v1.0.0 bricht bewusst mit v0.x. Keine Kompatibilität.
>
> | Prio | Bedeutung |
> |------|-----------|
> | **Kritisch** | Blockiert das Release. Muss vor v1.0.0 fertig sein. |
> | **Hoch** | Sollte drin sein, ohne geht es mit Risiko. |
> | **Mittel** | Wichtig, aber kein Release-Blocker. |
> | **Niedrig** | Nice-to-have für v1.0.0. |

---

## ✅ Erledigt (aktueller Stand)

### API-Integration
- ✓ API-Server startet als Daemon-Thread in `start.py` vor Plugin-Discovery
- ✓ Health-Poll (10 s Timeout) vor `PluginLauncher.get_plugins()`
- ✓ Fallback-Modus bei API-Ausfall (startet ohne Plugins)

### Legacy-Cleanup
- ✓ `python/registry.py` gelöscht
- ✓ `PluginLauncher` API-only (kein Legacy-Fallback)
- ✓ `client.py` ohne Fallback auf Datei-Registry
- ✓ `--register-only` aus CLI entfernt
- ✓ Alle Plugin-`main.py`-Imports auf `core.api.client` umgestellt
- ✓ `get_root_dir()` für beliebige Exe-Tiefen gefixt
- ✓ `build.py`/`update.py` ohne `registry`/`plugin_updater`
- ✓ `services.py` ohne `read_plugin_registry()`
- ✓ `models.py` ohne `ImportLegacyResponse`/`validate_config_dict`
- ✓ `gui.py` (alt) entfernt
- ✓ `plugin_updater.py` entfernt (dead code)
- ✓ `build.py`/`upload.py` TOOL_VERSION → `v1.0.0`

### Testing & CI
- ✓ Tests: `pytest.ini`, `conftest.py`, 155 Testfälle (44 Validator + 111 API/Core)
- ✓ API-Integrationstests: Health, Config CRUD, Plugins CRUD, Events
- ✓ API-Fehlertests: Config 404 (missing), 500 (corrupt), Event-Validierung
- ✓ API-Validierung: Plugin-Felder (level, port, name) werden korrekt abgewiesen (422)
- ✓ Core-Tests: `normalize_config_version()`, `ApiService`, `PluginRegistry`, `PluginLauncher`, `load_config()`
- ✓ Core-Tests: EventBus (15 async), PluginAPIClient (14 HTTP-mocked), PluginLauncher (5 + 3 Bad-Response)
- ✓ Core-Tests: Validator (44 Tests — Brackets, Colons, Prefixes, Multiplier, File-I/O)
- ✓ Core-Tests: PluginRegistry Backup-Mechanismus, korrupte JSON-Wiederherstellung
- ✓ Core-Tests: ApiService Fallback-Pfad, korrupte YAML-Konfig
- ✓ CI-Workflow: `test.yml` (push/PR auf main, `pytest tests/`)
- ✓ Produktions-Bug behoben: `write_config()` ruft jetzt `_validate_config_schema()` auf
- ✓ Produktions-Bug behoben: `normalize_config_version()` verarbeitet einstellige Strings (`"7"` → `"0.7"`)

### Security
- ✓ CORS-Standard von `["*"]` auf `["http://127.0.0.1", "http://localhost"]` geändert
- ✓ Security-Warning bei `--host 0.0.0.0` in `run.py`
- ✓ CORS-Hinweis im API-Startup-Log

### Plugin-Entkopplung
- ✓ Timer: REST-API (`/start`, `/pause`, `/reset`, `/status`)
- ✓ Timer: `auto_win: false` (kein automatischer POST an WinCounter)
- ✓ Timer: `pause_on_death: false` (keine MinecraftServerAPI-Abhängigkeit)
- ✓ WinCounter: `decrement_on_death: false` (kein automatischer Death-Decrement)
- ✓ Alle Plugins standalone mit `false`-Defaults

### API-Finalisierung (Production Readiness)
- ✓ Alle 12 API-Routes haben konsistentes Error-Handling (try/except mit log + HTTPException)
- ✓ PluginRegistry: Versionierte JSON-Backups (`api_plugin_registry.json.v1.bak`, …)
- ✓ PluginRegistry: Graceful Recovery bei korrupter JSON-Datei
- ✓ PluginLauncher: JSONDecodeError + None-plugins-Feld abgesichert
- ✓ Port-Konstanten-Vereinheitlichung: `DEFAULT_PORT` aus `server.py` importiert
- ✓ `API_VERSION` in `models.py` zentral definiert (kein Circular Import mehr)
- ✓ Dead Code entfernt: `ErrorResponse`, `WSMessage` (unused models)
- ✓ Dead Code entfernt: `import_legacy`-Referenzen aus Registry-Docstring + Plugins-Route
- ✓ `start.py`: Breitere Exception-Behandlung beim Config-Laden + API-Thread-Fehler-Logging
- ✓ `PluginUpdateRequest`: level/port-Validierung (ge/le constraints)

### Konfiguration & Schema
- ✓ `config_version: 1.0` (semantische Versionierung MAJOR.MINOR)
- ✓ `normalize_config_version()` in `core/utils.py` (legacy int → `"0.x"`)
- ✓ API normalisiert on Read, upgraded on Write
- ✓ `update.py` verwendet `packaging.version.parse()` für Cross-Format-Vergleiche
- ✓ Alle Plugins standardmäßig deaktiviert (opt-in)
- ✓ Schema-Validierung in der API (Typen, Pflichtfelder, `enabled`-Bool)
- ✓ Versionierte Config-Backups (`config.yaml.v1.bak`, `.v2.bak`, …)
- ✓ Warnung bei unbekannten Top-Level-Keys (Tippschutz)

---

## ❌ Noch offen (nach Priorität)

### 1. Kritisch — Testing & Stabilität

> 155 Tests existieren (44 Validator + 111 API/Core).
> SSE/WS-Tests sind noch nicht stabil (TestClient-Stream-Limit).
> API-Finalisierung abgeschlossen: alle Routes haben Error-Handling,
> PluginRegistry hat Backup-Mechanismus, Launcher fängt JSON-Fehler.

- [ ] **Hoch** — SSE/WS-Integrationstests stabilisieren
  - SSE-Stream-Read mit Timeout und explizitem Close.
  - **Blockiert durch:** TestClient unterstützt Streaming nur begrenzt.

- [ ] **Hoch** — Plugin-Smoke-Tests
  - Jedes Plugin starten, Flask-Server antwortet, API erreichbar.

### 2. Kritisch — Update-System

> `update.py` wurde auf semantische Versionierung umgestellt, aber
> die Integration mit der API (Status, Update-Signal) fehlt.
> Der Updater arbeitet noch rein dateibasiert.

- [ ] **Kritisch** — Updater mit API kommunizieren lassen
  - API-Endpunkt für Update-Status (`GET /api/v1/update/status`)
  - Signal `update_signal.tmp` durch API-Call ersetzen
  - **Warum:** Datei-basiertes Signaling ist brüchig und nicht beobachtbar.

- [ ] **Hoch** — Update-Pfad v1.0.0 → v1.0.1 testen
  - Config-Whitelist, Version-Check, Signal-Handling.

### 3. Kritisch — Sicherheit

> Die API steuert Minecraft-Server und RCON. Lokaler Zugriff
> reicht fürs erste, aber absichern muss sein.

- [ ] **Kritisch** — API-Authentifizierung
  - Localhost-Binding (bereits Default) + optionaler API-Key.
  - **Warum:** `server_host: 0.0.0.0` exponiert die API ins Netzwerk.

- [ ] **Kritisch** — RCON-Passwort-Warnung prominent
  - Warnung im Log beim Start, wenn Standard-Password `ABC1234` gesetzt ist.

- [ ] **Hoch** — `server_host: 0.0.0.0`-Sicherheitshinweis
- [ ] **Hoch** — Spotify `client_secret`-Validierung

### 4. Hoch — Port-Konsolidierung & EventBus

> Plugins laufen noch als eigene Flask-Prozesse auf 7 Ports.
> Ziel: Plugin-Kommunikation über die API routen, Ports reduzieren.

- [ ] **Hoch** — Plugin-Kommunikation über API zentralisieren
  - Timer → WinCounter nicht per Direkt-HTTP, sondern über API-Proxy.
  - REST/EventBus als Vermittler zwischen Plugins.
  - **Warum:** Reduziert Port-Konflikte, entkoppelt Plugins.

- [ ] **Hoch** — EventBus in Plugin-Kommunikation einbinden
  - EventBus (async pub/sub) existiert, wird aber nur von der API selbst genutzt.
  - Plugins sollen Events publizieren/abonnieren können (z.B. `timer.expired`).

- [ ] **Hoch** — Port-Manager (Port-Nutzung reduzieren)
  - Aktuell: 1 API + 7 Plugin + Minecraft + RCON = 10+ Ports.
  - Ziel: API als Router, Ausnahme Minecraft (25565), RCON (25575), API (29185).

### 5. Hoch — Plugin-Manifest (plugin.json)

> API und zukünftiger Plugin-Manager brauchen verlässliche Metadaten.
> Aktuell werden Plugins nur über `.exe`-Scannen in `plugins/` entdeckt.

- [ ] **Hoch** — Plugin-Manifest einführen
  - `plugin.json` mit name, version, description, required_apis, ports.
  - **Warum:** Erlaubt Metadaten *vor* dem Plugin-Start.

- [ ] **Hoch** — Plugin-Discovery über Manifest
  - `PluginLauncher` liest `plugin.json` statt `.exe`-Scannen.

### 6. Mittel — GUI (frühestens nach stabiler API)

> GUI ist ein eigenes Projekt. Setzt stabile API, Plugin-Manifeste und
> Config-Validierung voraus. Kein v1.0.0-Blocker.

- [ ] **Mittel** — Tech-Stack festlegen
  - Tauri, Electron, pywebview — Entscheidung nach API-Stabilität.
  - Bundle-Größe, Wartbarkeit, Update-Fähigkeit.

- [ ] **Mittel** — First-Run-Setup-Wizard
- [ ] **Mittel** — Config-Editor (Formular)
- [ ] **Mittel** — Actions-Editor (.mca)
- [ ] **Mittel** — Dashboard (Status, Logs)
- [ ] **Mittel** — Plugin-Manager (enable/disable)
- [ ] **Niedrig** — Spotify-Setup-Assistent
- [ ] **Niedrig** — Overlay-Vorschau + Theme-Editor
- [ ] **Niedrig** — Minecraft-Server-Console (RCON)

### 7. Niedrig — Build & Deployment

- [ ] **Niedrig** — Totmodule identifizieren
  - Welche Teile von `start.py`, `main.py`, `server.py` werden durch die API abgelöst?
- [ ] **Niedrig** — Hinweistext für v0.x-User (keine Migration)
- [ ] **Niedrig** — `version.txt` automatisch prüfen
- [ ] **Niedrig** — Mindestanforderungen dokumentieren (Python 3.12+, RAM, Java)
- [ ] **Niedrig** — Rollback-Mechanismus dokumentieren
- [ ] **Niedrig** — Troubleshooting-Sektion erweitern

### 8. Niedrig — Dokumentation (nach Feature-Freeze)

- [ ] **Niedrig** — README.md + GUIDE.md für v1.0.0
- [ ] **Niedrig** — Entwicklerdokumentation (dev-book EN+DE)
- [ ] **Niedrig** — CHANGELOG für v1.0.0
- [ ] **Niedrig** — API-Dokumentation (OpenAPI/Swagger)
