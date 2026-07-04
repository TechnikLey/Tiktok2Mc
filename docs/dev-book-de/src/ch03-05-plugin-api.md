# Plugin-API

Die Plugin-API stellt alle öffentlichen Funktionen bereit, die dir bei der Entwicklung von Plugins zur Verfügung stehen. Dieses Kapitel beschreibt nicht nur, *was* es gibt, sondern auch *wie* du es in der Praxis einsetzt.

## Einstiegspunkt

Jedes Plugin definiert eine Klasse, die von `BasePlugin` erbt:

```python
from core.base_plugin import BasePlugin

class MeinPlugin(BasePlugin):
    PLUGIN_NAME = "mein-plugin"
```

`BasePlugin` übernimmt die gesamte Lebenszyklus-Verwaltung: Konfigurationsladung, Overlay-Registrierung, Heartbeat, Threads und API-Kommunikation.

## Plugin-Identität

Ein Klassenattribut ist **Pflicht**:

- **`PLUGIN_NAME`** – String, muss exakt mit dem `name`-Feld in der `plugin.json` übereinstimmen. Das System identifiziert dein Plugin darüber. Ein Tippfehler führt dazu, dass das Plugin nicht startet, weil der Subprozess `POST /api/v1/plugins/register` mit einem anderen Namen aufruft als erwartet.

## Konfiguration

```python
cfg = self.config
milestones = cfg.get("milestones", [])
```

`config` gibt eine **Kopie** der Plugin-Konfiguration aus der `config.yaml` zurück (Python-Dict). Änderungen an dieser Kopie wirken sich **nicht** auf die gespeicherte Konfiguration aus – schreibe nie zurück in `self.config`.

Üblich: Konfiguration im `__init__` einmal auslesen und in Instanz-Variablen speichern:

```python
class MeinPlugin(BasePlugin):
    def __init__(self):
        super().__init__()
        cfg = self.config
        self._interval = cfg.get("interval", 10)
        self._farbe = cfg.get("theme", {}).get("background", "#000000")
```

## Zustandsverwaltung

| Eigenschaft / Methode | Beschreibung |
|---|---|
| `state` | Thread-sicherer Zugriff auf den Plugin-Zustand (Dictionary, lesen/schreiben) |
| `push_state()` | Sendet `state` per `POST /api/v1/plugins/{name}/state` an den API-Server |

Der Zustand ist ein Dictionary, das du nach Bedarf befüllst. Er wird auf zwei Wegen genutzt:

1. **SSE-Update**: Nach `push_state()` verteilt der API-Server den Zustand per Server-Sent Events an alle verbundenen Overlay-Clients (siehe [Overlays & Zustand](./ch03-08-overlays-and-state.md)).
2. **Heartbeat**: Jeder `push_state()`-Aufruf aktualisiert auch den Heartbeat-Zeitstempel in der Plugin-Registry.

Typisches Muster:

```python
class ZaehlerPlugin(BasePlugin):
    def __init__(self):
        super().__init__()
        self._zaehler = 0
        self.register_handler("inkrement", self._on_inkrement)

    def _on_inkrement(self, args):
        self._zaehler += args.get("schritt", 1)
        self._state["count"] = self._zaehler
        self.push_state()              # ← an API senden → SSE → Browser
```

**Wann `push_state()` aufrufen?** Immer dann, wenn sich der Zustand ändert und das Overlay aktualisiert werden soll. Rufe es nicht in `on_tick()` auf, wenn sich nichts geändert hat – das erzeugt unnötigen Traffic.

## Overlay

| Methode | Beschreibung |
|---|---|
| `get_overlay_html()` | **Muss überschrieben werden**. Gibt den HTML-String zurück. Wird von `run()` beim Start einmal aufgerufen. |
| `register_overlay(html)` | Ersetzt das Overlay-HTML zur Laufzeit per `POST /api/v1/plugins/{name}/overlay-html`. |

`get_overlay_html()` wird genau einmal beim Start aufgerufen. Für Echtzeit-Updates änderst du nicht das HTML, sondern rufst `push_state()` auf – der Client (Browser-JS) reagiert auf die SSE-Nachricht und aktualisiert den DOM.

`register_overlay(html)` brauchst du nur, wenn sich der HTML-Code selbst ändern soll (z. B. bei Theme-Wechsel). Für häufige Updates ist `push_state()` der richtige Weg.

## Kommunikation

