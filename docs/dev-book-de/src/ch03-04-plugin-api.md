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

### `get_dashboard_html() -> str`

Optional. Gibt eine vollständige HTML-Seite zurück, die das Web-Dashboard als Tab einbettet. Registriert wird sie nur bei nicht-leerer Rückgabe — deklariere zusätzlich `"dashboard_ui": true` in der `plugin.json`, damit der Tab erscheint. Siehe [Dashboard-Seiten](#dashboard-seiten).

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
| `self.theme_style` | Gibt die CSS-Variablen des Plugin-Themes als String zurück. Welche Variablen existieren, hängt vom `theme:`-Abschnitt der Plugin-Konfiguration ab (z. B. `--background`, `--text`, `--accent`). |
| `self.gui_hidden` | `True`, wenn `--gui-hidden` gesetzt ist. |

## Dashboard-Seiten

Plugins können eine eigene Seite im Web-Dashboard bereitstellen (Tab in der
Sidebar neben den festen Ansichten). Das ist Opt-in:

1. `"dashboard_ui": true` in der `plugin.json` deklarieren.
2. `get_dashboard_html()` überschreiben und ein vollständiges HTML-Dokument zurückgeben.

`run()` registriert die Seite dann automatisch (zur Laufzeit geht auch
`self.register_dashboard(html)`). Das Dashboard bettet sie als Iframe unter
`/api/v1/plugins/{name}/dashboard` ein; der Tab erscheint nur, solange das
Plugin aktiviert ist.

Da die Seite dieselbe Origin wie die API hat, funktionieren relative
`/api/v1/...`-Aufrufe — dieselben Bausteine wie bei Overlays:

- `EventSource("/api/v1/plugins/{name}/stream")` für Live-State (`push_state()`)
- `POST /api/v1/plugins/{name}/command` zum Auslösen eigener Command-Handler
- `GET/PUT /api/v1/plugins/{name}/data[/{key}]` für den persistenten Store

#### Dashboard-Seiten folgen dem GUI-Theme

Das Web-Dashboard lädt Plugin-Seiten mit einem `?theme=dark|light`
Query-Parameter und aktualisiert bereits geöffnete Tabs, wenn der Nutzer
Hell/Dunkel umschaltet. Die Seite sollte den Parameter auslesen und
entsprechende CSS-Variablen setzen, damit der Tab in beiden Modi lesbar
bleibt (die Overlay-Farben aus dem `theme:`-Config-Abschnitt sind für das
**Overlay-Fenster** gedacht, nicht für den Tab):

```html
<head>
  <script>
    (function () {
      var t = new URLSearchParams(location.search).get('theme');
      if (!t && window.matchMedia) {
        t = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
      }
      document.documentElement.setAttribute('data-theme', t || 'dark');
    })();
  </script>
  <style>
    /* erst self.theme_style, dann die GUI-Theme-Overrides */
    :root { --background: #f6f7f9; --text: #1b1e23; --accent: #4c8dff; }
    [data-theme="dark"] { --background: #15171c; --text: #e8eaed; --accent: #5a8dff; }
  </style>
</head>
```

Ohne Parameter (z. B. beim Öffnen in einem neuen Tab) gilt der Fallback auf
`prefers-color-scheme` wie oben gezeigt.

```python
class MyPlugin(BasePlugin):
    PLUGIN_NAME = "my-plugin"

    def get_dashboard_html(self) -> str:
        return """<!DOCTYPE html>
<html><body>
  <div id="out">...</div>
  <script>
    const es = new EventSource("/api/v1/plugins/my-plugin/stream");
    es.onmessage = (e) => { out.textContent = JSON.parse(e.data).value; };
  </script>
</body></html>"""
```

## Kommunikation

| Methode | Beschreibung |
|---------|--------------|
| `self.send_command(target, command, args)` | Sendet Befehl an ein anderes Plugin per `POST /plugins/{target}/command`. Gibt `True`/`False` zurück. |
| `self.query_plugin(target, query, args=None, timeout=5)` | Fragt ein anderes Plugin ab und gibt die geparste Antwort zurück (`{"id": ..., "result": ...}`), bei Timeout/Fehler `None`. Siehe [Plugins abfragen](#plugins-abfragen-requestresponse). |
| `self.api_post(path, data)` | Sendet HTTP-POST an `http://127.0.0.1:29185/api/v1/{path}`. Gibt `True`/`False` zurück. |
| `self.api_get(path, timeout=5)` | Sendet HTTP-GET. Gibt das JSON-Objekt oder `None` bei Fehlern zurück. |
| `self.api_request(path, payload=None, method=None, timeout=5)` | Vollwertiges Request/Response: gibt den **geparsten JSON-Body** zurück (`dict`/`list`/str/...), oder `None` bei leerem Body/Fehlern. Mit `payload=None` wird ein GET gesendet; mit Payload geht sie als JSON per POST (überschreibbar mit `method="PUT"` etc.). Wirft nie. |

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

# Request/Response mit Body-Zugriff (PUT + geparste Antwort)
result = self.api_request(
    "plugins/mein-plugin/data/counter",
    payload={"value": 42},
    method="PUT",
)
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

## Permissions (Pflicht)

Wie Hooks deklarieren Plugins, welche Fähigkeiten der Plugin-API sie nutzen.
Dazu eine `permissions`-Liste in der `plugin.json`:

```json
{
  "name": "mein-plugin",
  "permissions": ["store", "events"]
}
```

| Permission | Gewährt |
|------------|--------|
| `store` | `store_get`, `store_set`, `store_delete`, `store_all` |
| `network` | Generisches Control-Plane-HTTP: `api_get`, `api_post`, `api_put`, `api_delete`, `api_request` |
| `plugins` | Plugin-zu-Plugin-Kommunikation: `send_command`, `query_plugin` |
| `events` | `publish_event(type, data)` — Events auf den EventBus publizieren |

> [!IMPORTANT]
> **Default-Deny (Breaking Change seit v1.0.0):** Jeder gesperrte Helfer,
> dessen Familie nicht deklariert ist, wird mit seinem sicheren Rückgabewert
> abgelehnt (`False`/`None`/`{}`/Default) und als `PLUGIN-0020` geloggt;
> das Plugin läuft weiter. Deklariere genau das, was du nutzt.

Nicht gesperrt (immer verfügbar — das sind die eigenen Kernkanäle des
Plugins): Command-Polling und Handler, Heartbeat, `push_state`,
`register_overlay`, `register_dashboard`, `on_stop`.

Hinweise:

- Unbekannte Permission-Namen werden beim Start mit einer Warnung ignoriert.
- Permissions schützen nur die **BasePlugin-API-Oberfläche** — ein
  Plugin-Prozess ist volles Python und könnte weiterhin selbst Sockets öffnen.
  Für harte Isolation gibt es die
  [Sandbox-Profile](./ch03-02-plugin-structure.md#sandbox-profiles).
- Bevorzuge `publish_event` statt rohem `api_post("/events", ...)` — es
  braucht nur die `events`-Permission und validiert deinen Namespace
  (`"<plugin-name>.<ding>"`; reservierte Kernfamilien `tiktok.*`/
  `minecraft.*` werden serverseitig mit `403 API-0009` abgelehnt).

## Externe Netzwerk-Infrastruktur (Retry + Circuit-Breaker)

Für die Anbindung Dritter (Discord-Bots, Gameserver, externe APIs) bekommen
Plugins fertige Infrastruktur statt Eigenbau:

### `http_request(url, method="GET", *, headers=None, json_body=None, data=None, timeout=10.0, retries=2, retry_backoff=0.5)`

```python
resp = self.http_request(
    "https://api.example.test/v1/things",
    method="POST",
    json_body={"name": "x"},
)
if resp is None:
    ...  # Netzwerk erschöpft oder Breaker offen — Offline-Fall behandeln
elif resp["status"] >= 400:
    ...
else:
    payload = resp["json"]  # wird bei JSON-Antwort automatisch geparst
```

- Retries bei Verbindungsfehlern und `5xx` mit exponentiellem Backoff; `4xx`
  kehrt sofort zurück (Fehler des Aufrufers).
- Circuit-Breaker pro URL: Nach 5 aufeinanderfolgenden Fehlern wird die URL
  für 30 s lokal übersprungen (`None` statt tote Endpoint zu bombardieren);
  jeder Erfolg setzt ihn zurück.
- Liefert `{"status", "json", "text"}` für HTTP-Antworten, `None`, wenn die
  Anfrage nicht abgeschlossen werden konnte.

### `ws_connect(url, on_message, *, name=None, headers=None, reconnect_delay=5.0)` / `ws_close()`

Verwaltete WebSocket-Client-Threads mit Auto-Reconnect (nutzt das
mitgelieferte Paket `websocket-client`):

```python
def start(self):  # z. B. aus __init__ oder einem Command-Handler
    self.ws_connect(
        "wss://game.example.test/feed",
        self.on_game_message,
        name="game",
    )

def on_game_message(self, data):
    # data ist str (oder bytes); läuft im Client-Thread
    event = json.loads(data)
    ...

def on_stop(self):
    self.ws_close()  # alle Clients; ws_close("game") für einen
```

- Verbindet alle `reconnect_delay` Sekunden neu, bis geschlossen oder das
  Plugin herunterfährt (alle Clients werden beim Shutdown automatisch
  gestoppt).
- Handler-Exceptions sind isoliert und landen im Health-Monitor.
- Doppelter `name` während der Laufzeit → Rückgabe `False`.

> [!NOTE]
> Diese Helfer sind **nicht** permission-gesperrt: Ein Plugin-Prozess kann
> jederzeit selbst Sockets öffnen — ein Gate würde nur Reibung ohne echte
> Sicherheit erzeugen. Der Wert liegt in der gemeinsamen Retry-/Breaker-/
> Reconnect-Infrastruktur.

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

### `on_stop()`

Wird genau einmal aufgerufen, wenn das Plugin ordnungsgemäß heruntergefahren
wird — also beim Deaktivieren, Neustarten oder Löschen über Dashboard/API
(die API stellt dem Plugin vor dem Prozessstopp ein reserviertes internes
Kommando zu) sowie als `atexit`-Fallback beim normalen Interpreter-Ende.
Überschreibe es, um Queues zu leeren, Dateien/Verbindungen zu schließen
oder den finalen Zustand zu persistieren:

```python
def __init__(self):
    super().__init__()
    self._events: list[dict] = []

def on_stop(self):
    self.pending_events_flushen()
    self.push_state()
```

- Exceptions in `on_stop()` werden geloggt, verhindern aber nie den Exit.
- Das reservierte Shutdown-Kommando erreicht deine Command-Handler nie.
- Ein harter Kill (z. B. eingefrorener Prozess) kann `on_stop()` nicht
  ausführen — halte kritischen Zustand kontinuierlich über den persistenten
  Store (`store_set`) fest, nicht nur beim Herunterfahren.

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
7. Benutzer deaktiviert → API liefert Shutdown-Kommando → on_stop() läuft
   → Prozess beendet sich sauber (harter Stopp nur falls noch am Leben)
```

> [!NOTE]
> Disable/Restart/Unregister stellen dem Plugin zuerst ein reserviertes
> Shutdown-Kommando zu und warten kurz (~1 s Schonfrist), bevor das harte
> Stoppsignal geschrieben wird — so kann `on_stop()` den Zustand flushen.
> Hintergrund-Threads sind als `daemon=True` gestartet; eigene
> `atexit`-Handler brauchst du nicht mehr — überschreibe stattdessen
> `on_stop()` (siehe oben).

## REST-API-Endpunkte (für Nicht-Python-Plugins)

Plugins in anderen Sprachen kommunizieren direkt per HTTP mit dem API-Server (`http://127.0.0.1:29185/api/v1/`):

| Methode | Pfad | Beschreibung |
|---------|------|--------------|
| `GET` | `/plugins` | Alle registrierten Plugins auflisten (enthält pro Plugin das `queries`-Feld) |
| `GET` | `/plugins/queries` | Query-Discovery: alle deklarierten Query-Namen pro Plugin |
| `POST` | `/plugins/{name}/command` | Befehl an ein Plugin senden |
| `POST` | `/plugins/{name}/query` | Plugin abfragen (Request/Response — siehe unten) |
| `POST` | `/plugins/{name}/query-response` | Plugin-intern: Query-Antwort zustellen |
| `POST` | `/plugins/{name}/rpc` | Generischen Custom-Endpunkt des Plugins aufrufen (`on_rpc()`) — siehe unten |
| `GET` | `/plugins/{name}/commands?wait=1` | Befehle vom System abholen (Long-Polling) |
| `POST` | `/plugins/{name}/state` | Plugin-Zustand aktualisieren (für SSE) |
| `GET` | `/plugins/{name}/stream` | SSE-Stream für Zustands-Updates |
| `POST` | `/plugins/{name}/overlay-html` | Overlay-HTML setzen |
| `GET` | `/plugins/{name}/overlay` | Overlay-HTML abrufen |
| `POST` | `/plugins/{name}/dashboard-html` | Dashboard-Seiten-HTML setzen (Manifest: `dashboard_ui`) |
| `GET` | `/plugins/{name}/dashboard` | Dashboard-Seiten-HTML abrufen |
| `GET` | `/rcon/status` | RCON-Verbindungsstatus (read-only) |
| `POST` | `/rcon/command` | Minecraft-Befehl direkt ausführen (`{"command": "..."}`) — siehe unten |
| `GET` | `/plugins/{name}/config` | Plugin-Konfiguration lesen |
| `PUT` | `/plugins/{name}/config` | Plugin-Konfiguration schreiben |
| `POST` | `/events` | Eigenes Event auf dem EventBus veröffentlichen |
| `POST` | `/triggers/dispatch` | actions.mca-Trigger auslösen (ohne Debounce — siehe unten) |
| `POST` | `/events/ingest` | Namespaced Event publizieren und optional Trigger auslösen in einem Aufruf (siehe unten) |
| `GET` | `/plugins/{name}/data` | Kompletten Persistent Store des Plugins lesen |
| `GET` | `/plugins/{name}/data/{key}` | Einen Schlüssel aus dem Store lesen |
| `PUT` | `/plugins/{name}/data/{key}` | Schlüssel schreiben (Body: `{"value": <beliebiges JSON>}`) |
| `DELETE` | `/plugins/{name}/data/{key}` | Schlüssel aus dem Store löschen |
| `GET` | `/outbound/channels` | Outbound-Channels mit Status/Countern (URLs maskiert) |
| `POST` | `/outbound/channels/{name}/test` | Testnachricht durch einen Channel senden |
| `GET` | `/health` | Health-Status des API-Servers |
| `GET` | `/diagnostics` | Diagnose-Report (alle Komponenten) |

**Authentifizierung**: Wenn `api_key` in der globalen `config.yaml` gesetzt ist, muss jeder Request den Header `X-API-Key: <key>` enthalten (gilt nur für Requests von außerhalb localhost).

**Basis-URL**: Standard `http://127.0.0.1:29185/api/v1/`, überschreibbar über die Umgebungsvariable `API_BASE_URL`.

### Direkter RCON-Zugriff

`POST /api/v1/rcon/command` mit Body `{"command": "say hello"}` führt einen
Minecraft-Befehl **direkt** aus dem API-Prozess aus und gibt die Antwort des
Servers zurück (`{"response": "..."}`). Das ist derselbe Endpunkt, den die
Konsole im Web-Dashboard nutzt.

> [!WARNING]
> Anders als `!`-Zeilen in `actions.mca` umgeht dieser Pfad **RCON-Queue,
> Throttling und Retries der Bridge**. Für interaktive Abfragen und seltene
> Admin-Aktionen gedacht — nicht für häufige Trigger-Befehle. Er ist
> **standardmäßig deaktiviert** (`rcon.http_command_api: false` in der
> `config.yaml`, Sicherheits-/Stabilitäts-Standard); setze ihn auf `true`,
> um ihn zu aktivieren — der Konsole-Tab im Dashboard benötigt dies. Bei
> Deaktivierung werden direkte Befehle mit `403 MC-0012` abgelehnt,
> während der Queue-Pfad weiterarbeitet.

### Plugins abfragen (Request/Response)

Plugins können **serverseitige Abfragen** bereitstellen — Request/Response
mit Korrelations-IDs, z. B. ein Leaderboard, das auf `"top"` antwortet.
Das ist der unterstützte Weg, um strukturierte Daten *aus* einem
Plugin-Prozess zu lesen (Dashboard und andere Erweiterungen rufen es wie
einen normalen REST-Endpunkt auf):

1. `on_query(query, args) -> Any` in der Plugin-Klasse überschreiben. Der
   Rückgabewert wird JSON-serialisiert an den Aufrufer geliefert; eine
   Exception meldet einen Fehler.
2. Optional die unterstützten Query-Namen in der `plugin.json` unter
   `"queries": ["top", "stats"]` deklarieren — unbekannte Queries bekommen
   dann sofort einen 404 statt bis zum Timeout zu warten.

Aufrufer nutzen `POST /plugins/{name}/query` mit Body
`{"query": "top", "args": {}, "timeout": 5}` (Timeout geklemmt auf
0,5–30 s). Die Query wird über die Command-Queue als reservierter Befehl
`__query__` mit Korrelations-ID zugestellt; die Polling-Loop des
BasePlugin leitet sie automatisch an `on_query()` weiter und POSTet die
Antwort zurück. Python-Plugins rufen einfach
`self.query_plugin(target, query, args)` auf.

Antworten: `200 {"id": ..., "result": ...}` bei Erfolg; `504 PLUGIN-0018`,
wenn das Plugin nicht rechtzeitig antwortet; `502 PLUGIN-0019`, wenn der
Handler eine Exception wirft. Befehle (`!`-Zeilen, Reactions) bleiben
Fire-and-forget — Queries sind für Lesezugriffe mit Ergebnis da.

#### Query-Discovery

Da Queries ein bewusster Vertrag zwischen zwei Plugins sind, legt die API
offen, was existiert: `GET /plugins/queries` liest jede `plugin.json` und
liefert alle deklarierten Query-Namen inklusive Aktiv-Status des Plugins:

```json
{
  "total": 1,
  "plugins": [
    { "name": "deathcounter", "queries": ["deaths"], "enabled": true }
  ]
}
```

Plugins ohne `queries`-Deklaration werden weggelassen (ihre Queries
bekämen beim Aufruf ohnehin einen 404). Dieselbe Information liefert das
`queries`-Feld von `GET /plugins` pro Plugin. Der Aufruf einer nicht
deklarierten Query schlägt sofort mit einem 404 fehl, dessen Detail die
deklarierten Queries des Plugins auflistet — ein Tippfehler verrät also
sofort, was tatsächlich verfügbar ist.

```python
class MyPlugin(BasePlugin):
    PLUGIN_NAME = "leaderboard"

    def on_query(self, query: str, args: dict):
        if query == "top":
            scores = self.store_get("scores", {})
            top = sorted(scores.items(), key=lambda kv: -kv[1])[:10]
            return [{"user": u, "points": p} for u, p in top]
        return None
```

### Custom-Endpunkte (`on_rpc()` — generisches RPC)

Wenn die `commands`-/`queries`-Schemata nicht reichen, bekommt jedes Plugin
eine REST-artige Oberfläche — ganz ohne Server-Änderungen:

```python
def on_rpc(self, method: str, path: str, body: dict) -> Any:
    """Wird bei POST /api/v1/plugins/<name>/rpc aufgerufen."""
    if method == "POST" and path == "/songs":
        song = erstelle_song(body)
        return {"id": song.id}
    if method == "GET" and path.startswith("/songs/"):
        return finde_song(path.rsplit("/", 1)[1])
    raise ValueError(f"keine Route: {method} {path}")
```

Aufruf aus Dashboards, externen Tools oder anderen Plugins:

```json
POST /api/v1/plugins/spotify/rpc
{
  "method": "POST",
  "path": "/queue/play",
  "body": {"uri": "spotify:track:..."},
  "timeout": 5
}
```

- **Antwort**: `{"id": ..., "result": ...}` bei Erfolg; `504 PLUGIN-0018`
  bei Timeout; `502 PLUGIN-0019`, wenn `on_rpc()` eine Exception wirft.
- Die Zustellung nutzt denselben reservierten Befehlskanal wie Queries
  (`__rpc__`, Korrelations-ID über den Query-Store) und antwortet über den
  gemeinsamen Query-Response-Endpunkt.
- `method` ist GET/POST/PUT/DELETE/PATCH, `path` muss mit `/` beginnen und
  ist plugin-definiert, `body` ist ein optionales JSON-Objekt (leer bei GET).
- Der Rückgabewert muss JSON-serialisierbar sein; eine Exception meldet dem
  Aufrufer einen Fehler, ohne die Polling-Loop zu beenden.

### Persistenter Speicher (namespaced)
Jedes Plugin bekommt seine eigene JSON-Datei unter `data/plugin_data/<name>.json`
— das gemeinsame `data/`-Verzeichnis muss nicht mehr selbst angefasst werden, und
Kollisionen mit anderen Plugins sind ausgeschlossen. Schlüssel sind flache Strings
(`[A-Za-z0-9_.-]`, max. 128 Zeichen), Werte sind beliebiges JSON und überleben
Neustarts.

Python-Plugins nutzen die eingebauten Helfer auf `BasePlugin`:

```python
class MyPlugin(BasePlugin):
    PLUGIN_NAME = "leaderboard"

    def on_command(self, command, args):
        if command == "add_point":
            scores = self.store_get("scores", {})
            user = args.get("user", "?")
            scores[user] = scores.get(user, 0) + 1
            self.store_set("scores", scores)

        elif command == "reset":
            self.store_delete("scores")
```

Erweiterungen in anderen Sprachen nutzen normales HTTP:

```json
PUT /api/v1/plugins/leaderboard/data/scores.user-1
{"value": {"points": 10}}
```

> [!TIP]
> Lieber viele kleine Schlüssel als ein Riesen-Blob, wenn oft geschrieben wird —
> jeder Schreibvorgang schreibt die JSON-Datei des Namespace atomar neu.

### Trigger-Aktionen programmatisch auslösen

`POST /api/v1/triggers/dispatch` führt einen actions.mca-Trigger genau so aus,
als hätte das entsprechende TikTok-Event stattgefunden — ohne das Cooldown des
GUI-Event-Testers (`/triggers/execute`). Das ist der unterstützte Weg für
Erweiterungen, um actions.mca nach eigenem Zeitplan anzusteuern (Timer, Cron,
externe Integrationen):

```json
POST /api/v1/triggers/dispatch
{
  "trigger": "bonus_drop",
  "user": "System",
  "gift_id": null,
  "gift_name": null
}
```

- **trigger**: Action-Name aus der `actions.mca`, eine Gift-ID oder einer der
  eingebauten Event-Namen (`follow`, `like`, `join`, `share`, `comment`, `gift`)
- **user**: Benutzername, der als `{user}` eingesetzt wird (Standard `"System"`)
- **gift_id / gift_name**: Optional; für Gift-Trigger (`gift_id` ersetzt den
  Trigger-Namen auf der Leitung)
- **Antwort**: `{"status": "success", "trigger": ..., "user": ..., "message": ...}`
  — `status` ist `"error"` bei Validierungsfehlern oder nicht erreichbarer Bridge
- Der Aufruf wird **nicht** gedrosselt und **nicht** als Test-Event markiert;
  jeder Dispatch landet in der Trigger-History (`GET /triggers/history`)

### Generischer Event-Ingest (Bus + Trigger in einem Aufruf)

`POST /api/v1/events/ingest` ist der strukturierte Inbound für Erweiterungen
und externe Systeme (Spiele, OBS-Bots, Home Assistant, Automation). Er
publiziert ein namespaced Event auf den EventBus — erreicht also Plugins via
`event_subscriptions`, Hooks via `register_event`, den Outbound-Dispatcher
und den GUI-Livefeed — und löst optional im selben Aufruf eine
actions.mca-Triggerkette aus:

```json
POST /api/v1/events/ingest
{
  "type": "mygame.player_death",
  "data": {"player": "Notch", "level": 42},
  "trigger": "on_death",
  "user": "Notch"
}
```

| Feld | Pflicht | Bedeutung |
|-------|----------|---------|
| `type` | ja | Namespaced Event-Typ `<quelle>.<event>` (z. B. `mygame.player_death`) |
| `data` | nein | Freies Payload-Dict (Standard `{}`) |
| `trigger` | nein | actions.mca-Action-Name, der zusätzlich ausgeführt wird |
| `user` / `gift_id` / `gift_name` | nein | Payload für den optionalen Trigger; fällt auf die gleichnamigen `data`-Schlüssel zurück |

- **Antwort**: `{"status": "ok", "event": ..., "trigger": {...}}` — der
  `trigger`-Schlüssel erscheint nur, wenn ein Trigger ausgelöst wurde,
  und trägt dasselbe Format wie `/triggers/dispatch`.
- Reservierte Kernfamilien (`tiktok.*`, `minecraft.*`) werden abgelehnt
  (`403`, `API-0009`) — publiziere unter dem eigenen Namespace.
- Nutze diesen Endpunkt statt des Minecraft-branded Bridge-Webhooks, wenn du
  ein eigenes Spiel anbindest: keine Queue-Pause-Nebeneffekte, keine
  Namenskollisionen, volle Kontrolle über den Event-Namen.

### Outbound Webhooks

Der API-Prozess kann Live-Events an externe HTTP-Endpunkte weiterleiten
(„Outbound-Channels", z. B. Discord-Webhooks). Channels werden in der globalen
`config.yaml` unter `outbound.channels` konfiguriert; jeder Channel abonniert
per Event-Patterns (`tiktok.gift`, `tiktok.*`, `*`) mit denselben
Matching-Regeln wie Plugin-`event_subscriptions`:

```yaml
outbound:
  enabled: true          # Hauptschalter für alle Channels
  max_fails: 3           # Circuit Breaker: Fehler vor Cooldown
  cooldown: 10           # Circuit Breaker: Pause in Sekunden
  retries: 1             # zusätzliche Zustellversuche pro Nachricht
  timeout: 5             # HTTP-Timeout in Sekunden
  channels:
    - name: "discord-events"
      url: "https://discord.com/api/webhooks/..."
      events: ["tiktok.*"]
      format: discord    # discord | raw
      template: "**{user}** hat *{type}* ausgelöst"
      enabled: true
```

Zwei Payload-Formate werden unterstützt:

- **raw**: JSON-Envelope `{"type": "...", "data": {...}, "timestamp": ...}`
- **discord**: Discord-Webhook-Payload `{"content": "<Template>"}` — Templates
  unterstützen `{user}`, `{type}` und jeden Event-Daten-Platzhalter
  (`{comment}`, `{gift_id}`, ...); unbekannte Platzhalter werden zu leeren
  Strings

Jeder Channel hat seinen eigenen Circuit Breaker (gleicher Mechanismus wie bei
Overlays): Nach `max_fails` aufeinanderfolgenden Fehlzustellungen pausiert der
Channel für `cooldown` Sekunden und verwirft eingehende Events, statt sie zu
senden. Fehlgeschlagene Zustellungen werden `retries`-mal wiederholt
(jeweils 1 s Abstand). Status und Counter pro Channel sind über
`GET /api/v1/outbound/channels` abrufbar (URLs sind maskiert), ein manueller
Konnektivitätstest läuft über
`POST /api/v1/outbound/channels/{name}/test` — die Probe ignoriert
Event-Patterns und beeinflusst weder Circuit Breaker noch Counter.

### Benachrichtigungen

Der Notification-Dispatcher ist der einheitliche Weg, nutzergerichtete
Meldungen (Statusupdates, Warnungen, Ergebnisse) sichtbar zu machen, ohne
sich darum kümmern zu müssen, *wo* sie erscheinen. Sender geben **ihre
eigenen Channel-Einstellungen inline mit** — eine globale Konfiguration ist
nicht nötig. Plugins nutzen die `BasePlugin`-API-Helper:

```python
result = self.api_request("notifications", payload={
    "title": "Backup fertig",
    "channels": {
        "overlay": {"duration": 4},                    # OBS-Overlay-Text
        "sound":   {"file": "data/sounds/alert.wav"},  # .wav (Windows)
        "tts":     {"rate": 0},                        # Windows-SAPI-Sprache
        "discord": {"webhook_url": "https://discord.com/api/webhooks/..."},
    },
})  # -> {"sent": [...], "failed": [...], "skipped": [...]}
```

Für reines Fire-and-forget funktioniert auch
`self.api_post("notifications", {...})` — liefert dann nur einen
Erfolgs-Flag statt des Bodys.

Eingebaute Channels: `log` (immer verfügbar), `overlay`, `sound`,
`tts`, `discord`. Weitere Channel-Handler lassen sich in
`core/api/notification_dispatcher.py` registrieren (`CHANNEL_HANDLERS`) —
das System ist damit austauschbar statt auf eine feste Liste beschränkt.
Jeder Request trägt seine eigenen Parameter — verschiedene Aktionen können
so innerhalb einer Session **unterschiedliche Webhooks, Sounds oder
Overlays** ansprechen; jeder Aufruf ist unabhängig. (Optional kann ein
`notifications:`-Abschnitt in der globalen `config.yaml` Standard-Parameter
für Aufrufe bereitstellen, die nur einen Channel-Namen nennen — Plugins
verlassen sich nie darauf.)

Ohne `channels` wird an die optional global konfigurierten Channels
zugestellt (sonst `log`); unbekannte Channel-Namen loggen `NOTIF-0002` und
erscheinen als `skipped`. Ein Channel, der bei der Zustellung scheitert
(fehlende Datei, Webhook-Fehler, ...), wird als `failed` gemeldet (in den
API-Logs mit `NOTIF-0001`) — Zustellungsprobleme werfen nie Exceptions und
ändern nicht den HTTP-Status; du siehst sie nur in der Rückgabe
(`failed`/`skipped`).

#### Empfohlenes Muster: autarke Plugin-Einstellungen

Alle Versand-Einstellungen (Webhook-URL, Sound-Datei, Overlay-Dauer, ...)
über das eigene `config_schema` des Plugins anbieten, wie oben gezeigt
inline mitgeben und in der Plugin-README erwähnen („in den
Plugin-Einstellungen konfigurierbar") — Enduser kommen so nie mit YAML oder
der globalen Config in Berührung.

REST-Endpunkte: `POST /api/v1/notifications` (senden),
`GET /api/v1/notifications/channels` (Aktiv-Status + eingebaute/konfigurierte
Channels), `POST /api/v1/notifications/reload` (optionalen globalen
Config-Abschnitt neu einlesen).

## Nächstes Kapitel

Lerne, wie du [Events empfängst](./ch03-05-events-and-subscriptions.md) — sowohl von TikTok als auch über den Event-Command-Mapper.
