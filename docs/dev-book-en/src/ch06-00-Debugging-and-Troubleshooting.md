# Debugging & troubleshooting

Have you written your plugin but it doesn't work as expected? Here you will learn to find, understand and fix errors.

---

## Types of errors

Before we debug, we should know what error classes there are:

| Error type | Symptom | Example |
|-----------|---------|---------|
| **Syntax error** | Program doesn't start at all | `def foo(` – missing bracket |
| **Import error** | `ModuleNotFoundError` | Dependency not installed |
| **Runtime error** | Program crashes during execution | Division by 0 |
| **Logic error** | Program runs, but does the wrong thing | `if x = 5:` instead of `if x == 5:` |
| **Configuration error** | Settings are wrong | `config.yaml` has invalid YAML |

---

## Tool 1: Logs (The most important!)

### Where are the logs?

```
build/release/logs/
├── debug.log          # General debug logs
├── error.log          # Errors only
├── plugin_timer.log   # Plugin-specific logs
└── ...
```

### Understanding log levels

In the `config.yaml`:

```yaml
log_level: 2
```

> [!TIP]
> For development, set the level to `4`:

```yaml
log_level: 4
```

### Log output in your plugin

```python
import logging

logger = logging.getLogger(__name__)

logger.debug("Debug info for developers")
logger.info("General information")
logger.warning("Warning – could cause problems")
logger.error("An error has occurred")
logger.critical("CRITICAL error – program might crash")
```

**Example:**

```python
@app.route("/webhook", methods=["POST"])
def webhook():
    logger.info(f"Webhook received: {request.json}")
    
    try:
        process_event(request.json)
        logger.info("Event processed successfully")
    except Exception as e:
        logger.error(f"Error in event processing: {e}", exc_info=True)
        return {"error": str(e)}, 500
```

---

## Tool 2: Print Debugging

For quick tests you can also use `print()`:

```python
def on_gift(event):
    print(f"[DEBUG] Gift received: {event.gift.name}")
    print(f"[DEBUG] User: {event.user.nickname}")
    print(f"[DEBUG] Count: {event.repeat_count}")
```

**But be careful:** `print()` is **not** ready for production. Use `logging` for real applications.

---

## Tool 3: Try-Except Blocks

Catching and understanding errors:

```python
try:
    result = 10 / number  # Could be division-by-zero
except ZeroDivisionError:
    print("ERROR: Division by 0!")
    return None
except Exception as e:
    print(f"Unexpected error: {e}")
    return None
```

**Using traceback() for details:**

```python
import traceback

try:
    process_data(data)
except Exception as e:
    print(f"ERROR: {e}")
    traceback.print_exc()  # Shows the complete error stack
    logger.error(f"Error: {e}", exc_info=True)
```

---

## Tool 4: The Debugger (VS Code)

Visual Studio Code has a **built-in debugger**:

### Set breakpoints

1. Open your Python file
2. Click to the left of the line → red dot (breakpoint)
3. Start the program with `F5` (Debug mode)
4. When the line is reached → program pauses
5. Inspect variables, step through the code

### Debug controls

- `F10` – Next line (Step Over)
- `F11` – Go into function (Step Into)
- `Shift+F11` – Go out of function
- `F5` – Continue to the next breakpoint
- `Shift+F5` – Stop debugging

### Watch variables

On the right in the debug panel:

```
VARIABLES
├─ request
│   ├─ method: "POST"
│   ├─ json: {...}
│   └─ ...
├─ event
│   ├─ gift: {...}
│   └─ ...
```

You can inspect variables here without typing!

---

## Common Errors & Solutions

### 1. "ModuleNotFoundError: No module named 'TikTokLive'"

**Cause:** Dependency not installed.

**Solution:**
```bash
pip install -r requirements.txt
```

or

```bash
pip install TikTokLive Flask pywebview pyyaml
```

---

### 2. "Config error while loading"

**Cause:** `configuration.yaml` is not valid YAML.

**Test:**
```bash
python -c "import yaml; yaml.safe_load(open('config/config.yaml'))"
```

If errors → check YAML syntax (indentation, colons, etc.)

---

### 3. "Port already in use"

**Error:** `Address already in use :8080`

**Cause:** Another program is using the port.

**Solution:**

**Windows:**
```powershell
netstat -ano | findstr :8080
taskkill /PID <pid_nummer> /F
```

**macOS/Linux:**
```bash
lsof -i :8080
kill -9 <pid>
```

**Or:** Change port in `config.yaml`:

```yaml
Timer:
  WebServerPort: 8081  # Instead of 8080
```

---

### 4. "TikTok connection fails"

**Error:** Client cannot connect to TikTok.

**Diagnostics:**