| Methode | Beschreibung |
|---|---|
| `send_command(target, command, args)` | Sendet einen Befehl per `POST /api/v1/plugins/{target}/command` an ein anderes Plugin |
| `api_post(path, data)` | Sendet eine HTTP-POST an `http://127.0.0.1:29185/api/v1/{path}` |
| `api_get(path, timeout)` | Sendet eine HTTP-GET an `http://127.0.0.1:29185/api/v1/{path}` |

### send_command – Direkte Kommunikation

```python
# Timer-Plugin anweisen zu pausieren
self.send_command("timer", "pause", {})

# Win-Counter: einen Sieg hinzufügen
self.send_command("win-counter", "add_win", {"amount": 1})
```

Das Ziel-Plugin muss einen Handler registriert haben:

```python
class WinCounterPlugin(BasePlugin):
    def __init__(self):
        super().__init__()
        self.register_handler("add_win", self._on_add_win)

    def _on_add_win(self, args):
        anzahl = args.get("amount", 1)
        self._wins += anzahl
```

Intern ruft `send_command` `POST /api/v1/plugins/win-counter/command` mit dem Body `{"command": "add_win", "args": {"amount": 1}}` auf. Der API-Server legt den Befehl in die CommandQueue des Ziel-Plugins. Dessen Polling-Thread holt ihn bei der nächsten `GET /commands`-Abfrage ab.

### api_post / api_get – Direkter API-Zugriff

Diese Methoden geben dir Zugriff auf die gesamte REST-API:

```python
# Event veröffentlichen (siehe Events & Subscriptions)
self.api_post("/events", {
    "type": "mein-plugin.erreicht",
    "data": {"wert": 42}
})

# Plugin-Liste abfragen
plugins = self.api_get("/plugins")
```

Beide geben bei Erfolg das geparste JSON (Dict/Liste) zurück, bei Fehlern `False` (`api_post`) bzw. `None` (`api_get`). Prüfe immer die Rückgabewerte:

```python
result = self.api_post("/events", {"type": "test"})
if not result:
    log.warning("Event konnte nicht gesendet werden")
```

## Befehls-Handler

```python
self.register_handler("befehl_name", callback)
```

Der Callback wird im Polling-Thread aufgerufen, sobald der Befehl eintrifft. Signatur: `callback(args: dict) -> None`.

Typischer Einsatz im `__init__`:

```python
class TimerPlugin(BasePlugin):
    def __init__(self):
        super().__init__()
        self.register_handler("start", self._on_start)
        self.register_handler("pause", self._on_pause)
        self.register_handler("reset", self._on_reset)
        self.register_handler("set_time", self._on_set_time)
```

Die Namen (`"start"`, `"pause"`, etc.) sind frei wählbar. Sie müssen mit den `command`-Werten übereinstimmen, die andere Komponenten (Event-Command-Mapper, andere Plugins) verwenden.

Fallback für nicht registrierte Befehle:

```python
def on_command(self, command, args):
    """Wird aufgerufen, wenn kein Handler registriert ist."""
    log.warning(f"Unbekannter Befehl: {command}")
```

## Lebenszyklus

### `run()` – Der Haupt-Einstiegspunkt

`run()` wird **einmal** aufgerufen und kehrt nicht zurück, bis das Plugin beendet wird. Es führt in dieser Reihenfolge aus:

1. Gesundheits-Status auf `RUNNING` setzen
2. `get_overlay_html()` aufrufen und Overlay per `POST /api/v1/plugins/{name}/overlay-html` registrieren
3. Zwei Daemon-Threads starten:
   - **Tick-Thread**: Ruft `on_tick()` einmal pro Sekunde auf. Macht nebenbei alle 30 Sekunden einen Heartbeat (`GET /commands?wait=0`).
   - **Polling-Thread**: Ruft in einer Schleife `GET /api/v1/plugins/{name}/commands?wait=1` auf. Der Server blockt bis zu 30s, bis ein Befehl ansteht (Long-Polling). Bei Antwort wird der passende Handler aus `self._handlers` aufgerufen.
4. Wenn pywebview verfügbar und `--gui-hidden` nicht gesetzt: Fenster öffnen

```python
if __name__ == "__main__":
    TimerPlugin().run()   # ← startet alles
```

### `on_tick()` – Periodische Arbeit

Wird vom Tick-Thread einmal pro Sekunde aufgerufen. Nutze es für:

- Countdown-Logik (Timer-Plugin)
- Herunterzählen von Cooldowns
- Regelmäßige Zustands-Prüfungen

```python
def on_tick(self):
    if self._running and self._richtung == "down":
        self._remaining -= 1
        if self._remaining <= 0:
            self._on_zero()
        self.push_state()
```

