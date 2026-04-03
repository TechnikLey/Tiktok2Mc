# Error Handling & Best Practices

### You are responsible for yourself

> [!WARNING]
> The main system does **NOT** take care of errors in your plugin.

```
Main streaming tool
├─ Plugin A (crashes → dead forever)
├─ Plugin B (runs normally)
└─ Plugin C (hangs → dark forever)
```

**Consequence:** **Your plugin must have 100% own error handling.**

### Error handling strategies

| Phase | Error | Handling |
|-------|-------|----------|
| **Startup** | Config is missing | Use defaults + log |
| **Flask Server** | Port already in use | Alternative port + error message |
| **HTTP requests** | Timeout/Connection | Retry logic + fallback |
| **File I/O** | Permission denied | Try-except + logging |
| **Unknown** | ??? | Global try-except + log + exit |

### Error handling: layered model

**Layer 1: Startup Protection**
```python
import sys
import logging

logging.basicConfig(
    level=logging.INFO,
    filename="logs/plugin.log",
    format='%(asctime)s [%(levelname)s] %(message)s'
)

try:
    # Load config
    cfg = load_config()
except Exception as e:
    logging.critical(f"Config error: {e}")
    cfg = {}  # Defaults!

try:
    # Start Flask
    threading.Thread(target=lambda: app.run(port=cfg.get("port", 8001)), 
                     daemon=True).start()
except Exception as e:
    logging.critical(f"Flask error: {e}")
    sys.exit(1)
```

**Layer 2: Route Protection**
```python
@app.route("/webhook", methods=['POST'])
def webhook():
    try:
        data = request.json
        # Your logic
        return {"status": "ok"}, 200
    except Exception as e:
        logging.error(f"Webhook error: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}, 500

@app.route("/api/add", methods=['POST'])
def add():
    try:
        amount = request.json.get("amount", 1)
        # Logic
        return {"result": result}
    except Exception as e:
        logging.error(f"Add error: {e}")
        return {"status": "error"}, 500
```

**Layer 3: Global Wrapper**
```python
def main():
    try:
        # Everything your plugin does
        threading.Thread(target=start_flask, daemon=True).start()
        webview.create_window(...)
        webview.start()
    except KeyboardInterrupt:
        logging.info("Plugin stopped by user")
    except Exception as e:
        logging.critical(f"Plugin crashed: {e}", exc_info=True)
        sys.exit(1)

if __name__ == '__main__':
    main()
```

### Logging Best Practices

```python
import logging
from pathlib import Path

# Setup
LOGS_DIR = ROOT_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.DEBUG,
    handlers=[
        logging.FileHandler(LOGS_DIR / "myplugin.log"),
        logging.StreamHandler()  # Also console
    ],
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)

logger = logging.getLogger(__name__)

# Usage:
logger.debug("Debug info for developers")
logger.info("Plugin started successfully")
logger.warning("Config missing, using default")
logger.error("HTTP request failed", exc_info=True)
logger.critical("Plugin cannot recover from this error!")
```

### Common Errors + Fixes

| Error | Cause | Fix |
|-------|-------|-----|
| **Port already in use** | Port 8001 occupied | Alternative port in config.yaml |
| **Connection refused** | Other plugin offline | try-except + fallback |
| **Timeout** | Request too slow | `timeout=5` increase |
| **JSON decode error** | Malformed response | `json.JSONDecodeError` catch |
| **FileNotFoundError** | Config file is missing | `.exists()` check before reading |

### Plugin Ready Checklist

- ☑ Global try-except wrapper around main()
- ☑ Logging to file + console
- ☑ All config keys with `.get()` + defaults
- ☑ HTTP requests in threads
- ☑ HTTP requests with timeout + try-except
- ☑ Check all files with `.exists()`
- ☑ Graceful shutdown with Ctrl+C

**Congratulations!** You now know everything you need to build a production-ready plugin.

```
┌──────────────────────────────────────────────┐
│           Main Streaming Tool                │
│     (does NOT care about crashes)            │
└────────────┬─────────────────────────────────┘
             │
             │── Plugin A (crashes → ignored)
             │── Plugin B (runs normally)
             │── Plugin C (hangs → ignored)
```

If your plugin crashes, it is **gone**. The system does not restore it.

## Global error handling

Wrap your entire main logic in try-except:

```python
import logging

logging.basicConfig(
    level=logging.INFO,
    filename=ROOT_DIR / "logs" / "my_plugin.log",
    format='%(asctime)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

try:
    # Your entire plugin logic here
    flask_thread = threading.Thread(target=start_flask)
    flask_thread.start()
    
    webview.create_window('Plugin', 'http://127.0.0.1:7777')
    webview.start()

except Exception as e:
    logger.critical(f"Plugin crashed: {e}", exc_info=True)
    sys.exit(1)
```

This logs the error and exits the plugin cleanly.

## Logging – your best friend

Logging is essential for debugging. Use the `logs/` folder:

```python
import logging
from pathlib import Path

LOGS_DIR = ROOT_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.DEBUG,
    handlers=[
        logging.FileHandler(LOGS_DIR / "plugin.log"),
        logging.StreamHandler()  # Also in console
    ],
    format='%(asctime)s [%(levelname)s] %(message)s'
)

logger = logging.getLogger(__name__)

# Usage:
logger.info("Plugin started")
logger.warning("This could be problematic")
logger.error("Critical error occurred")
logger.debug("Debug information")
```

### Understanding log levels

```yaml
# In your config.yaml for the main system
log_level: 2

# Your plugin:
# Level 1: ERROR/CRITICAL
# Level 2: WARNING
# Level 3: INFO
# Level 4: DEBUG
```

