# Event-Command-Mapper

Der Event-Command-Mapper ist ein Dienst, der EventBus-Ereignisse auf Plugin-Befehle abbildet. Er ermöglicht lose Kopplung zwischen Komponenten.

## Konfiguration

Die Konfiguration erfolgt in der Datei `event_commands.yaml`:

```yaml
event_commands:
  minecraft.player_death:
    - target: timer
      command: pause
    - target: spotify-control
      command: pause
  timer.zero:
    - target: win-counter
      command: add_win
      args: {amount: 1}
```

## Funktionsweise

1. Ein Event wird auf dem EventBus veröffentlicht (z. B. `timer.zero`).
2. Der Event-Command-Mapper empfängt das Event.
3. Er sucht in der Konfiguration nach passenden Einträgen.
4. Für jeden Treffer sendet er einen Befehl an das Ziel-Plugin.

## Format

Jeder Eintrag besteht aus:

| Feld | Beschreibung |
|---|---|
| `target` | Name des Ziel-Plugins (aus der `plugin.json`) |
| `command` | Befehl, der an das Plugin gesendet wird |
| `args` | Optionale Argumente als Dictionary |

## Plugin-Entwicklung

Als Plugin-Entwickler musst du den Event-Command-Mapper nicht direkt ansprechen. Du erstellst Handler für die Befehle, die andere Komponenten an dein Plugin senden:

```python
self.register_handler("pause", self._on_pause)
self.register_handler("add_win", self._on_add_win)
```

Und du veröffentlichst Events, auf die andere Plugins reagieren können:

```python
self.api_post("/events", {
    "type": "mein-plugin.ereignis",
    "data": {...}
})
```

## Vorteile

- **Keine direkten Abhängigkeiten**: Plugins müssen einander nicht kennen.
- **Zentrale Konfiguration**: Alle Verknüpfungen sind in einer Datei dokumentiert.
- **Flexibel**: Neue Verknüpfungen können hinzugefügt werden, ohne Code zu ändern.
- **Erweiterbar**: Der Event-Command-Mapper wird automatisch beim Start geladen.