**Achtung**: `on_tick()` läuft im Tick-Thread, nicht im Polling-Thread. Teile Daten (z. B. `self._state`) müssen thread-sicher sein – `BasePlugin` verwendet einen Lock für `state`.

## Verzeichnisse

| Eigenschaft | Typ | Beschreibung |
|---|---|---|
| `self._data_dir` | `Path` | Absoluter Pfad zum Datenverzeichnis des Plugins. Bleibt über Neustarts erhalten. Ideal für persistente Dateien. |
| `self._plugin_dir` | `Path` | Absoluter Pfad zum Plugin-Verzeichnis (neben `main.py`). Hier liegen `config.yaml` und `plugin.json`. |

```python
class MeinPlugin(BasePlugin):
    def __init__(self):
        super().__init__()
        self._daten_pfad = self._data_dir / "historie.json"
        self._journal = self._plugin_dir / "readme.txt"
```

**Wohin gehören welche Dateien?**

| Dateityp | Verzeichnis | Beispiel |
|---|---|---|
| Vom Benutzer bearbeitbar | `_plugin_dir` | `config.yaml`, `theme.json` |
| Vom Plugin erzeugt, dauerhaft | `_data_dir` | Datenbanken, Logs, Exporte |
| Vom Plugin erzeugt, temporär | System-Temp | Caches (nicht über `_data_dir`) |

## Weitere Eigenschaften

| Eigenschaft | Typ | Beschreibung |
|---|---|---|
| `theme_style` | `str` | Gibt CSS-Variablen (`--background`, `--text`, etc.) aus dem aktuellen Plugin-Theme zurück. Verwende das im Overlay-HTML für konsistente Gestaltung. |
| `gui_hidden` | `bool` | `True`, wenn `--gui-hidden` gesetzt oder pywebview nicht installiert ist. Prüfe das, wenn du das Overlay-Verhalten anpassen willst. |
| `save_window_state(w, h)` | Methode | Speichert Fensterbreite und -höhe für den nächsten Start. |

```python
def get_overlay_html(self) -> str:
    return f"""<!DOCTYPE html>
<html>
<head><style>
{self.theme_style}
    body {{ background: var(--background); color: var(--text); }}
</style></head>
<body>Inhalt</body>
</html>"""
```

## Ereignisse veröffentlichen

Um Ereignisse an den EventBus zu senden, damit andere Komponenten darauf reagieren können:

```python
self.api_post("/events", {
    "type": "mein-plugin.erreicht",
    "data": {"wert": 42}
})
```

Das Event wird im EventBus veröffentlicht. Folgende Komponenten können es empfangen:

- **Event-Command-Mapper**: Leitet es basierend auf `event_commands.yaml` an andere Plugins weiter
- **Event-Bridge**: Leitet es an Plugins mit passenden `event_subscriptions` weiter
- **SSE-Clients**: Browser-JS kann den EventBus-Stream abonnieren

Der Event-Typ sollte einen Namensraum enthalten (`mein-plugin.ereignis`), um Kollisionen zu vermeiden.

## Zusammenfassung: Typischer Lebenslauf eines Plugins

```
1. System startet → Plugin-Watcher scannt plugin.json
2. POST /api/v1/plugins/register (Metadaten hinterlegen)
3. Benutzer aktiviert → Signal-Datei → Subprozess starten
4. python main.py → if __name__ → PluginInstanz().run()
5. run():
   a. Overlay registrieren
   b. Tick-Thread starten (on_tick)
   c. Polling-Thread starten (GET /commands)
   d. GUI-Fenster öffnen
6. Polling-Thread empfängt Befehle → Handler aufrufen
7. Benutzer deaktiviert → Signal-Datei → Subprozess beenden
```

## Häufige Fehler

| Fehler | Ursache | Lösung |
|---|---|---|
| `on_tick()` läuft nicht | `run()` wurde nicht aufgerufen | Prüfe den `if __name__`-Block |
| `push_state()` ohne Wirkung | Overlay-HTML verwendet kein SSE | Füge `EventSource`-JS im HTML ein |
| `send_command()` schlägt fehl | Ziel-Plugin nicht aktiv | Aktiviere zuerst das Ziel-Plugin |
| `api_post()` gibt `False` zurück | API-Server nicht erreichbar | Prüfe, ob `python run.py` läuft |

> [!NOTE]
> Die hier dokumentierte API ist die stabile, öffentliche Schnittstelle. Interne Methoden (alle mit `_`-Präfix, die nicht in dieser Tabelle stehen) sind nicht Teil dieser API und können sich ohne Vorankündigung ändern.