With `level=4` your debug output is visible when registering,
as soon as `log_level: 4` is set.
The `log_level` must be >= your registered `level` for the
terminal to be displayed.

## Avoid typical mistakes

### 1. Hard-coded paths

WRONG:
```python
cfg_file = "C:\\Users\\Admin\\Documents\\config.yaml"
```

CORRECT:
```python
cfg_file = ROOT_DIR / "config" / "config.yaml"
```

Always use `get_root_dir()`, `get_base_dir()`, etc.

### 2. Encoding error when reading files

WRONG:
```python
with open(cfg_file) as f:  # Default encoding can be different
    data = yaml.safe_load(f)
```

CORRECT:
```python
with open(cfg_file, "r", encoding="utf-8") as f:
    data = yaml.safe_load(f)
```

### 3. Blocking operations in the main loop

If you do a long operation (network request, file processing), everything after that blocks:

```python
# WRONG:
requests.get("http://API.com/data")  # May take 10 seconds
app.run()  # Flask only starts after the request
```

CORRECT:
```python
# Start in thread
def fetch_data():
    requests.get("http://API.com/data")

threading.Thread(target=fetch_data, daemon=True).start()
app.run()  # Flask runs in parallel
```

### 4. Not checking for configuration errors

```python
# WRONG:
port = cfg["MyPlugin"]["port"]  # KeyError if not present!

# CORRECT:
port = cfg.get("MyPlugin", {}).get("port", 8000)  # With default
```

### 5. Race conditions for file access

```python
# WRONG - two plugins write at the same time:
with STATE_FILE.open("w") as f:
    json.dump(data, f)

# BETTER - Temporary file + rename:
import tempfile
with tempfile.NamedTemporaryFile(mode="w", dir=DATA_DIR, delete=False) as tmp:
    json.dump(data, tmp)
    tmp.flush()
    tmp_path = tmp.name

import shutil
shutil.move(tmp_path, STATE_FILE)  # Atomic operation
```

### 6. Forgotten timeout for network requests

```python
# WRONG - hangs forever:
response = requests.get("http://localhost:9999")

# CORRECT:
try:
    response = requests.get("http://localhost:9999", timeout=3)
except requests.Timeout:
    logger.error("Request timed out")
```

## Graceful Shutdown

If the user enters "exit" in the start file, your plugin will be terminated with SIGTERM. Use this:

```python
import signal

def handle_shutdown(sig, frame):
    logger.info("Plugin is closing...")
    # Cleanup here
    sys.exit(0)

signal.signal(signal.SIGTERM, handle_shutdown)
signal.signal(signal.SIGINT, handle_shutdown)
```

## Monitoring and health checks

If other plugins communicate with you, it can be beneficial to have
a `health` check available:

```python
@app.route('/health')
def health():
    return json.dumps({"status": "ok", "version": "1.0.0"})
```

Other plugins can check whether you are still running:

```python
try:
    r = requests.get("http://localhost:7878/health", timeout=1)
    if r.status_code == 200:
        print("Plugin is running")
except:
    print("Plugin not available")
```

## Resource management

### Avoid memory leaks

```python
# WRONG - infinite list:
all_events = []
@app.route('/webhook', methods=['POST'])
def webhook():
    all_events.append(request.json)  # Getting bigger and bigger!

# CORRECT - limited queue:
from collections import deque
events = deque(maxlen=1000)  # Max 1000 entries

@app.route('/webhook', methods=['POST'])
def webhook():
    events.append(request.json)  # Oldest entries are automatically deleted
```

### Avoid thread leaks

```python
# WRONG - new threads for each request:
@app.route('/process', methods=['POST'])
def process():
    threading.Thread(target=heavy_work).start()  # Memory leak!

# CORRECT - Thread Pool:
from concurrent.futures import ThreadPoolExecutor
executor = ThreadPoolExecutor(max_workers=5)

@app.route('/process', methods=['POST'])
def process():
    executor.submit(heavy_work)  # Max 5 parallel tasks
```

## Testing before release

```python
# test_plugin.py
import requests
import time

def test_basic():
    # Plugin should run on port 7878
    r = requests.get("http://localhost:7878/health")
    assert r.status_code == 200

def test_webhook():
    r = requests.post("http://localhost:7878/webhook", json={
        "event": "player_death",
        "message": "Test"
    })
    assert r.status_code == 200
    time.sleep(1)
    # Check if effect is visible...

if __name__ == "__main__":
    test_basic()
    test_webhook()
    print("All tests passed!")
```

Then start tests:
```bash
python test_plugin.py
```

> [!TIP]
> It is recommended to build the project with the `build.ps1` script and
> then test it in the `release` folder because certain plugins/main program dependencies
> are only properly present in the release folder.

## Checklist before release

- Global try-except around main logic
- Logging at critical/error/info level
- All config accesses with `.get()` + fallback
- Timeouts for all network requests
- `/health` endpoint
- Paths with `get_root_dir()` etc., not hardcoded
- Encoding utf-8 for file operations
- Threading instead of blocking ops in main
- Memory + thread leaks minimized
- README documented and up to date

---

## Summary

- **Your plugin is alone** – No automatic crash handling
- **Logging:** Use the `logs/` folder, save debug info
- **Error handling:** Try-except global + on every network op
- **Timeouts:** Always set for requests
- **Threading:** Outsource blocking ops to threads
- **Testing:** Test manually/automatically before release

That's it for the basics! From here on out, it's all about your creativity and the specific needs of your plugin. Good luck!
