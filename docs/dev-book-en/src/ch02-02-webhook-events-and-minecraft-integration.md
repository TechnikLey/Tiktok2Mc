# Receive events: webhook system

###  Event data flow

When something happens in Minecraft (player dies, login, etc.), the game plugin sends an **HTTP POST request** to your plugin. That's called a **Webhook**.

**Flow:**
```
Minecraft Event (player_death)
        ↓
Minecraft plugin checks configServerAPI.yml
        ↓
Sends HTTP POST → http://localhost:PORT/webhook
        ↓
Your plugin (@app.route("/webhook")) receives
        ↓
Your plugin processes & responds
```

### Available events

> [!NOTE]
> A **complete list of all events** can be found in the `configServerAPI.yml` in the project.
Here are a few examples:

* `player_death`
* `player_respawn`
* `player_join`
* `player_quit`
* `block_break`
* `entity_death`

### Webhook implementation: 3 steps

**1. Start Flask server (in the main thread)**
```python
from flask import Flask, request
app = Flask(__name__)

def start_server():
    app.run(host="127.0.0.1", port=8001, debug=False, threaded=True)

import threading
srv = threading.Thread(target=start_server, daemon=True)
srv.start()
```

**2. Define /webhook endpoint**
```python
@app.route("/webhook", methods=['POST'])
def webhook():
    try:
        data = request.json
        event_type = data.get("event")
        
        if event_type == "player_death":
            print(f"Player died: {data.get('player')}")
        elif event_type == "block_break":
            print(f"Block broken: {data.get('block')}")
        
        return {"status": "ok"}, 200
    except Exception as e:
        print(f"Webhook error: {e}")
        return {"status": "error"}, 500
```

**3. Register in config.yaml**
```yaml
MyPlugin:
  Enable: true
  WebServerPort: 8001
```

and in the `configServerAPI.yml`:
```yaml
  urls:
    - "http://localhost:7777/webhook"
    - "http://localhost:7878/webhook"
    - "http://localhost:7979/webhook"
    - "http://localhost:8080/webhook"
    - "http://localhost:8001/webhook" # Your webhook
```

### Complete example: DeathCounter

```python
from flask import Flask, request
import json
from pathlib import Path

app = Flask(__name__)
DATA_DIR = Path(".") / "data"
DEATHS_FILE = DATA_DIR / "deathcount.json"

# Load counter
if DEATHS_FILE.exists():
    with open(DEATHS_FILE) as f:
        death_count = json.load(f).get("count", 0)
else:
    death_count = 0

@app.route("/")
def index():
    return f"<h1>Death counter: {death_count}</h1>"

@app.route("/webhook", methods=['POST'])
def webhook():
    global death_count
    data = request.json
    
    if data.get("event") == "player_death":
        death_count += 1
        # Save
        with open(DEATHS_FILE, "w") as f:
            json.dump({"count": death_count}, f)
        print(f"[+] Deaths: {death_count}")
    
    return {"status": "ok"}, 200

if __name__ == '__main__':
    import threading
    threading.Thread(target=lambda: app.run(port=8001), daemon=True).start()
    input("Server is running. Enter to stop...")
```

## Integrate webhook into your plugin

To receive webhooks, you need an HTTP server in your plugin. **Flask** is perfect for this:

```python
from flask import Flask, request

app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def webhook():
    event_data = request.json
    event_type = event_data.get("event")
    
    if event_type == "player_death":
        print("Player has died!")
    elif event_type == "player_respawn":
        print("Player has respawned!")
    
    return "OK", 200
```

That is the minimum. Your plugin must:
1. **Start Flask** and listen on port X
2. **Provide** the `/webhook` endpoint
3. **Process the POST request** and react

### Practical example: The timer

The timer plugin reacts to two events:

```python
@app.route('/webhook', methods=['POST'])
def webhook():
    ev = request.json.get("event")
    if ev == "player_death":
        window.evaluate_js("resetTimer(); setPaused(true);")
    elif ev == "player_respawn":
        window.evaluate_js("setPaused(false);")
    return "OK"
```

If a player dies:
- Timer is reset
- Timer is paused

When a player respawns:
- Timer continues running

## Understanding the event payload

When an event arrives, the request looks like this:

```json
{
    "load_type": "INGAME_GAMEPLAY",
    "event": "player_death",
    "message": "Player died from fall damage"
}
```

Depending on `load_type` you can program different behaviors:

- **`INGAME_GAMEPLAY`**: The event is from the current game
- **`STARTUP`**: The event is at server startup
- Others: see `configServerAPI.yml`

## Configure webhook URL

Your plugin must have a port setting in the `config.yaml`. The `configServerAPI.yml` then calls this URL:

```yaml
# config.yaml
MinecraftServerAPI:
  WebServerPortDeathCounter: 7979
  WebServerPortTimer: 7878
```

The webhook URLs are then configured like this:

```yaml
# configServerAPI.yml
webhooks:
    urls:
    - "http://localhost:7979/webhook"    # DeathCounter
    - "http://localhost:7878/webhook"    # Timer
```

> [!IMPORTANT]
> The port must be unique! No other plugin is allowed to use the same port.

## Threading: Start Flask in the background

An important point: Your plugin continues to run after registration. If you call Flask's `app.run()` directly, it blocks everything afterwards.

The solution: Start Flask in a **thread**:

```python
import threading

def start_flask_server():
    app.run(host='127.0.0.1', port=7878, debug=False)

# In the main program:
flask_thread = threading.Thread(target=start_flask_server, daemon=True)
flask_thread.start()

# The rest of your code continues to run in parallel...
```

With `daemon=True` the thread will automatically end when your plugin exits.

## Error handling

Everything doesn't always work. A few important points:

1. **Webhook not working?**
   - Check that your port is set in `config.yaml`
   - Check that the URL in `configServerAPI.yml` is correct
   - Look in your log file

2. **Port already in use?**
   - Choose a different port or exit the other program

---

## Summary

- Webhooks are HTTP POST requests from Minecraft to your plugin
- Flask makes implementation easy
- The `/webhook` endpoint processes incoming events
- The port must be synchronized in `config.yaml` and `configServerAPI.yml`
- Threading is important so that the Flask server doesn't block everything

**Next chapter:** [Configuration and data storage](./ch02-03-configuration-and-data-storage.md)
