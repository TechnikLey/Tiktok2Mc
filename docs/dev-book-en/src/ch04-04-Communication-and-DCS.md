## Communication and DCS (HTTP-based Inter-Plugin Communication)

### Concept: Why HTTP Between Plugins?

Plugins work as **separate processes** in parallel. Communication between them occurs via:
- **DCS (Direct Control System)**: HTTP requests between plugins (port-based)
- **Webhooks**: HTTP POST requests from external programs (e.g. Minecraft)

DCS is the **universal communication method** – all plugins support it.

### Communication Pattern

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

**Step by step:**
1. Source plugin sends HTTP request to `http://localhost:PORT/endpoint`
2. Target plugin receives request, processes action
3. Target responds with JSON or status
4. Source plugin processes response (with error handling if necessary)

**Important:** Requests should be made **in threads**, otherwise the calling plugin will block!

### Practical Example: Timer Calls WinCounter

In real code, this is exactly what happens: when the timer reaches 0, it sends an HTTP POST to the WinCounter to add a win.

**WinCounter (server on port 8080):**
```python
@app.route("/add", methods=["POST"])
def add():
    win_manager_instance.add_win(int(request.args.get('amount', 1)))
    return "OK"
```

**Timer (client):**
```python
WIN_PORT = cfg.get("WinCounter", {}).get("WebServerPort", 8080)
ADD_URL = f"http://localhost:{WIN_PORT}/add?amount=1"

class API:
    def on_timer_end(self):
        print(f"[ACTION] Timer reached 0. Sending POST to {ADD_URL}")
        try:
            requests.post(ADD_URL, timeout=2)
        except Exception as e:
            print(f"[ERROR] Could not reach counter: {e}")
```

### Port Assignment in the Project

Each plugin has its own port, defined in `config.yaml`:

| Plugin | Port | Config key |
|--------|------|-----------|
| GUI | 5000 | `GUI.Port` |
| OverlayTxt | 5005 | `Overlaytxt.Port` |
| MinecraftServerAPI | 7777 | `MinecraftServerAPI.WebServerPort` |
| Timer | 7878 | `MinecraftServerAPI.WebServerPortTimer` |
| DeathCounter | 7979 | `MinecraftServerAPI.DEATHCOUNTER_PORT` |
| WinCounter | 8080 | `WinCounter.WebServerPort` |
| LikeGoal | 9797 | `Gifts.LIKE_GOAL_PORT` |

> [!IMPORTANT]
> Every port must be **unique**. If two plugins use the same port, startup will fail.

### Avoiding Critical Errors

| Error | Problem | Solution |
|-------|---------|----------|
| Synchronous requests in the main thread | GUI/Server blocked | Use threads or set `timeout` |
| Unreachable plugins | "Connection refused" | Check port, plugin may not be running yet |
| Timeout too short | Request aborts | Set at least `timeout=2` |
| Request without error handling | Crash on error | Always use `try/except` |

---

### Server-Sent Events (SSE): Live Updates to the Browser

Many plugins use **Server-Sent Events** to send their data to OBS (browser source) or the pywebview window in real time. The basic principle:

1. Browser opens a persistent connection to `/stream`
2. Server sends data via `yield` (not `return`)
3. Browser automatically updates itself with new data

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

In the browser (JavaScript):
```javascript
const es = new EventSource("/stream");
es.onmessage = (e) => {
    const data = JSON.parse(e.data);
    document.getElementById('counter').innerText = data.count;
};
```

This pattern is used by **DeathCounter**, **WinCounter**, **LikeGoal** and **OverlayTxt**.

---

### Webhooks: Receiving Events from Minecraft

Plugins can receive events from Minecraft via a `/webhook` endpoint. The **MinecraftServerAPI** plugin on the Minecraft server sends HTTP POST requests to all configured URLs.

```python
@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    event = data.get("event")
    
    if event == "player_death":
        death_manager.add_death()
    elif event == "player_respawn":
        # React to respawn
        pass
    
    return {"status": "ok"}, 200
```

The webhook URLs are configured in `configServerAPI.yml`:
```yaml
webhooks:
  urls:
    - "http://localhost:7777/webhook"    # Main App
    - "http://localhost:7878/webhook"    # Timer
    - "http://localhost:7979/webhook"    # DeathCounter
    - "http://localhost:8080/webhook"    # WinCounter
```

> [!TIP]
> For detailed instructions on how to implement webhooks in your own plugins, see
> [Chapter: Webhook Events and Minecraft Integration](./ch02-02-webhook-events-and-minecraft-integration.md).

---

### Summary

| Communication method | Direction | Example |
|----------------------|-----------|---------|
| **DCS (HTTP requests)** | Plugin → Plugin | Timer calls WinCounter `/add` |
| **SSE (Server-Sent Events)** | Plugin → Browser/OBS | DeathCounter updates overlay |
| **Webhooks** | Minecraft → Plugins | `player_death` event to DeathCounter |

- **DCS** = HTTP-based inter-plugin communication
- **SSE** = Live updates to browser source or pywebview
- **Webhooks** = Receive events from external programs
- **Ports** must be unique and configured in `config.yaml`
- **Error handling** with `try/except` and `timeout` is mandatory

### → Continue to [Integrating modules into streaming software](./ch04-05-Integrating-Plugins-into-Streaming-Software.md)
