# Konfigurationsreferenz

Dieses Kapitel beschreibt die wichtigsten Konfigurationsmöglichkeiten des Systems. Die Konfiguration ist in mehrere Ebenen unterteilt.

## Globale Konfiguration (`config.yaml`)

Die globale `config/config.yaml` enthält systemweite Einstellungen:

```yaml
# Adresse, unter der die Bridge RCON erreicht (Bind-Adresse der Server)
server_host: "127.0.0.1"

# RCON-Verbindung zum Minecraft-Server
rcon:
  enabled: true
  port: 25575
  password: ""

# TikTok-Verbindung
tiktok:
  user: "dein_tiktok_name"

# Systemeinstellungen
api:
  port: 29185
```

## Plugin-Konfiguration

Jedes Plugin hat eine eigene `config.yaml` in seinem Verzeichnis:

```yaml
enabled: true
# Plugin-spezifische Einstellungen hier
```

Die verfügbaren Felder ergeben sich aus dem `config_schema` in der `plugin.json`.

## Hook-Konfiguration

Jeder Hook hat eine eigene `config.yaml` in seinem Verzeichnis:

```yaml
enabled: true
# Hook-spezifische Einstellungen hier
```

Die verfügbaren Felder ergeben sich aus dem `config_schema` in der `hook.json`.

## Event-Befehle (`event_commands.yaml`)

Diese Datei definiert, wie Events aus dem EventBus an Plugins weitergeleitet werden:

```yaml
event_commands:
  # Event-Typ:
  #   - target: Plugin-Name
  #     command: Befehl
  #     args: { ... }
  minecraft.player_death:
    - target: timer
      command: pause
  timer.zero:
    - target: win-counter
      command: add_win
      args: {amount: 1}
```

## Laufzeit-Dateien

Das System erzeugt und verwendet folgende Dateien zur Laufzeit:

| Datei | Zweck |
|---|---|
| `data/api_plugin_registry.json` | Persistierte Plugin-Registrierung |
| `data/hook_registry.json` | Persistierte Hook-Registrierung |
| `data/actions.mca` | Vom Benutzer bearbeitete actions.mca |
| `data/event_commands.yaml` | Vom Benutzer bearbeitete Event-Commands |
| `core/runtime/plugin_start_<name>` | Signal-Datei zum Starten eines Plugins |
| `core/runtime/plugin_stop_<name>` | Signal-Datei zum Stoppen eines Plugins |

## gifts.json Pfad (Entwicklung vs. Release)

- **Entwicklung**: `defaults/gifts.json` (Quelle im Repository)
- **Release/Installiert**: `core/gifts.json` (wird vom Build-System kopiert)

Der Code liest zuerst `core/gifts.json`, dann fällt er auf `defaults/gifts.json` zurück (siehe `src/core/api/routes/actions.py`).
