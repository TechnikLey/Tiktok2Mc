# Dein erstes Plugin

In diesem Tutorial erstellst du ein Plugin, das auf TikTok-Follow-Events und Gift-Events reagiert.

Der Code aus dem [Quickstart](./ch01-00-getting-started.md) wird hier erweitert.

## Das vollständige Beispiel

Ersetze `src/plugins/mein-plugin/main.py`:

```python
import logging
from core.base_plugin import BasePlugin

log = logging.getLogger(__name__)

class MeinPlugin(BasePlugin):
    PLUGIN_NAME = "mein-plugin"

    def __init__(self):
        super().__init__()
        cfg = self.config
        self._schwellwert = cfg.get("schwellwert", 10)

        self.register_handler("tiktok_event", self._on_tiktok_event)
        self.register_handler("count", self._on_count)

        self._zaehler = 0
        self._state["count"] = 0

    # -- TikTok-Events empfangen --

    def _on_tiktok_event(self, args):
        event_type = args.get("event_type", "")
        user = args.get("user", "")
        data = args.get("data", {})

        if event_type == "tiktok.follow":
            log.info(f"{user} folgt jetzt!")
            self._zaehler += 1
            self._state["count"] = self._zaehler
            self.push_state()

            if self._zaehler >= self._schwellwert:
                self.api_post("/events", {
                    "type": "mein-plugin.milestone",
                    "data": {"count": self._zaehler}
                })

        elif event_type == "tiktok.gift":
            gift_name = data.get("gift_name", "unbekannt")
            log.info(f"{user} sendete {gift_name}")

    # -- Befehle von anderen Plugins empfangen --

    def _on_count(self, args):
        self._zaehler += args.get("inkrement", 1)
        self._state["count"] = self._zaehler
        self.push_state()

    # -- Overlay --

    def get_overlay_html(self) -> str:
        ss = self.theme_style
        return f"""<!DOCTYPE html>
<html>
<head><style>
{ss}
    body {{ background: var(--background); color: var(--text); }}
    .count {{ font-size: 48px; }}
</style></head>
<body>
    <div class="count" id="counter">0</div>
    <script>
        const es = new EventSource("/api/v1/plugins/mein-plugin/stream");
        es.onmessage = (e) => {{
            const d = JSON.parse(e.data);
            document.getElementById("counter").innerText = d.count;
        }};
        es.onerror = () => {{
            es.close();
            setTimeout(() => {{ window.location.reload(); }}, 2000);
        }};
    </script>
</body>
</html>"""

if __name__ == "__main__":
    MeinPlugin().run()
```

## Wie es funktioniert

### 1. Plugin-Identität

`PLUGIN_NAME = "mein-plugin"` identifiziert das Plugin eindeutig. Der Wert muss mit dem `name`-Feld in der `plugin.json` übereinstimmen.

### 2. Handler registrieren

`self.register_handler("tiktok_event", self._on_tiktok_event)` speichert die Methode in einem internen Dictionary. Wenn der Polling-Thread einen Befehl empfängt, sucht er den passenden Handler und ruft ihn auf.

Die Namen der Handler sind frei wählbar. `"tiktok_event"` ist ein Standard-Name, den die Event-Bridge für TikTok-Events verwendet.

### 3. Konfiguration lesen

```python
cfg = self.config
self._schwellwert = cfg.get("schwellwert", 10)
```

`self.config` gibt eine Kopie der Konfiguration aus der `config.yaml` zurück.

### 4. Zustand verwalten

```python
self._state["count"] = self._zaehler
self.push_state()
```

`self._state` ist ein Dictionary, das du nach Belieben füllen kannst. `push_state()` sendet den aktuellen Zustand an den API-Server, der ihn per SSE an verbundene Browser verteilt.

### 5. Events veröffentlichen

```python
self.api_post("/events", {
    "type": "mein-plugin.milestone",
    "data": {"count": self._zaehler}
})
```

So löst du ein eigenes Event aus. Andere Plugins oder der Event-Command-Mapper können darauf reagieren.

## Der Lebenszyklus im Detail

`run()` (von `BasePlugin`) führt folgende Schritte aus:

1. **Gesundheit registrieren**: Plugin-Status auf `RUNNING` setzen
2. **Overlay registrieren**: `get_overlay_html()` aufrufen, HTML per `POST /plugins/{name}/overlay-html` an API senden
3. **Zwei Hintergrund-Threads starten**:
   - **Tick-Thread**: Ruft `on_tick()` einmal pro Sekunde auf. Sendet alle 30s einen Heartbeat (Polling mit `?wait=0`)
   - **Polling-Thread**: Ruft in Schleife `GET /plugins/{name}/commands?wait=1` (Long-Polling, Server blockt bis zu 30s). Bei Antwort: passenden Handler aus `self._handlers` aufrufen
4. **GUI-Fenster öffnen**: Wenn pywebview installiert und `--gui-hidden` nicht gesetzt

## Event-Daten der TikTok-Events

Die Event-Bridge liefert folgendes Dictionary an den `tiktok_event`-Handler:

```python
{
    "event_type": "tiktok.follow",   # oder tiktok.gift, tiktok.comment, ...
    "user": "TikTokBenutzername",     # TikTok-Benutzername
    "data": {                         # Event-spezifische Felder
        # Bei gift: gift_name, gift_id, count
        # Bei comment: comment (vollständiger Text)
        # Bei like: delta (Likes seit Session-Start), total
    }
}
```

Die Detailstruktur findest du in [Events empfangen](./ch03-05-events-and-subscriptions.md).

## Der Weg eines TikTok-Events zu deinem Handler

```
TikTok Live → TikTokLive-Client (Bridge-Prozess)
    → _publish_tiktok_event("follow", username)
    → HTTP POST /api/v1/events  {type: "tiktok.follow", data: {...}}
    → API-Server EventBus.publish("tiktok.follow", ...)
    → PluginEventBridge (API-Prozess, filtert nach tiktok.*)
    → command_queue.enqueue(plugin, "tiktok_event", event_type, user, data)
    → Plugin-Polling-Thread (GET /commands?wait=1)
    → self._handlers["tiktok_event"](args)
```

## Nächste Schritte

Jetzt kennst du den grundlegenden Lebenszyklus. Im nächsten Kapitel lernst du [Plugin-Struktur & Manifest](./ch03-02-plugin-structure.md) im Detail.
