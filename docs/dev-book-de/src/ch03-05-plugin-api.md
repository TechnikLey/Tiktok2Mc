# Plugin-API

Die Plugin-API stellt alle öffentlichen Funktionen bereit, die dir bei der Entwicklung von Plugins zur Verfügung stehen. Die API ist so gestaltet, dass sie stabil bleibt, auch wenn sich die interne Implementierung ändert.

## Einstiegspunkt

Jedes Plugin definiert eine Klasse, die von der bereitgestellten Basisklasse erbt:

```python
from core.base_plugin import BasePlugin

class MeinPlugin(BasePlugin):
    PLUGIN_NAME = "mein-plugin"
```

Die Basisklasse übernimmt die gesamte Lebenszyklus-Verwaltung, Konfigurationsladung und API-Kommunikation.

## Plugin-Identität

Ein Klassenattribut ist für jedes Plugin erforderlich:

- **`PLUGIN_NAME`** – Muss exakt mit dem `name`-Feld in der `plugin.json` übereinstimmen.

## Konfiguration

| Eigenschaft | Beschreibung |
|---|---|
| `config` | Gibt die Plugin-Konfiguration aus der `config.yaml` zurück (Kopie, Änderungen wirken sich nicht auf die gespeicherte Konfiguration aus) |

## Zustandsverwaltung

| Eigenschaft / Methode | Beschreibung |
|---|---|
| `state` | Thread-sicherer Zugriff auf den Plugin-Zustand (Dictionary, lesen/schreiben) |
| `push_state()` | Sendet den aktuellen `state` an den API-Server. Der Server verteilt ihn per SSE an alle verbundenen Overlay-Clients. |

`push_state()` wird benötigt, damit Overlay-Clients (z. B. eine Browser-Quelle in OBS) den aktuellen Zustand in Echtzeit erhalten. Ohne diesen Aufruf sehen Overlay-Clients nur den initialen HTML-Inhalt.

## Overlay

| Methode | Beschreibung |
|---|---|
| `get_overlay_html()` | **Muss überschrieben werden**. Gibt den HTML-String für das Overlay zurück. Wird beim Start einmal aufgerufen, um das Fenster oder die Browser-Quelle zu initialisieren. |
| `register_overlay(html)` | Ersetzt das Overlay-HTML zur Laufzeit. Der neue HTML-String wird sofort an den API-Server übermittelt. |

Für Echtzeit-Updates nach der Initialisierung verwendest du nicht `register_overlay()`, sondern `push_state()` (siehe oben). `register_overlay()` ist nur nötig, wenn sich der HTML-Code selbst ändern soll.

## Kommunikation

| Methode | Beschreibung |
|---|---|
| `send_command(target, command, args)` | Sendet einen Befehl an ein anderes Plugin über die API |
| `api_post(path, data)` | Sendet eine HTTP-POST-Anfrage an die zentrale API (`http://127.0.0.1:29185/api/v1/...`) |
| `api_get(path, timeout)` | Sendet eine HTTP-GET-Anfrage an die zentrale API (`http://127.0.0.1:29185/api/v1/...`) |

## Befehls-Handler

| Methode | Beschreibung |
|---|---|
| `register_handler(command, callback)` | Registriert eine Handler-Funktion für einen Befehl |

Der Callback erhält ein Dictionary mit den Argumenten und wird ausgeführt, sobald der zugehörige Befehl eintrifft:

```python
def __init__(self):
    super().__init__()
    self.register_handler("player_death", self._on_death)

def _on_death(self, args):
    anzahl = args.get("amount", 1)
```

## Lebenszyklus

| Methode | Beschreibung |
|---|---|
| `on_tick()` | Wird einmal pro Sekunde vom Polling-Thread aufgerufen (optional überschreiben) |
| `on_command(command, args)` | Wird für Befehle ohne registrierten Handler aufgerufen (optional überschreiben) |
| `run()` | Startet den Polling-Thread (fragt regelmäßig neue Befehle ab), ruft `get_overlay_html()` auf und öffnet das pywebview-Fenster. **Muss** als letzte Zeile in `if __name__ == "__main__":` stehen. |

## Hilfsmethoden

| Eigenschaft | Beschreibung |
|---|---|
| `theme_style` | Gibt CSS-Variablen (`--background`, `--text`, etc.) aus dem aktuellen Plugin-Theme zurück, für die Overlay-Gestaltung |
| `gui_hidden` | `True`, wenn das GUI-Fenster versteckt ist (z. B. durch `--gui-hidden`) |
| `save_window_state(width, height)` | Speichert die Fenstergröße für den nächsten Start |

## Verzeichnisse

| Eigenschaft | Beschreibung |
|---|---|
| `self._data_dir` | Absoluter Pfad zum Datenverzeichnis des Plugins (für persistente Dateien wie JSON, SQLite). Das Verzeichnis bleibt über Plugin-Neustarts erhalten. |
| `self._plugin_dir` | Absoluter Pfad zum Plugin-Verzeichnis (neben `main.py`). Hier liegen `config.yaml` und `plugin.json`. |

```python
class MeinPlugin(BasePlugin):
    def __init__(self):
        super().__init__()
        daten_pfad = self._data_dir / "zustaende.json"
        journal_pfad = self._plugin_dir / "readme.txt"
```

## Ereignisse veröffentlichen

Um Ereignisse an den EventBus zu senden:

```python
self.api_post("/events", {
    "type": "mein.event.typ",
    "data": {"wert": 42}
})
```

Andere Plugins oder der Event-Command-Mapper können auf dieses Event reagieren – siehe [Events & Subscriptions](./ch03-06-events-and-subscriptions.md) und [Event-Command-Mapper](./ch05-02-event-command-mapper.md).

> [!NOTE]
> Die hier dokumentierte API ist die stabile, öffentliche Schnittstelle. Interne Methoden und Implementierungsdetails sind nicht Teil dieser API und können sich ohne Vorankündigung ändern.
