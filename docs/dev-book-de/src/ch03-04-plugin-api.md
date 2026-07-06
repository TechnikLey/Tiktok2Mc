# Plugin-API-Referenz

Alle öffentlichen Methoden von `BasePlugin`, die dir bei der Entwicklung zur Verfügung stehen.

## Basisklasse

```python
from core.base_plugin import BasePlugin

class MeinPlugin(BasePlugin):
    PLUGIN_NAME = "mein-plugin"
```

## Pflicht-Attribute und -Methoden

### `PLUGIN_NAME: str`

Muss exakt mit dem `name`-Feld in der `plugin.json` übereinstimmen. Wird für API-Endpunkte, die CommandQueue und die Plugin-Registry verwendet.

### `get_overlay_html() -> str`

Muss überschrieben werden. Gibt den HTML-String für das Overlay zurück. Wird von `run()` beim Start einmal aufgerufen. Für Plugins ohne Overlay reicht eine minimale Rückgabe: `return "<html><body></body></html>"` oder `return ""`.

## Konfiguration

| Methode | Beschreibung |
|---------|--------------|
| `self.config` | Gibt eine **Kopie** des Config-Dicts zurück. Read-only. |

## Zustandsverwaltung

| Methode | Beschreibung |
|---------|--------------|
| `self.state` | Thread-sicherer Zugriff auf den Plugin-Zustand (Dictionary). Gibt eine Kopie zurück. |
| `self.state = {...}` | Ersetzt den gesamten State (thread-safe). |
| `self.push_state()` | Sendet den aktuellen State per `POST /plugins/{name}/state` an den API-Server → SSE → Browser. |

**Thread-Safety**: `self.state` (Property) ist thread-safe und sollte für Lese- und Schreibzugriffe aus parallelen Threads verwendet werden. Der direkte Zugriff auf `self._state["key"] = val` ist unter CPython durch die GIL für einzelne Zuweisungen atomar, aber nicht für zusammengesetzte Operationen:

```python
# Empfohlen: thread-safe über die Property
state = self.state
state["count"] = self._zaehler
self.state = state
self.push_state()

# Auch OK (einzelne Zuweisung, atomar unter GIL):
self._state["count"] = self._zaehler
self.push_state()  # liest über thread-safes self.state
```

> **Faustregel**: `self.state =` für zusammengesetzte Operationen (z. B. Inkrement, mehrere Felder gleichzeitig). `self._state[key] = val` ist nur für einzelne, atomare Zuweisungen geeignet.

## Overlay

| Methode | Beschreibung |
|---------|--------------|
| `self.register_overlay(html)` | Ersetzt das Overlay-HTML zur Laufzeit per `POST /plugins/{name}/overlay-html`. |
| `self.theme_style` | Gibt CSS-Variablen (`--background`, `--text`, `--accent`, `--muted`, `--danger`, `--separator`) als String zurück. |
| `self.gui_hidden` | `True`, wenn `--gui-hidden` gesetzt oder pywebview nicht installiert ist. |

## Kommunikation

| Methode | Beschreibung |
|---------|--------------|
| `self.send_command(target, command, args)` | Sendet Befehl an ein anderes Plugin per `POST /plugins/{target}/command`. Gibt `True`/`False` zurück. |
| `self.api_post(path, data)` | Sendet HTTP-POST an `http://127.0.0.1:29185/api/v1/{path}`. Gibt `True`/`False` zurück. |
| `self.api_get(path, timeout=5)` | Sendet HTTP-GET. Gibt das JSON-Objekt oder `None` bei Fehlern zurück. |

> [!NOTE]
> Die API-Basis-URL kann über die Umgebungsvariable `API_BASE_URL` überschrieben werden (z. B. für abweichende Host/Port-Konfiguration). Standard: `http://127.0.0.1:29185/api/v1`.

```python
# Befehl an Timer-Plugin senden
self.send_command("timer", "pause", {})

# Eigenes Event veröffentlichen
self.api_post("/events", {
    "type": "mein-plugin.erreicht",
    "data": {"count": 42}
})

# Plugin-Liste abfragen
plugins = self.api_get("/plugins")
```

## Befehls-Handler

```python
self.register_handler("befehl_name", callback)
```

Signatur des Callbacks: `callback(args: dict) -> None`

Fallback für nicht registrierte Befehle:

```python
def on_command(self, command, args):
    """Wird aufgerufen, wenn kein passender Handler existiert."""
    log.warning(f"Unbekannter Befehl: {command}")
```

## Lebenszyklus

### `run()`

Wird einmal aufgerufen, kehrt nicht zurück (blockiert bis zum Plugin-Ende). Führt aus:

1. Plugin-Status in `HealthMonitor` auf `RUNNING` setzen
2. `get_overlay_html()` abrufen und an API senden
3. Tick-Thread starten (`on_tick()` einmal pro Sekunde)
4. Polling-Thread starten (Long-Polling `?wait=1`)
5. pywebview-Fenster öffnen (optional)