```python
# Test in main.py
client = TikTokLiveClient(unique_id="my_username")
try:
    asyncio.run(client.connect())
    print("✓ Connection successful!")
except Exception as e:
    print(f"✗ Connection failed: {e}")
```

**Common Causes:**
- TikTok user does not exist (misspelled)
- Internet down
- TikTok API has changed

---

### 5. "Plugin won't load"

**Error:** Plugin is in `src/plugins/` but is not used.

**Debugging:**

1. **Check:** Plugin registered in `PLUGIN_REGISTRY`?
   ```python
   # In start.py / registry.py
   {"name": "MyPlugin", "path": ..., "enable": True, ...}
   ```

2. **Check:** Plugin has `main.py`?
   ```
   src/plugins/my_plugin/
   ├── main.py       # Must exist!
   ├── README.md
   └── version.txt
   ```

3. **Check:** Plugin can import?
   ```bash
   python src/plugins/my_plugin/main.py --register-only
   ```
   If error → check imports

---

### 6. "Webhook is not received"

**Error:** Minecraft sends event but your plugin doesn't receive it.

**Debugging:**

```python
@app.route("/webhook", methods=["POST"])
def webhook():
    logger.info(f"Webhook received: {request.json}")
    print(f"[WEBHOOK] {request.json}")  # Additionally print
    return {"success": True}, 200
```

**Checks:**

1. **Is Flask running?** 
   ```bash
   curl http://localhost:7878/webhook -X POST -d "{}"
   ```

2. **Firewall allows port?** Port must be open.

3. **Config is correct?** Port in `config.yaml` must match Flask port.

---

### 7. "Queue overflowing" or "Performance problems"

**Error:** Many events → System becomes slow.

**Debugging:**

```python
import asyncio

# In main loop
while True:
    size = trigger_queue.qsize()
    if size > 100:
        logger.warning(f"Queue size: {size} – could be tight!")
    
    event = trigger_queue.get()
    process(event)
```

**Optimization:**

- Use batch processing (process multiple events at once)
- Use threading (several workers per queue)
- Filter events (do not process all of them)

---

### 8. "Thread safety error" / "Race condition"

**Error:** Sporadic, non-reproducible errors (sometimes it works, sometimes it doesn't).

**Cause:** Two threads change the data at the same time.

**Solution – Use Lock:**

```python
from threading import Lock

counter_lock = Lock()
counter = 0

def increment():
    global counter
    with counter_lock:  # Only one thread at a time!
        counter += 1
        logger.debug(f"Counter: {counter}")
```

---

## Performance profiling

If the program is slow:

### 1. Where is the bottleneck?

```python
import time

start = time.time()
result = process_large_data()
elapsed = time.time() - start

logger.info(f"process_large_data() took {elapsed:.2f}s")
```

### 2. Use Profiler

```bash
python -m cProfile -s cumtime main.py
```

This shows which functions consume the most time.

---

## Debugging checklist

If something doesn't work:

- [ ] Are the **logs** readable?
- [ ] **Try-except** blocks around critical parts?
- [ ] **Imports** correct? (`pip install` all dependencies?)
- [ ] **Config valid**? (YAML, ports, etc.)
- [ ] **Breakpoints** set and ran through the code?
- [ ] **Environment variables** correct?
- [ ] **Other processes** block resources? (ports, files)
- [ ] **Data type error**? (String instead of integer, etc.)
- [ ] **Off-by-one error**? (index error)
- [ ] **Race conditions**? (threading problems)

---

## Get help

### 1. Describe your problem precisely

**Bad:**
> "My plugin doesn't work!"

**Good:**
> "My plugin timer doesn't start. Error: `ModuleNotFoundError: No module named 'requests'`. I have executed `pip install -r requirements.txt`, but it doesn't work."

### 2. Share code snippet

```python
# My on_gift handler
@client.on(GiftEvent)
def on_gift(event):
    trigger_queue.put_nowait((event.gift.name, event.user.nickname))
    # Error here?
```

### 3. Share logs

```
[ERROR] Error in event handler:
Traceback (most recent call last):
  File "main.py", line 123, in on_gift
    ...
KeyError: 'gift_id'
```

### 4. Describe your environment

- OS: Windows / macOS / Linux
- Python: 3.8 / 3.9 / 3.10 / 3.11 / 3.12
- Streaming Tool Version: v1.0 / dev / etc.

---

## Summary

Good debugging follows this flow:

```
Notice error
    ↓
Check logs (Tool 1)
    ↓
Print debugging (Tool 2)
    ↓
Use try-except (Tool 3)
    ↓
VS Code Debugger (Tool 4)
    ↓
Error found!
    ↓
Implement fix
```

With a little practice you will be able to find errors quickly.
