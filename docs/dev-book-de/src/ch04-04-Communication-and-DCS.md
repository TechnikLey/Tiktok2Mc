## Kommunikation und DCS (HTTP-basierte Inter-Plugin-Kommunikation)

### Concept: Warum HTTP zwischen Plugins?

Plugins arbeiten als **separate Prozesse** parallel. Kommunikation zwischen ihnen erfolgt über:
- **DCS (Direct Control System)**: HTTP-Requests zwischen Plugins (Port-basiert)
- **Webhooks**: HTTP-POST-Requests von externen Programmen (z.B. Minecraft)

DCS ist die **universelle Kommunikationsmethode** – alle Plugins unterstützen sie.

### Kommunikations-Pattern

```
┌──────────────┐       HTTP Request         ┌──────────────┐
│  Timer       ├───────────────────────────>│  WinCounter  │
│  Port 7878   │  POST /add?amount=1        │  Port 8080   │
│              │                            │              │
│              │       HTTP Response        │              │
│              │<───────────────────────────┤              │
│              │       "OK"                 │              │
└──────────────┘                            └──────────────┘
```

### DCS Request-Response Workflow

**Schritt-für-Schritt:**
1. Source-Plugin sendet HTTP-Request an `http://localhost:PORT/endpoint`
2. Target-Plugin empfängt Request, verarbeitet Aktion
3. Target antwortet mit JSON oder Status
4. Source-Plugin verarbeitet Response (ggf. Fehlerbehandlung)

**Wichtig:** Requests sollten **in Threads** erfolgen, sonst blockiert das aufrufende Plugin!

### Praktisches Beispiel: Timer ruft WinCounter auf

Im echten Code passiert genau das: Wenn der Timer bei 0 ankommt, sendet er einen HTTP-POST an den WinCounter, um einen Win hinzuzufügen.

**WinCounter (Server auf Port 8080):**
```python
@app.route("/add", methods=["POST"])
def add():
    win_manager_instance.add_win(int(request.args.get('amount', 1)))
    return "OK"
```

**Timer (Client):**
```python
WIN_PORT = cfg.get("WinCounter", {}).get("WebServerPort", 8080)
ADD_URL = f"http://localhost:{WIN_PORT}/add?amount=1"

class API:
    def on_timer_end(self):
        print(f"[ACTION] Timer 0 erreicht. Sende POST an {ADD_URL}")
        try:
            requests.post(ADD_URL, timeout=2)
        except Exception as e:
            print(f"[ERROR] Konnte Counter nicht erreichen: {e}")
```

### Port-Zuordnung im Projekt

Jedes Plugin hat seinen eigenen Port, definiert in `config.yaml`:

| Plugin | Port | Config-Key |
|--------|------|-----------|
| GUI | 5000 | `GUI.Port` |
| OverlayTxt | 5005 | `Overlaytxt.Port` |
| MinecraftServerAPI | 7777 | `MinecraftServerAPI.WebServerPort` |
| Timer | 7878 | `MinecraftServerAPI.WebServerPortTimer` |
| DeathCounter | 7979 | `MinecraftServerAPI.DEATHCOUNTER_PORT` |
| WinCounter | 8080 | `WinCounter.WebServerPort` |
| LikeGoal | 9797 | `Gifts.LIKE_GOAL_PORT` |

> [!IMPORTANT]
> Jeder Port muss **eindeutig** sein. Wenn zwei Plugins den gleichen Port nutzen, schlägt der Start fehl.

### Kritische Fehler vermeiden

| Fehler | Problem | Lösung |
|--------|---------|--------|
| Synchrone Requests im Main-Thread | GUI/Server blockiert | In Thread oder mit `timeout` arbeiten |
| Nicht erreichbare Plugins | "Connection refused" | Port prüfen, Plugin läuft noch nicht? |
| Timeout zu kurz | Request bricht ab | Min. `timeout=2` setzen |
| Request ohne Error-Handling | Absturz bei Fehler | Immer `try/except` nutzen |

---

### Server-Sent Events (SSE): Live-Updates an den Browser

Viele Plugins nutzen **Server-Sent Events** um ihre Daten in Echtzeit an OBS (Browser-Source) oder das pywebview-Fenster zu senden. Das Grundprinzip:

1. Browser öffnet eine persistente Verbindung zu `/stream`
2. Server sendet Daten über `yield` (kein `return`)
3. Browser aktualisiert sich automatisch bei neuen Daten

```python
@app.route("/stream")
def stream():
    q = Queue()
    manager.listeners.append(q)
    def event_stream():
        yield f"data: {json.dumps(manager.get_data())}\n\n"
        while True:
            data = q.get()
            yield f"data: {json.dumps(data)}\n\n"
    return Response(event_stream(), mimetype="text/event-stream")
```

Im Browser (JavaScript):
```javascript
const es = new EventSource("/stream");
es.onmessage = (e) => {
    const data = JSON.parse(e.data);
    document.getElementById('counter').innerText = data.count;
};
```

Dieses Muster wird von **DeathCounter**, **WinCounter**, **LikeGoal** und **OverlayTxt** verwendet.

---

### Webhooks: Events von Minecraft empfangen

Plugins können über einen `/webhook`-Endpoint Events von Minecraft empfangen. Das **MinecraftServerAPI**-Plugin im Minecraft-Server sendet HTTP-POST-Requests an alle konfigurierten URLs.

```python
@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    event = data.get("event")
    
    if event == "player_death":
        death_manager.add_death()
    elif event == "player_respawn":
        # Reaktion auf Respawn
        pass
    
    return {"status": "ok"}, 200
```

Die Webhook-URLs werden in `configServerAPI.yml` konfiguriert:
```yaml
webhooks:
  urls:
    - "http://localhost:7777/webhook"    # Main App
    - "http://localhost:7878/webhook"    # Timer
    - "http://localhost:7979/webhook"    # DeathCounter
    - "http://localhost:8080/webhook"    # WinCounter
```

> [!TIP]
> Für eine ausführliche Anleitung zur Webhook-Implementierung in eigenen Plugins siehe
> [Kapitel: Webhook-Events und Minecraft-Integration](./ch02-02-webhook-events-and-minecraft-integration.md).

---

### Zusammenfassung

| Kommunikationsweg | Richtung | Beispiel |
|-------------------|----------|----------|
| **DCS (HTTP-Requests)** | Plugin → Plugin | Timer ruft WinCounter `/add` auf |
| **SSE (Server-Sent Events)** | Plugin → Browser/OBS | DeathCounter aktualisiert Overlay |
| **Webhooks** | Minecraft → Plugin | `player_death` Event an DeathCounter |

- **DCS** = HTTP-basierte Inter-Plugin-Kommunikation
- **SSE** = Live-Updates an Browser-Source oder pywebview
- **Webhooks** = Events von externen Programmen empfangen
- **Ports** müssen eindeutig und in `config.yaml` konfiguriert sein
- **Fehlerbehandlung** mit `try/except` und `timeout` ist Pflicht

### → Weiter zu [Plugins in Streaming-Software einbinden](./ch04-05-Integrating-Plugins-into-Streaming-Software.md)