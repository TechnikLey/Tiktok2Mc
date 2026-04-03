# Internal plugin communication

### Plugins talk to each other

Plugins run in parallel. Sometimes one needs data from another:
- **Timer** asks **DeathCounter**: "How many deaths?"
- **WinCounter** triggers **Timer**: "Reset now"

**Communication channels:**
1. **HTTP requests** (clean, async ready) **RECOMMENDED**
2. **File sharing** (simple, but race conditions)
3. **WebSockets** (real time, complex)

### HTTP pattern: client-server

```
┌──────────────┐ POST /api/action ┌──────────────┐
│   Plugin A   ├────────────────> │   Plugin B   │
│  (Client)    │  {action: "add"} │   (Server)   │
│   Port 8001  │                  │   Port 8002  │
│              │<─────────────────┤              │
│              │  {status: ok}    │              │
└──────────────┘                  └──────────────┘
```

### HTTP request: 3 steps

**Step 1: Server Plugin (WinCounter)**

### Scenario: Timer calls WinCounter

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
        print("Win added!")
except requests.exceptions.Timeout:
    print("WinCounter is not responding")
except Exception as e:
    print(f"Error: {e}")
```

### Important points

**Define ports in config.yaml:**
```yaml
WinCounter:
    Enable: true
    WebServerPort: 8080

Timer:
    Enable: true
    WebServerPortTimer: 7878
```

**Set timeout:** If the other plugin doesn't load, you don't have to wait forever.

**Error handling:** The other plugin can be offline.

## 2. File-based communication

Plugins can exchange information via shared files – e.g. a JSON file with current data.

```python
# Plugin A writes:
data = {"total_wins": 42, "timestamp": time.time()}
with (DATA_DIR / "shared_state.json").open("w") as f:
    json.dump(data, f)

# Plugin B reads:
if (DATA_DIR / "shared_state.json").exists():
    with (DATA_DIR / "shared_state.json").open("r") as f:
        data = json.load(f)
        print(data["total_wins"])
```

**Advantage:** Simple, no network dependencies.

**Disadvantage:** **Race conditions** possible! If both plugins write at the same time, a change will be lost.

**Best practices:** Only for rarely written data or read-only access.

## 3. WebSockets (for real-time communication)

If real-time data is required, plugins can communicate via WebSockets. But that is more complex.

```python
# With python socketio
from socketio import Server

sio = Server(async_mode='threading')

@sio.event
def send_update(data):
    print(f"Receive data: {data}")

# In another plugin:
import socketio
sio_client = socketio.Client()
sio_client.connect('http://localhost:9000')
sio_client.emit('send_update', {'kills': 5})
```

**When to use?** Only if true real-time synchronization is important.

## 4. Webhook communication

A plugin can notify another plugin of certain events by calling its webhook.

```python
# Plugin A sends event to Plugin B:
requests.post("http://localhost:7777/webhook", json={
    "event": "custom_event",
    "data": {"some": "data"}
})

# Plugin B receives:
@app.route('/webhook', methods=['POST'])
def webhook():
    event = request.json.get("event")
    if event == "custom_event":
        handle_custom_event(request.json.get("data"))
    return "OK"
```

**Advantage:** Asynchronous, flexible.
**Disadvantage:** More complex to debug.

## Best Practice Patterns

### Pattern 1: Request-Response (synchronous)

```python
# Client waits for response
try:
    r = requests.get(f"http://localhost:8080/stats", timeout=2)
    stats = r.json()
except:
    stats = {}  # Fallback
```

**Benefit:** Simple, synchronous queries (counter readings, status, etc.)

### Pattern 2: Fire-and-Forget (asynchronous)

```python
# Client sends, does not wait for response
threading.Thread(
    target=requests.post,
    args=(f"http://localhost:8080/trigger", ),
    daemon=True
).start()
```

**Benefit:** If the answer doesn't matter (e.g. trigger events).

### Pattern 3: Polling (query regularly)

```python
def poll_other_plugin():
    while running:
        try:
            r = requests.get(f"http://localhost:8080/status")
            process_status(r.json())
        except:
            pass
        time.sleep(5)  # Query every 5 seconds

threading.Thread(target=poll_other_plugin, daemon=True).start()
```

**Benefit:** Regular, non-permanent synchronization.

## Error handling best practices

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
            print(f"Server responded with {r.status_code}")
            
    except requests.exceptions.ConnectTimeout:
        print(f"Timeout: {url} not responding")
    except requests.exceptions.ConnectionError:
        print(f"Connection Error: {url} not reachable")
    except Exception as e:
        print(f"Unexpected error: {e}")
    
    return None  # Fallback on error
```

---

## Summary

- **HTTP requests:** Standard for plugin communication (synchronous, reliable)
- **Files:** For persistent data, but beware of race conditions
- **WebSockets:** Only if true real-time sync is necessary
- **Error handling:** Always set timeout and catch errors
- **Ports in config.yaml:** Define centrally, don't hardcode

**Next chapter:** [Error handling and best practices](./ch02-06-error-handling-and-best-practices.md)
