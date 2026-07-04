# Plugin-API

Die Plugin-API stellt alle öffentlichen Funktionen bereit, die dir bei der Entwicklung von Plugins zur Verfügung stehen. Die API ist so gestaltet, dass sie stabil bleibt, auch wenn sich die interne Implementierung ändert.

## Einstiegspunkt

Jedes Plugin definiert eine Klasse, die von der bereitgestellten Basisklasse erbt:

```python
from core.base_plugin import BasePlugin

class MeinPlugin(BasePlugin):
    PLUGIN_NAME = "mein-plugin"
    DEFAULT_PORT = 29195
```

Die Basisklasse übernimmt die gesamte Lebenszyklus-Verwaltung, Konfigurationsladung und API-Kommunikation.

## Plugin-Identität

Zwei Klassenattribute sind für jedes Plugin erforderlich:

- **`PLUGIN_NAME`** – Muss exakt mit dem `name`-Feld in der `plugin.json` übereinstimmen.
- **`DEFAULT_PORT`** – Ein eindeutiger Port für die HTTP-Kommunikation.

## Konfiguration

| Eigenschaft | Beschreibung |
|---|---|
| `config` | Gibt die Plugin-Konfiguration aus der `config.yaml` zurück |

## Zustandsverwaltung

| Eigenschaft / Methode | Beschreibung |
|---|---|
| `state` | Thread-sicherer Zugriff auf den Plugin-Zustand (lesen/schreiben) |
| `push_state()` | Veröffentlicht den aktuellen Zustand an die API |

## Overlay

| Methode | Beschreibung |
|---|---|
| `get_overlay_html()` | **Muss überschrieben werden**. Gibt den HTML-String für das Overlay zurück |
| `register_overlay(html)` | Registriert Overlay-HTML beim API-Server |

## Kommunikation

| Methode | Beschreibung |
|---|---|
| `send_command(target, command, args)` | Sendet einen Befehl an ein anderes Plugin |
| `api_post(path, data)` | Sendet eine HTTP-POST-Anfrage an die zentrale API |
| `api_get(path, timeout)` | Sendet eine HTTP-GET-Anfrage an die zentrale API |

## Befehls-Handler

| Methode | Beschreibung |
|---|---|
| `register_handler(command, callback)` | Registriert eine Handler-Funktion für einen Befehl |

Der Callback erhält ein Dictionary mit den Argumenten und wird im Polling-Thread ausgeführt:

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
| `on_tick()` | Wird einmal pro Sekunde aufgerufen (optional überschreiben) |
| `on_command(command, args)` | Wird für nicht registrierte Befehle aufgerufen (optional überschreiben) |
| `run()` | Haupt-Einstiegspunkt – startet alle Threads und das Overlay |

## Hilfsmethoden

| Methode | Beschreibung |
|---|---|
| `save_window_state(width, height)` | Speichert die Fenstergröße |
| `theme_style` | Gibt CSS-Variablen aus dem aktuellen Theme zurück |
| `gui_hidden` | `True`, wenn das GUI-Fenster versteckt ist |

## Ereignisse veröffentlichen

Um Ereignisse an den EventBus zu senden:

```python
self.api_post("/events", {
    "type": "mein.event.typ",
    "data": {"wert": 42}
})
```

> [!NOTE]
> Die hier dokumentierte API ist die stabile, öffentliche Schnittstelle. Interne Methoden und Implementierungsdetails sind nicht Teil dieser API und können sich ohne Vorankündigung ändern.
