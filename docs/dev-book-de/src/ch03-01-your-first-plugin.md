# Dein erstes Plugin

In diesem Tutorial erstellst du dein erstes Plugin. Es wird auf TikTok-Follow-Events reagieren und eine Nachricht ausgeben.

Du lernst dabei nicht nur den Code, sondern auch, wie ein Plugin im System lebt: wie es gestartet wird, wie es Befehle empfängt und wie Events von TikTok bis zu deinem Handler gelangen.

## Plugin erstellen

Das Projekt enthält ein Skript, das die Grundstruktur für ein Plugin erzeugt:

```bash
python create_plugin.py
```

Das Skript fragt nach:

- **Plugin-Name**: Nur Kleinbuchstaben und Ziffern, z. B. `hallo`
- **Update-URL**: Optional, für spätere Updates

Nach der Erstellung findest du dein Plugin unter `src/plugins/hallo/` mit folgender Struktur:

```
src/plugins/hallo/
├── plugin.json
├── main.py
├── config.yaml
├── version.txt
└── README.md
```

## Plugin-Code schreiben

Öffne `src/plugins/hallo/main.py` und ersetze den Inhalt:

```python
import logging
from core.base_plugin import BasePlugin

log = logging.getLogger(__name__)

class HalloPlugin(BasePlugin):
    PLUGIN_NAME = "hallo"

    def __init__(self):
        super().__init__()
        self.register_handler("tiktok_event", self._on_tiktok_event)
        self._last_user = ""

    def _on_tiktok_event(self, args):
        event_type = args.get("event_type", "")
        user = args.get("user", "")
        if event_type == "tiktok.follow":
            self._last_user = user
            log.info(f"{user} folgt jetzt!")

    def get_overlay_html(self) -> str:
        return "<html><body>Hallo Plugin!</body></html>"

if __name__ == "__main__":
    HalloPlugin().run()
```

### Was passiert hier Zeile für Zeile?

**Klasse und Identität**: `HalloPlugin` erbt von `BasePlugin`. Das Pflichtattribut `PLUGIN_NAME = "hallo"` muss exakt mit dem `name`-Feld in der `plugin.json` übereinstimmen – das System identifiziert dein Plugin darüber.

**Handler registrieren**: `self.register_handler("tiktok_event", self._on_tiktok_event)` speichert die Methode `_on_tiktok_event` intern in einem Dictionary (`self._handlers["tiktok_event"] = callback`). Wenn später ein Befehl namens `"tiktok_event"` für dieses Plugin eintrifft, ruft die Polling-Schleife diesen Callback mit den Argumenten auf.

**Der `if __name__ == "__main__"`-Block**: Das System startet jedes Plugin als **separaten Python-Subprozess** – z. B. `python src/plugins/hallo/main.py`. Dieser Block sorgt dafür, dass beim Ausführen der Datei eine Instanz erzeugt und `run()` aufgerufen wird. Ohne diesen Block würde der Subprozess einfach beenden und das Plugin wäre sofort tot.

### Was macht `run()`?

`run()` ist die Lebenszyklus-Methode von `BasePlugin`. Sie führt folgende Schritte aus:

1. **Registriert die Gesundheit**: Setzt den Plugin-Status auf `RUNNING` und zeichnet einen Heartbeat-Zeitstempel auf.
2. **Registriert das Overlay**: Ruft `get_overlay_html()` auf und sendet das HTML per `POST /api/v1/plugins/hallo/overlay-html` an den zentralen API-Server. Das Overlay wird dann unter `http://127.0.0.1:29185/api/v1/plugins/hallo/overlay` ausgeliefert.
3. **Startet zwei Hintergrund-Threads**:
   - **Tick-Thread**: Ruft `on_tick()` einmal pro Sekunde auf (überschreibbar) und sendet alle 30 Sekunden einen Heartbeat an den API-Server.
   - **Polling-Thread**: Fragt in einer Dauerschleife `GET /api/v1/plugins/hallo/commands?wait=1` ab. Das `?wait=1` aktiviert **Long-Polling**: Der Server blockt die Antwort bis zu 30 Sekunden, bis ein Befehl ansteht – das Plugin muss nicht busy-waiten.
4. **Öffnet das GUI-Fenster** (optional): Wenn pywebview installiert und `--gui-hidden` nicht gesetzt ist, öffnet es ein Fenster mit dem Overlay-HTML.

### Wie kommt ein TikTok-Event in deinen Handler?

Die Reise eines TikTok-Events durchläuft drei Prozesse:

```
TikTok Live          →   Bridge-Prozess          →   API-Server          →   Plugin-Prozess
(client empfängt)        (main.py)                   (FastAPI)                (hallo/main.py)
                              │                           │                        │
                         EventBus                   CommandQueue            Polling-Thread
                              │                           │                        │
                         Event-Bridge                wartet auf               GET /commands
                         Worker filtert              Befehle für                   │
                         nach event_sub-              "hallo"                 Handler wird
                         scriptions und               (long-poll)            aufgerufen
                         enqueuet "tik-
                         tok_event"
```

