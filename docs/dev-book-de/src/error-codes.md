# Fehlercodes

Jeder Fehler im System hat einen stabilen, dokumentierten Code im Format `SUBSYSTEM-NNNN`.

## Subsysteme

| Präfix | Subsystem |
|--------|-----------|
| `CORE` | Allgemeine Laufzeit |
| `PLUGIN` | Plugin-System |
| `GUI` | Grafische Oberfläche |
| `API` | REST-API |
| `CONFIG` | Konfiguration |
| `OVERLAY` | Overlay-System |
| `HOOK` | Hook-System |
| `LIFECYCLE` | Prozess-Lebenszyklus |
| `MC` | Minecraft / RCON |
| `TIKTOK` | TikTok-Live-Verbindung |

## Schweregrade

| Stufe | Bedeutung |
|-------|-----------|
| `DEBUG` | Diagnose-Information |
| `INFO` | Normalbetrieb |
| `WARNING` | Potenzielles Problem |
| `ERROR` | Funktion eingeschränkt |
| `CRITICAL` | Schwerer Fehler |
| `FATAL` | Prozess wird beendet |

## Wichtige Fehlercodes

### HOOK (Hook-System)

| Code | Meldung | Beschreibung |
|------|---------|--------------|
| `HOOK-0001` | Hook directory not found | Hook-Verzeichnis existiert nicht |
| `HOOK-0002` | Invalid hook.json | `hook.json` fehlt oder ungültiges JSON |
| `HOOK-0003` | main.py not found | `main.py` fehlt im Hook-Verzeichnis |
| `HOOK-0004` | Missing required field | `name` oder `version` fehlt im Manifest |
| `HOOK-0005` | Disallowed import | Nicht erlaubtes Modul importiert |
| `HOOK-0006` | Unexpected load error | Allgemeiner Ladefehler |
| `HOOK-0007` | Missing register() function | `register()`-Funktion fehlt in main.py |

### PLUGIN (Plugin-System)

| Code | Meldung | Beschreibung |
|------|---------|--------------|
| `PLUGIN-0001` | Failed to initialize plugin | Plugin-Fehler in der Initialisierung |
| `PLUGIN-0002` | Plugin process crashed | Plugin-Subprozess abgestürzt |
| `PLUGIN-0003` | Plugin tick handler failed | `on_tick()` warf Exception |
| `PLUGIN-0004` | Plugin command handler failed | Handler warf Exception |
| `PLUGIN-0005` | Plugin dependency not met | `depends_on`-Plugin nicht aktiv |
| `PLUGIN-0006` | Plugin not found in registry | Plugin nicht registriert |
| `PLUGIN-0007` | API version mismatch | `min_api_version` nicht erfüllt |

### CONFIG (Konfiguration)

| Code | Meldung | Beschreibung |
|------|---------|--------------|
| `CONFIG-0001` | Config file not found | `config/config.yaml` existiert nicht |
| `CONFIG-0002` | Config file invalid | YAML-Syntax-Fehler |
| `CONFIG-0003` | Config healing applied | Fehlende Felder wurden repariert |
| `CONFIG-0004` | Plugin config not found | Plugin-`config.yaml` fehlt |
| `CONFIG-0005` | Plugin config invalid | Plugin-Konfiguration ungültig |

### MC (Minecraft / RCON)

| Code | Meldung | Beschreibung |
|------|---------|--------------|
| `MC-0001` | RCON connection failed | Verbindung zum Minecraft-Server fehlgeschlagen |
| `MC-0002` | RCON authentication failed | Falsches RCON-Passwort |
| `MC-0003` | RCON command failed | Befehl konnte nicht gesendet werden |
| `MC-0004` | RCON queue full | Warteschlange voll, Befehl verworfen |
| `MC-0005` | Server not running | Minecraft-Server läuft nicht |

### TIKTOK (TikTok-Live)

| Code | Meldung | Beschreibung |
|------|---------|--------------|
| `TIKTOK-0001` | Connection failed | Verbindung zum TikTok-Live fehlgeschlagen |
| `TIKTOK-0002` | Reconnecting | Automatische Wiederverbindung |
| `TIKTOK-0003` | Event parse error | TikTok-Event konnte nicht geparst werden |

### CORE (Allgemein)

| Code | Meldung | Beschreibung |
|------|---------|--------------|
| `CORE-0001` | Unhandled exception in main thread | Fatale Exception im Haupt-Thread |
| `CORE-0002` | Unhandled exception in worker thread | Exception in Hintergrund-Thread |
| `CORE-0003` | Resource not found | Datei oder Ressource nicht gefunden |
| `CORE-0004` | Operation timed out | Zeitüberschreitung |
| `CORE-0006` | Event bus queue full | EventBus-Queue voll, Event verworfen |
| `CORE-0008` | Heartbeat timeout | Komponente antwortet nicht |

## Fehler in Logs finden

Fehlercodes erscheinen im Log mit ihrem Code:

```
[ERROR] [HOOK-0005] Disallowed import: hook 'sprung' imports 'os'
```

Du kannst im gesamten Log nach `SUBSYSTEM-NNNN` suchen.
