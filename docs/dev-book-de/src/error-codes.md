# Fehlercodes

Jeder Fehler im System hat einen stabilen, dokumentierten Code im Format `SUBSYSTEM-NNNN`.

## Subsysteme

| Präfix | Subsystem |
|--------|-----------|
| `CORE` | Allgemeine Laufzeit / Infrastruktur |
| `PLUGIN` | Plugin-System |
| `GUI` | Grafische Oberfläche |
| `API` | REST-API / FastAPI |
| `NETWORK` | Netzwerk / HTTP / WebSocket |
| `CONFIG` | Konfigurationsladen / -validierung |
| `OVERLAY` | Overlay-Subsystem |
| `LIFECYCLE` | Prozess-Lebenszyklus / Supervisor |
| `MC` | Minecraft-Server / RCON |
| `TIKTOK` | TikTok-Live-Verbindung / Events |
| `HOOK` | Hook-System |
| `WATCHER` | Datei-/Verzeichnis-Watcher |
| `WORKER` | Hintergrund-Worker-Threads / -Tasks |
| `VALIDATE` | Validierungs-Subsystem |
| `DIAG` | Diagnose / Health |
| `SHUTDOWN` | Shutdown-Prozeduren |
| `STARTUP` | Start-Prozeduren |
| `SECURITY` | Authentifizierung / Sandbox |
| `BACKUP` | Backup-Subsystem |
| `UPDATE` | Update-Subsystem |
| `SANDBOX` | Plugin-Sandbox |
| `HEARTBEAT` | Heartbeat-Überwachung |

## Schweregrade

| Stufe | Bedeutung |
|-------|-----------|
| `DEBUG` (0) | Diagnose-Detail, keine Aktion nötig |
| `INFO` (1) | Normalbetrieb, informativ |
| `NOTICE` (2) | Normaler, aber bedeutsamer Zustand |
| `WARNING` (3) | Potenzielles Problem, sollte geprüft werden |
| `ERROR` (4) | Funktion eingeschränkt, Aktion erforderlich |
| `CRITICAL` (5) | Schwerer Fehler, sofortige Aufmerksamkeit nötig |
| `FATAL` (6) | Prozess wird beendet |

## Wichtige Fehlercodes

Die vollständige, maschinenlesbare Liste liefert `GET /api/v1/diagnostics/error-codes`.

### HOOK (Hook-System)

| Code | Meldung | Beschreibung |
|------|---------|--------------|
| `HOOK-0001` | Hook manifest missing or invalid | `hook.json` fehlt, ist unlesbar oder ungültig |
| `HOOK-0002` | Hook main.py not found | Im Hook-Verzeichnis fehlt `main.py` |
| `HOOK-0003` | Hook imports disallowed module | Der Hook importiert ein nicht erlaubtes Modul |
| `HOOK-0004` | Hook failed to load | `main.py` warf beim Laden eine Exception |
| `HOOK-0005` | Hook registration failed | Die `register()`-Funktion warf eine Exception |
| `HOOK-0006` | Hook script action failed | Eine Hook-Aktion warf während der Ausführung eine Exception |
| `HOOK-0007` | Hook has no register() function | `main.py` definiert keine `register()`-Funktion |
| `HOOK-0008` | Hook lifecycle callback failed | Ein `on_live_start`/`on_live_end`/`on_unload`-Callback warf eine Exception |
| `HOOK-0009` | Hook permission denied | Ein geschützter HookAPI-Aufruf fehlte den nötigen `permissions`-Eintrag in der `hook.json` |
| `HOOK-0010` | Hook timer callback failed | Ein `register_timer()`-Callback warf eine Exception; der Timer läuft weiter |

### PLUGIN (Plugin-System)

| Code | Meldung | Beschreibung |
|------|---------|--------------|
| `PLUGIN-0001` | Failed to initialize plugin | Plugin-Fehler in der Initialisierung |
| `PLUGIN-0002` | Plugin process crashed | Plugin-Subprozess unerwartet beendet |
| `PLUGIN-0003` | Plugin tick handler failed | `on_tick()` warf Exception |
| `PLUGIN-0004` | Plugin command handler failed | Command-Handler warf Exception |
| `PLUGIN-0005` | Plugin directory not found | Plugins-Verzeichnis fehlt oder ist nicht zugänglich |
| `PLUGIN-0006` | Plugin manifest invalid | `plugin.json` fehlt, ist unlesbar oder ungültig |
| `PLUGIN-0007` | Plugin disabled by configuration | Plugin ist per Registry/Konfiguration deaktiviert |
| `PLUGIN-0008` | Plugin sandbox violation detected | Plugin überschritt Sandbox-Grenzen |
| `PLUGIN-0009` | Plugin executable not found | Kompiliertes Plugin-Executable fehlt |
| `PLUGIN-0010` | Plugin discovery failed | Plugin-Erkennung fehlgeschlagen |
| `PLUGIN-0011` | Plugin health check failed | Plugin-Prozess gestorben oder nicht ansprechbar |
| `PLUGIN-0012` | Plugin failed to register overlay | Overlay-HTML konnte nicht registriert werden |
| `PLUGIN-0013` | Plugin state push failed | Zustand konnte nicht an die API gesendet werden |
| `PLUGIN-0014` | Plugin command fetch failed | Befehlsabruf von der API fehlgeschlagen |
| `PLUGIN-0015` | Plugin heartbeat missing | Plugin sendet keine Heartbeats mehr |
| `PLUGIN-0016` | Plugin failed to stop gracefully | Plugin stoppte nicht innerhalb des Timeouts |
| `PLUGIN-0017` | Plugin command queue full | Plugin-Command-Queue ist voll |
| `PLUGIN-0020` | Plugin permission denied | Ein gesperrter BasePlugin-Helfer wurde ohne passenden `permissions`-Eintrag in der `plugin.json` aufgerufen |
| `API-0009` | Reserved event type rejected | Reservierte Kern-Event-Familie ohne vertrauten Bridge-Marker publiziert |
| `API-0010` | Event payload violates declared schema | Fehlende Pflichtfelder oder falsche Typen gegenüber dem `data_schema` des Events |