1. **Bridge-Prozess** (`src/python/main.py`): Der TikTokLive-Client empfängt ein Follow-Event. Der Bridge-Prozess veröffentlicht es auf dem **EventBus** (In-Memory Publish/Subscribe).
2. **Event-Bridge Worker**: Eine Hintergrundaufgabe im Bridge-Prozess abonniert alle Events vom EventBus. Für jedes TikTok-Event prüft sie, welche Plugins `"tiktok.follow"` (oder `"tiktok.*"`) in ihrer `plugin.json` unter `event_subscriptions` deklariert haben. Für jedes passende Plugin enqueued sie einen Befehl `"tiktok_event"` in die **CommandQueue** des API-Servers – mit den Event-Daten als Argumente.
3. **API-Server** (läuft im Supervisor-Prozess): Die CommandQueue hält für jedes Plugin eine Liste ausstehender Befehle bereit.
4. **Plugin-Prozess** (`hallo/main.py`): Der Polling-Thread fragt `GET /api/v1/plugins/hallo/commands?wait=1` ab. Sobald der `"tiktok_event"`-Befehl in der Queue liegt, liefert der Server ihn aus. Der Polling-Thread sucht in `self._handlers` nach dem Schlüssel `"tiktok_event"`, findet `self._on_tiktok_event` und ruft sie mit dem Argument-Dictionary auf.

### Was ist das Argument-Dictionary `args`?

Der Event-Bridge Worker erzeugt für jedes TikTok-Event ein Dictionary mit folgenden Feldern:

```python
{
    "event_type": "tiktok.follow",   # oder tiktok.gift, tiktok.comment, ...
    "user": "TikTokBenutzername",
    "data": {
        # Event-spezifische Felder, z. B. bei gift:
        # "gift_id": 5655,
        # "diamonds": 1,
    }
}
```

Dein Handler prüft `event_type`, um verschiedene Event-Typen zu unterscheiden.

## Manifest anpassen

Öffne `src/plugins/hallo/plugin.json` und passe es an:

```json
{
  "name": "hallo",
  "version": "1.0.0",
  "entry_point": "src/plugins/hallo/main.py",
  "display_name": "Hallo Plugin",
  "description": "Mein erstes Plugin",
  "author": "Dein Name",
  "min_api_version": "1.0.0",
  "capabilities": [],
  "depends_on": [],
  "config_schema": {
    "version": 1,
    "fields": []
  }
}
```

Das Feld `entry_point` zeigt dem System, welche Datei als Subprozess gestartet werden muss. Der Wert `src/plugins/hallo/main.py` wird später zum Befehl `python src/plugins/hallo/main.py`.

Zusätzlich musst du **Event-Subscriptions** deklarieren, damit die Event-Bridge dein Plugin beliefert. Füge das Feld `event_subscriptions` hinzu:

```json
{
  "name": "hallo",
  "event_subscriptions": ["tiktok.follow"]
}
```

Ohne diese Deklaration würde dein `tiktok_event`-Handler nie aufgerufen werden, weil die Event-Bridge dein Plugin nicht kennt.

## Plugin testen

Starte das System und aktiviere das Plugin:

1. **Starte TikTok2Mc**: `python run.py`
   Der Bridge-Prozess startet den API-Server und den Plugin-Watcher. Der Watcher scannt `src/plugins/*/plugin.json` und registriert jedes gefundene Plugin beim API-Server (`POST /api/v1/plugins/register`).

2. **Aktiviere das Plugin**: Ohne Aktivierung läuft der Subprozess nicht.
   ```bash
   curl -X PUT http://127.0.0.1:29185/api/v1/plugins/hallo/enable
   ```
   Der API-Server schreibt eine Signal-Datei `core/runtime/plugin_start_hallo`. Der Signal-Watcher erkennt sie und startet den Subprozess:
   ```
   python src/plugins/hallo/main.py
   ```
   Das Plugin ruft `HalloPlugin().run()` auf und beginnt mit dem Polling.

3. **Sende einen Test-Event**:
   ```bash
   python tests/send_trigger.py --event tiktok.follow --user TestUser
   ```
   Das Skript sendet `POST /api/v1/events` mit einem simulierten TikTok-Event an den EventBus. Der Event-Bridge Worker enqueued `"tiktok_event"` für dein Plugin. Der Polling-Thread empfängt es und ruft `_on_tiktok_event` auf.

4. **Prüfe die Ausgabe**: In der Konsole des Plugin-Prozesses sollte `TestUser folgt jetzt!` erscheinen. Wenn du das System im selben Terminal gestartet hast, siehst du die Ausgabe direkt. Andernfalls findest du sie im `logs/`-Verzeichnis.

### Plugin deaktivieren

Zum Stoppen des Plugins:
```bash
curl -X PUT http://127.0.0.1:29185/api/v1/plugins/hallo/disable
```

Der API-Server schreibt `core/runtime/plugin_stop_hallo`. Der Signal-Watcher beendet den Subprozess.

## Häufige Fehler

| Fehler | Ursache | Lösung |
|---|---|---|
| Plugin wird nicht erkannt | `plugin.json` fehlt oder `entry_point` falsch | Prüfe die JSON-Syntax und den Pfad |
| Plugin startet nicht | `PLUGIN_NAME` in `main.py` stimmt nicht mit `name` im Manifest überein | Korrigiere den Namen |
| Events kommen nicht an | `event_subscriptions` fehlt im Manifest | Füge `["tiktok.follow"]` oder `["tiktok.*"]` hinzu |
| `get_overlay_html()` fehlt | Wird von `run()` benötigt | Implementiere die Methode |
| `if __name__`-Block fehlt | Der Subprozess beendet sofort | Füge den Block am Ende hinzu |

## Nächste Schritte

Herzlichen Glückwunsch! Du hast dein erstes Plugin erstellt und verstehst, wie es im System lebt. Im nächsten Kapitel lernst du die [Plugin-Struktur](./ch03-02-plugin-structure.md) im Detail kennen.
