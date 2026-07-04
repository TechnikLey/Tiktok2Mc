# Plugin-übergreifende Kommunikation

Plugins können miteinander kommunizieren, ohne voneinander abhängig zu sein. Das System bietet zwei Mechanismen für die pluginübergreifende Kommunikation.

## Direkte Befehle

Mit der `send_command`-Methode kannst du einen Befehl an ein bestimmtes Plugin senden:

```python
self.send_command("timer", "pause", {})

self.send_command("win-counter", "add_win", {"amount": 1})
```

Das Ziel-Plugin empfängt den Befehl über seinen registrierten Handler:

```python
class WinCounterPlugin(BasePlugin):
    def __init__(self):
        super().__init__()
        self.register_handler("add_win", self._on_add_win)

    def _on_add_win(self, args):
        anzahl = args.get("amount", 1)
```

## Ereignisbasierte Kommunikation

Der empfohlene Weg für lose Kopplung ist die ereignisbasierte Kommunikation über den [Event-Command-Mapper](./ch05-02-event-command-mapper.md).

Ein Plugin veröffentlicht ein Event:

```python
self.api_post("/events", {
    "type": "mein-plugin.erreicht",
    "data": {"wert": 42}
})
```

In der `event_commands.yaml` wird festgelegt, was passieren soll:

```yaml
event_commands:
  mein-plugin.erreicht:
    - target: anderes-plugin
      command: reagieren
      args: {wert: 42}
```

### Warum ereignisbasiert?

1. **Keine direkten Abhängigkeiten**: Das sendende Plugin muss das Ziel-Plugin nicht kennen.
2. **Einfach erweiterbar**: Neue Reaktionen können hinzugefügt werden, ohne den Code zu ändern.
3. **Wartbar**: Die Verknüpfungen sind zentral in einer YAML-Datei dokumentiert.
4. **Wiederverwendbar**: Ein Event kann mehrere Aktionen in verschiedenen Plugins auslösen.

## Wann welcher Mechanismus?

| Situation | Mechanismus |
|---|---|
| Ein Plugin muss ein anderes direkt steuern | `send_command()` |
| Ein Plugin möchte ein Ereignis bekannt geben | EventBus + [Event-Command-Mapper](./ch05-02-event-command-mapper.md) |
| Mehrere Plugins sollen auf ein Ereignis reagieren | EventBus + [Event-Command-Mapper](./ch05-02-event-command-mapper.md) |
| Die Verbindung soll konfigurierbar sein | [Event-Command-Mapper](./ch05-02-event-command-mapper.md) |
