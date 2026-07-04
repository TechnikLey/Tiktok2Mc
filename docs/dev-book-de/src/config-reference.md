# Konfigurationsreferenz

Dieses Kapitel beschreibt die wichtigsten Konfigurationsmöglichkeiten des Systems. Die Konfiguration ist in mehrere Ebenen unterteilt.

## Globale Konfiguration (`config.yaml`)

Die globale `config/config.yaml` enthält systemweite Einstellungen:

```yaml
# RCON-Verbindung zum Minecraft-Server
rcon:
  host: "localhost"
  port: 25575
  password: ""

# TikTok-Verbindung
tiktok:
  username: ""

# Systemeinstellungen
api:
  host: "127.0.0.1"
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
