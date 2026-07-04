# Plugin-übergreifende Kommunikation

Plugins können auf zwei Arten miteinander kommunizieren: direkt per `send_command` oder lose gekoppelt über den EventBus.

## Direkte Befehle: `send_command()`

```python
self.send_command("timer", "pause", {})
self.send_command("win-counter", "add_win", {"amount": 1})
```

Das Ziel-Plugin muss einen passenden Handler registriert haben:

```python
class TimerPlugin(BasePlugin):
    def __init__(self):
        super().__init__()
        self.register_handler("pause", self._on_pause)
        self.register_handler("start", self._on_start)

    def _on_pause(self, args):
        self._running = False
```

Intern ruft `send_command` die API auf: `POST /api/v1/plugins/timer/command` mit Body `{"command": "pause", "args": {}}`. Der API-Server legt den Befehl in die CommandQueue des Ziel-Plugins.

**Vorteil**: Einfach, direkt, synchron.
**Nachteil**: Erzeugt Abhängigkeit — Plugin A muss Plugin B kennen.

## Ereignisbasierte Kommunikation: EventBus + ECM

Der empfohlene Weg für lose Kopplung:

```python
# Plugin A veröffentlicht ein Event
self.api_post("/events", {
    "type": "timer.zero",
    "data": {}
})
```

In der `data/event_commands.yaml` wird definiert, was passiert:

```yaml
event_commands:
  timer.zero:
    - target: win-counter
      command: add_win
      args: {amount: 1}
```

**Vorteile**: Null Kopplung, zentrale Konfiguration, einfach erweiterbar.

## Workflow-Beispiel: TikTok-Gift → Timer → Win-Counter

```
tiktok.gift → Event-Command-Mapper → Timer (start, 60s)
    → Timer läuft ab → timer.zero wird veröffentlicht
    → Event-Command-Mapper → Win-Counter (add_win)
```

Konfiguration in `event_commands.yaml`:

```yaml
event_commands:
  tiktok.gift:
    - target: timer
      command: start
      args: {duration: 60}
  timer.zero:
    - target: win-counter
      command: add_win
      args: {amount: 1}
```

Kein Plugin enthält hardcodierte Verweise auf andere Plugins.

## Kommunikation zwischen Plugins und Hooks

Hooks können Events auslösen, die Plugins empfangen. Dazu nutzt der Hook `api.enqueue_trigger()` oder indirekt den Event-Command-Mapper. Plugins können nicht direkt Hooks aufrufen — Hooks sind nur für `$`-Befehle in der `actions.mca` gedacht.

## Zusammenfassung

| Situation | Mechanismus |
|-----------|-------------|
| Ein Plugin muss ein anderes direkt steuern | `send_command()` |
| Ein Event soll mehrere Plugins auslösen | EventBus + ECM |
| Die Verbindung soll konfigurierbar sein | EventBus + ECM |
| Lose Kopplung gewünscht | EventBus + ECM |

## Nächstes Kapitel

Lerne [Overlays & Zustand](./ch03-07-overlays-and-state.md) für Echtzeit-Updates im Browser oder OBS.
