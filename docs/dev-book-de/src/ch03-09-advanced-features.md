# Fortgeschrittene Features

Dieses Kapitel beschreibt fortgeschrittene Muster für komplexe Plugin-Architekturen. Die hier vorgestellten Techniken sind für einfache Plugins nicht erforderlich.

## Ereignis-Milestones

Ein häufiges Muster ist das Auslösen von Ereignissen bei bestimmten Schwellenwerten. Das Death-Counter-Plugin demonstriert dies:

```python
class DeathCounterPlugin(BasePlugin):
    def __init__(self):
        super().__init__()
        cfg = self.config
        self._milestones = sorted({int(m) for m in cfg.get("milestones", [])})
        self._milestones_sent = set()

    def _on_death(self, args):
        for ms in self._milestones:
            if self._count >= ms and ms not in self._milestones_sent:
                self._milestones_sent.add(ms)
                self._maybe_signal("milestone", {"milestone": ms})

    def _maybe_signal(self, event_type, extra=None):
        data = {"count": self._count}
        if extra:
            data.update(extra)
        self.api_post("/events", {"type": f"death.{event_type}", "data": data})
```

## Timer-Plugins: Tick und Lebenszyklus

Das Timer-Plugin zeigt, wie periodische Arbeit und Lebenszyklus-Events implementiert werden:

```python
def on_tick(self):
    """Wird einmal pro Sekunde aufgerufen."""
    if self._running and self._direction == "down":
        self._remaining -= 1
        if self._remaining <= 0:
            self._on_zero()
    self.push_state()
```

## Kaskadierende Event-Weiterleitung

Der [Event-Command-Mapper](./ch05-02-event-command-mapper.md) kann Events über mehrere Stufen leiten. Ein Event kann einen Befehl an ein Plugin senden, das daraufhin ein weiteres Event veröffentlicht, das wiederum ein anderes Plugin steuert:

```
tiktok.gift → Timer (start) → timer.zero → Win-Counter (add_win)
```

Diese Kaskade wird komplett in der `event_commands.yaml` konfiguriert, ohne dass eines der Plugins die Kette kennen muss.

## Bedingte Ausführung

Ein Plugin kann je nach Konfiguration unterschiedlich reagieren:

```python
signal_on = set(cfg.get("signal_on", ["milestone"]))
if "started" in signal_on:
    self.api_post("/events", {"type": "timer.started", "data": {...}})
```

Dies ermöglicht es Benutzern, das Verhalten des Plugins über die Konfiguration zu steuern, ohne den Code zu ändern.

## Sichere Zustandsspeicherung

Für Daten, die über Plugin-Neustarts hinaus erhalten bleiben sollen, empfiehlt sich eine separate Zustandsdatei:

```python
class MeinManager:
    def __init__(self, pfad):
        self._pfad = pfad
        self._daten = {}
        self._laden()

    def _laden(self):
        if self._pfad.exists():
            try:
                self._daten = json.loads(self._pfad.read_text(encoding="utf-8"))
            except Exception:
                pass

    def speichern(self):
        try:
            self._pfad.parent.mkdir(parents=True, exist_ok=True)
            self._pfad.write_text(
                json.dumps(self._daten, indent=4), encoding="utf-8"
            )
        except Exception:
            pass
```