### CONFIG (Konfiguration)

| Code | Meldung | Beschreibung |
|------|---------|--------------|
| `CONFIG-0001` | Configuration file not found | `config/config.yaml` existiert nicht |
| `CONFIG-0002` | Configuration file has invalid YAML syntax | YAML-Syntax-Fehler |
| `CONFIG-0003` | Configuration key missing, using default | Schlüssel fehlt, Standardwert wird verwendet |
| `CONFIG-0004` | Configuration validation warning | Konfigurationswert fiel durch die Validierung |
| `CONFIG-0005` | Runtime configuration reload failed | Reload zur Laufzeit fehlgeschlagen |
| `CONFIG-0006` | Duplicate command keys detected in config | Doppelte Schlüssel in commands_config |
| `CONFIG-0007` | Comment command prefix collision | Zwei Gruppen verwenden denselben Prefix |
| `CONFIG-0008` | Plugin configuration missing or invalid | Plugin-`config.yaml` konnte nicht geladen werden |

### MC (Minecraft / RCON)

| Code | Meldung | Beschreibung |
|------|---------|--------------|
| `MC-0001` | Minecraft server JAR not found | `server.jar` fehlt im Instanz-Verzeichnis |
| `MC-0002` | Java runtime not available | Kein Java 17+ verfügbar |
| `MC-0003` | Minecraft server exited with non-zero code | Server-Prozess beendete mit Fehlercode |
| `MC-0004` | RCON connection failed | RCON-Verbindung zum Server fehlgeschlagen |
| `MC-0005` | RCON command failed | RCON-Befehl gab einen Fehler zurück |
| `MC-0006` | RCON command dropped after retries | Befehl nach mehreren Versuchen verworfen |
| `MC-0007` | RCON queue full | RCON-Queue voll, Befehl verworfen |
| `MC-0008` | RCON password not set | RCON aktiv, aber kein Passwort konfiguriert |
| `MC-0009` | MinecraftServerAPI plugin disabled | MinecraftServerAPI-Plugin konnte nicht aktiviert werden |
| `MC-0010` | MinecraftServerAPI config failed to write | Schreiben der API-Konfiguration fehlgeschlagen |
| `MC-0011` | Minecraft server properties update failed | Schreiben von `server.properties` fehlgeschlagen |

### TIKTOK (TikTok-Live)

| Code | Meldung | Beschreibung |
|------|---------|--------------|
| `TIKTOK-0001` | TikTok Live connection failed | Verbindung zum TikTok-Live fehlgeschlagen |
| `TIKTOK-0002` | TikTok Live disconnected | Verbindung getrennt (Auto-Reconnect aktiv) |
| `TIKTOK-0003` | TikTok event handler failed | Event-Handler warf eine Exception |
| `TIKTOK-0004` | TikTok event publishing failed | Veröffentlichen auf dem EventBus fehlgeschlagen |
| `TIKTOK-0005` | TikTok bridge worker crashed | Bridge-Worker (Trigger/RCON/Event-Bridge) abgestürzt |

### CORE (Allgemein)

| Code | Meldung | Beschreibung |
|------|---------|--------------|
| `CORE-0001` | Unhandled exception in main thread | Fatale Exception im Haupt-Thread |
| `CORE-0002` | Unhandled exception in worker thread | Exception in Hintergrund-Thread |
| `CORE-0003` | Resource not found | Datei oder Ressource nicht gefunden |
| `CORE-0004` | Operation timed out | Zeitüberschreitung |
| `CORE-0005` | Failed to clean up resource | Aufräumen fehlgeschlagen |
| `CORE-0006` | Event bus queue full, dropping event | EventBus-Queue voll, Event verworfen |
| `CORE-0007` | State machine invalid transition | Ungültiger Zustandsübergang |
| `CORE-0008` | Heartbeat timeout detected | Komponente antwortet nicht |
| `CORE-0009` | Component health state changed | Health-Zustand einer Komponente änderte sich |

## Fehler in Logs finden

Fehlercodes erscheinen im Log mit ihrem Code:

```
[ERROR] [HOOK-0003] Hook imports disallowed module: hook 'sprung' imports 'os'
```

Du kannst im gesamten Log nach `SUBSYSTEM-NNNN` suchen.
