# Interne-Plugin Kommunikation

### Plugins sprechen miteinander

Plugins laufen parallel. Manchmal braucht eines Daten von einem anderen:
- **Timer** fragt **DeathCounter**: "Wie viele Tode?"
- **WinCounter** triggert **Timer**: "Reset jetzt"

**Kommunikationswege:**
1. **HTTP-Requests** (Clean, async-ready) **EMPFOHLEN**
2. **Datei-Austausch** (Einfach, aber Race Conditions)
3. **WebSockets** (Realtime, komplex)

### HTTP-Pattern: Client-Server

```
┌──────────────┐ POST /api/action ┌──────────────┐
│   Plugin A   ├────────────────> │   Plugin B   │
│  (Client)    │  {action: "add"} │   (Server)   │
│   Port 8001  │                  │   Port 8002  │
│              │<─────────────────┤              │
│              │ {status: ok}     │              │
└──────────────┘                  └──────────────┘
```

### HTTP-Request: 3 Schritte

**Schritt 1: Server-Plugin (WinCounter)**

### Szenario: Timer ruft WinCounter auf

**WinCounter (Server):**
```python
@app.route('/add', methods=['POST'])
@app.route('/add', methods=['GET'])
def add_wins():
    amount = request.args.get('amount', 1, type=int)
    global win_count
    win_count += amount
    return json.dumps({"wins": win_count})
```

**Timer (Client):**
```python
import requests

WIN_PORT = cfg.get("WinCounter", {}).get("WebServerPort", 8080)
WIN_URL = f"http://localhost:{WIN_PORT}/add?amount=1"

try:
    response = requests.post(WIN_URL, timeout=3)
    if response.status_code == 200:
        print("Win hinzugefügt!")
except requests.exceptions.Timeout:
    print("WinCounter antwortet nicht")
except Exception as e:
    print(f"Fehler: {e}")
```

### Wichtige Punkte

**Ports in config.yaml definieren:**
```yaml
WinCounter:
  Enable: true
  WebServerPort: 8080

Timer:
  Enable: true
  WebServerPortTimer: 7878
```

**Timeout setzen:** Wenn das andere Plugin nicht lädt, wartet man nicht ewig.

**Fehlerbehandlung:** Das andere Plugin kann offline sein.

## 2. Datei-basierte Kommunikation

Plugins können sich über gemeinsame Dateien austauschen – z.B. eine JSON-Datei mit aktuellen Daten.

```python
# Plugin A schreibt:
data = {"total_wins": 42, "timestamp": time.time()}
with (DATA_DIR / "shared_state.json").open("w") as f:
    json.dump(data, f)

# Plugin B liest:
if (DATA_DIR / "shared_state.json").exists():
    with (DATA_DIR / "shared_state.json").open("r") as f:
        data = json.load(f)
        print(data["total_wins"])
```

**Vorteil:** Einfach, keine Netzwerk-Dependencies.

**Nachteil:** **Race Conditions** möglich! Wenn beide Plugins gleichzeitig schreiben, geht eine Änderung verloren.

**Best Practice:** Nur für selten geschriebene Daten oder Read-Only Zugriffe.

## 3. WebSockets (für Echtzeit-Kommunikation)

Wenn realtime Daten nötig sind, können Plugins über WebSockets kommunizieren. Das ist aber komplexer.

```python
# Mit python-socketio
from socketio import Server

sio = Server(async_mode='threading')

@sio.event
def send_update(data):
    print(f"Daten empfangen: {data}")

# In anderem Plugin:
import socketio
sio_client = socketio.Client()
sio_client.connect('http://localhost:9000')
sio_client.emit('send_update', {'kills': 5})
```

**Wann nutzen?** Nur wenn echte Echtzeit-Synchronisation wichtig ist.

## 4. Webhook-Kommunikation

Ein Plugin kann ein anderes Plugin vor bestimmten Events benachrichtigen, indem es seinen Webhook aufruft.

```python
# Plugin A sendet Event an Plugin B:
requests.post("http://localhost:7777/webhook", json={
    "event": "custom_event",
    "data": {"some": "data"}
})

# Plugin B empfängt:
@app.route('/webhook', methods=['POST'])
def webhook():
    event = request.json.get("event")
    if event == "custom_event":
        handle_custom_event(request.json.get("data"))
    return "OK"
```

**Vorteil:** Asynchron, flexibel.
**Nachteil:** Komplexer zu debuggen.

## Best Practice Patterns

### Pattern 1: Request-Response (synchron)

```python
# Client wartet auf Antwort
try:
    r = requests.get(f"http://localhost:8080/stats", timeout=2)
    stats = r.json()
except:
    stats = {}  # Fallback
```

**Nutzen:** Einfache, synchrone Abfragen (Zählerstände, Status, etc.)

### Pattern 2: Fire-and-Forget (asynchron)

```python
# Client sendet, wartet nicht auf Antwort
threading.Thread(
    target=requests.post,
    args=(f"http://localhost:8080/trigger", ),
    daemon=True
).start()
```

**Nutzen:** Wenn die Antwort egal ist (z.B. Events triggern).

### Pattern 3: Polling (regelmäßig abfragen)

```python
def poll_other_plugin():
    while running:
        try:
            r = requests.get(f"http://localhost:8080/status")
            process_status(r.json())
        except:
            pass
        time.sleep(5)  # Alle 5 Sekunden abfragen

threading.Thread(target=poll_other_plugin, daemon=True).start()
```

**Nutzen:** Regelmäßige, nicht-ständige Synchronisation.

## Error Handling Best Practices

```python
import requests

def call_other_plugin(url, data=None, timeout=3):
    try:
        if data:
            r = requests.post(url, json=data, timeout=timeout)
        else:
            r = requests.get(url, timeout=timeout)
        
        if r.status_code == 200:
            return r.json()
        else:
            print(f"Server antwortete mit {r.status_code}")
            
    except requests.exceptions.ConnectTimeout:
        print(f"Timeout: {url} antwortet nicht")
    except requests.exceptions.ConnectionError:
        print(f"Connection Error: {url} nicht erreichbar")
    except Exception as e:
        print(f"Unerwarteter Fehler: {e}")
    
    return None  # Fallback bei Fehler
```

---

## Zusammenfassung

- **HTTP-Requests:** Standard für Plugin-Kommunikation (synchron, zuverlässig)
- **Dateien:** Für persistente Daten, aber Vorsicht vor Race Conditions
- **WebSockets:** Nur wenn echte Echtzeit-Sync nötig
- **Fehlerbehandlung:** Immer timeout setzen und Fehler abfangen
- **Ports in config.yaml:** Zentral definieren, nicht hardcoden

**Nächstes Kapitel:** [Fehlerbehandlung und Best Practices](./ch02-06-error-handling-and-best-practices.md)