### `on_tick()`

Wird einmal pro Sekunde vom Tick-Thread aufgerufen. Überschreibe sie für periodische Aufgaben (z. B. Timer-Countdown). Das Attribut `self._running` ist von `BasePlugin` vordefiniert; weitere Attribute müssen im `__init__` initialisiert werden:

```python
def __init__(self):
    super().__init__()
    self._remaining = 60  # Initialisierung vor on_tick()

def on_tick(self):
    if self._running and self._remaining > 0:
        self._remaining -= 1
        self.push_state()
```

**Threading-Hinweis**: `on_tick()` läuft im Tick-Thread. Handler laufen im Polling-Thread. `self._state` (direkter Zugriff) und `self.state` (Property) sind unter CPython für einzelne Zuweisungen sicher (GIL garantiert atomare dict-Operationen).

## Verzeichnisse

| Eigenschaft | Typ | Beschreibung |
|-------------|-----|--------------|
| `self._data_dir` | `Path` | Globales Datenverzeichnis: `<projekt>/data/`. **Alle Plugins teilen sich dieses Verzeichnis** — verwende plugin-spezifische Dateinamen. |
| `self._plugin_dir` | `Path` | Plugin-eigenes Verzeichnis (neben main.py). Enthält config.yaml und plugin.json. |

```python
# Persistenten Zähler speichern (plugin-spezifischer Dateiname!)
count_file = self._data_dir / f"{self.PLUGIN_NAME}_count.json"

# Config-eigene Dateien
theme_file = self._plugin_dir / "theme.json"
```

## Weitere Eigenschaften

| Eigenschaft | Beschreibung |
|-------------|--------------|
| `self.bg_color` | Hintergrundfarbe aus dem Theme (String) |
| `self.save_window_state(w, h)` | Speichert Fenstergröße für nächsten Start |

## Typischer Plugin-Lebenslauf

```
1. System startet → PluginWatcher scannt plugin.json
2. API-Server registriert Plugin in Registry
3. Benutzer aktiviert → Signal-Datei → Supervisor startet Subprozess
4. python main.py → if __name__ → MeinPlugin().run()
5. run() registriert Overlay, startet Threads
6. Polling-Thread empfängt Befehle → Handler wird aufgerufen
7. Benutzer deaktiviert → Signal-Datei → Supervisor beendet Prozess (SIGTERM)
```

> [!NOTE]
> Der Supervisor beendet den Plugin-Prozess per `SIGTERM`. Hintergrund-Threads sind als `daemon=True` gestartet und werden automatisch beendet. Für eigene Betriebsmittel (Dateien, Netzwerkverbindungen) `atexit`-Handler registrieren:
> ```python
> import atexit
> def cleanup():
>     self._file.close()
> atexit.register(cleanup)
> ```

## REST-API-Endpunkte (für Nicht-Python-Plugins)

Plugins in anderen Sprachen kommunizieren direkt per HTTP mit dem API-Server (`http://127.0.0.1:29185/api/v1/`):

| Methode | Pfad | Beschreibung |
|---------|------|--------------|
| `GET` | `/plugins` | Alle registrierten Plugins auflisten |
| `POST` | `/plugins/{name}/command` | Befehl an ein Plugin senden |
| `GET` | `/plugins/{name}/commands?wait=1` | Befehle vom System abholen (Long-Polling) |
| `POST` | `/plugins/{name}/state` | Plugin-Zustand aktualisieren (für SSE) |
| `GET` | `/plugins/{name}/stream` | SSE-Stream für Zustands-Updates |
| `POST` | `/plugins/{name}/overlay-html` | Overlay-HTML setzen |
| `GET` | `/plugins/{name}/overlay` | Overlay-HTML abrufen |
| `GET` | `/plugins/{name}/config` | Plugin-Konfiguration lesen |
| `PUT` | `/plugins/{name}/config` | Plugin-Konfiguration schreiben |
| `POST` | `/events` | Eigenes Event auf dem EventBus veröffentlichen |
| `GET` | `/health` | Health-Status des API-Servers |
| `GET` | `/diagnostics` | Diagnose-Report (alle Komponenten) |

**Authentifizierung**: Wenn `api_key` in der globalen `config.yaml` gesetzt ist, muss jeder Request den Header `X-API-Key: <key>` enthalten (gilt nur für Requests von außerhalb localhost).

**Basis-URL**: Standard `http://127.0.0.1:29185/api/v1/`, überschreibbar über die Umgebungsvariable `API_BASE_URL`.

## Nächstes Kapitel

Lerne, wie du [Events empfängst](./ch03-05-events-and-subscriptions.md) — sowohl von TikTok als auch über den Event-Command-Mapper.
