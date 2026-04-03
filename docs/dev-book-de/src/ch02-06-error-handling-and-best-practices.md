# Error Handling & Best Practices

### Du bist selbst verantwortlich

> [!WARNING]
> Das Haupt-System kümmert sich **NICHT** um Fehler deines Plugins.

```
Main Streaming Tool
├─ Plugin A (crasht → für immer tot)
├─ Plugin B (läuft normal)
└─ Plugin C (hängt sich auf → für immer dunkel)
```

**Konsequenz:** **Dein Plugin muss 100% eigenen Error-Handling haben.**

### Error-Handling Strategien

| Phase | Fehler | Handling |
|-------|--------|----------|
| **Startup** | Config fehlt | Defaults nutzen + Log |
| **Flask Server** | Port bereits in Benutzung | Alternative Port + Error-Message |
| **HTTP-Requests** | Timeout/Connection | Retry-Logic + Fallback |
| **Datei-I/O** | Permission denied | Try-except + Logging |
| **Unbekannt** | ??? | Global try-except + Log + Exit |

### Fehler-Handling: Schichten-Modell

**Schicht 1: Startup Protection**
```python
import sys
import logging

logging.basicConfig(
    level=logging.INFO,
    filename="logs/plugin.log",
    format='%(asctime)s [%(levelname)s] %(message)s'
)

try:
    # Config laden
    cfg = load_config()
except Exception as e:
    logging.critical(f"Config-Fehler: {e}")
    cfg = {}  # Defaults!

try:
    # Flask starten
    threading.Thread(target=lambda: app.run(port=cfg.get("port", 8001)), 
                     daemon=True).start()
except Exception as e:
    logging.critical(f"Flask-Fehler: {e}")
    sys.exit(1)
```

**Schicht 2: Route Protection**
```python
@app.route("/webhook", methods=['POST'])
def webhook():
    try:
        data = request.json
        # Deine Logik
        return {"status": "ok"}, 200
    except Exception as e:
        logging.error(f"Webhook-Fehler: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}, 500

@app.route("/api/add", methods=['POST'])
def add():
    try:
        amount = request.json.get("amount", 1)
        # Logic
        return {"result": result}
    except Exception as e:
        logging.error(f"Add-Fehler: {e}")
        return {"status": "error"}, 500
```

**Schicht 3: Global Wrapper**
```python
def main():
    try:
        # Alles, was dein Plugin macht
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
LOGS_DIR = Root_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.DEBUG,
    handlers=[
        logging.FileHandler(LOGS_DIR / "myplugin.log"),
        logging.StreamHandler()  # Auch Console
    ],
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)

logger = logging.getLogger(__name__)

# Nutzung:
logger.debug("Debug-Info für Entwickler")
logger.info("Plugin started successfully")
logger.warning("Config missing, using default")
logger.error("HTTP request failed", exc_info=True)
logger.critical("Plugin cannot recover from this error!")
```

### Typische Fehler + Fixes

| Fehler | Ursache | Fix |
|--------|--------|-----|
| **Port already in use** | Port 8001 belegt | Alternative Port in config.yaml |
| **Connection refused** | Anderes Plugin offline | try-except + Fallback |
| **Timeout** | Request zu langsam | `timeout=5` erhöhen |
| **JSON decode error** | Malformed response | `json.JSONDecodeError` fangen |
| **FileNotFoundError** | Config-Datei fehlt | `.exists()` checken vor Read |

### Plugin-Ready Checkliste

- ☑ Global try-except wrapper um main()
- ☑ Logging auf File + Console
- ☑ Alle config-Keys mit `.get()` + defaults
- ☑ HTTP-Requests in Threads
- ☑ HTTP-Requests mit timeout + try-except
- ☑ Alle Dateien mit .exists() checken
- ☑ Graceful shutdown bei Ctrl+C

**Gratuliere!** Du kennst jetzt alles, um ein production-ready Plugin zu bauen.

```
┌─────────────────────────────────────────────┐
│         Main Streaming Tool                 │
│         (kümmert sich NICHT um Crashes)     │
└────────────┬────────────────────────────────┘
             │
             │── Plugin A (crasht → ignoriert)
             │── Plugin B (läuft normal)
             │── Plugin C (hängt sich auf → ignoriert)
```

Wenn dein Plugin crasht, ist es **weg**. Das System stellt es nicht wieder her.

## Globales Error Handling

Wrapple deine gesamte Main-Logik in try-except:

```python
import logging

logging.basicConfig(
    level=logging.INFO,
    filename=ROOT_DIR / "logs" / "my_plugin.log",
    format='%(asctime)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

try:
    # Deine gesamte Plugin-Logik hier
    flask_thread = threading.Thread(target=start_flask)
    flask_thread.start()
    
    webview.create_window('Plugin', 'http://127.0.0.1:7777')
    webview.start()

except Exception as e:
    logger.critical(f"Plugin ist gecrasht: {e}", exc_info=True)
    sys.exit(1)
```

Das loggt den Fehler und beendet das Plugin sauber.

## Logging – Deine beste Freundin

Logging ist essentiell zum Debuggen. Nutze `logs/` Ordner:

```python
import logging
from pathlib import Path

LOGS_DIR = ROOT_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.DEBUG,
    handlers=[
        logging.FileHandler(LOGS_DIR / "plugin.log"),
        logging.StreamHandler()  # Auch in Console
    ],
    format='%(asctime)s [%(levelname)s] %(message)s'
)

logger = logging.getLogger(__name__)

# Nutzen:
logger.info("Plugin gestartet")
logger.warning("Das könnte problematisch sein")
logger.error("Kritischer Fehler aufgetreten")
logger.debug("Debug-Informationen")
```

### Log-Level verstehen

```yaml
# In deiner config.yaml für das Haupt-System
log_level: 2

# Dein Plugin:
# Level 1: ERROR/CRITICAL
# Level 2: WARNING
# Level 3: INFO
# Level 4: DEBUG
```

Mit `level=4` bei der Registrierung ist dein Debug-Output sichtbar,
sobald `log_level:4` ist.
Das `log_level` muss >= deinem Registrierten `level` sein damit das
Terminal angezigt wird.

## Typische Fehler vermeiden

### 1. Hardcodierte Pfade

FALSCH:
```python
cfg_file = "C:\\Users\\Admin\\Documents\\config.yaml"
```

RICHTIG:
```python
cfg_file = ROOT_DIR / "config" / "config.yaml"
```

Nutze immer `get_root_dir()`, `get_base_dir()`, etc.

### 2. Encoding-Fehler bei Datei-Lesen

FALSCH:
```python
with open(cfg_file) as f:  # Default encoding kann unterschiedlich sein
    data = yaml.safe_load(f)
```

RICHTIG:
```python
with open(cfg_file, "r", encoding="utf-8") as f:
    data = yaml.safe_load(f)
```

### 3. Blockierende Operationen in der Main-Loop

Wenn du eine lange Operation machst (Netzwerk-Request, Datei-Verarbeitung), blockiert alles danach:

```python
# FALSCH:
requests.get("http://API.com/data")  # Kann 10 Sekunden dauern
app.run()  # Flask startet erst nach dem Request
```

RICHTIG:
```python
# In Thread starten
def fetch_data():
    requests.get("http://API.com/data")

threading.Thread(target=fetch_data, daemon=True).start()
app.run()  # Flask läuft parallel
```

### 4. Nicht auf Konfiguration Fehler prüfen

```python
# FALSCH:
port = cfg["MyPlugin"]["port"]  # KeyError wenn nicht vorhanden!

# RICHTIG:
port = cfg.get("MyPlugin", {}).get("port", 8000)  # Mit Default
```

### 5. Race Conditions bei Datei-Zugriff

```python
# FALSCH - zwei Plugins schreiben gleichzeitig:
with STATE_FILE.open("w") as f:
    json.dump(data, f)

# BETTER - Temporary File + Rename:
import tempfile
with tempfile.NamedTemporaryFile(mode="w", dir=DATA_DIR, delete=False) as tmp:
    json.dump(data, tmp)
    tmp.flush()
    tmp_path = tmp.name

import shutil
shutil.move(tmp_path, STATE_FILE)  # Atomic operation
```

### 6. Timeout vergessen bei Netzwerk-Requests

```python
# FALSCH - hängt für immer:
response = requests.get("http://localhost:9999")

# RICHTIG:
try:
    response = requests.get("http://localhost:9999", timeout=3)
except requests.Timeout:
    logger.error("Request timed out")
```

## Graceful Shutdown

Falls der Nutzer "exit" in der Start-Datei eingibt, wird dein Plugin mit SIGTERM beendet. Nutze das:

```python
import signal

def handle_shutdown(sig, frame):
    logger.info("Plugin wird beendet...")
    # Cleanup hier
    sys.exit(0)

signal.signal(signal.SIGTERM, handle_shutdown)
signal.signal(signal.SIGINT, handle_shutdown)
```

## Monitoring und Health Checks

Wenn anderer Plugins mit dir kommunizieren, kann es von vorteil sein,
ein `health` checker zu haben:

```python
@app.route('/health')
def health():
    return json.dumps({"status": "ok", "version": "1.0.0"})
```

Andere Plugins können checken, ob du noch läufst:

```python
try:
    r = requests.get("http://localhost:7878/health", timeout=1)
    if r.status_code == 200:
        print("Plugin läuft")
except:
    print("Plugin nicht erreichbar")
```

## Resource Management

### Memory Leaks vermeiden

```python
# FALSCH - infinite list:
all_events = []
@app.route('/webhook', methods=['POST'])
def webhook():
    all_events.append(request.json)  # Wird immer größer!

# RICHTIG - begrenzte Queue:
from collections import deque
events = deque(maxlen=1000)  # Max 1000 Einträge

@app.route('/webhook', methods=['POST'])
def webhook():
    events.append(request.json)  # Älteste Einträge werden automatisch gelöscht
```

### Thread-Leaks vermeiden

```python
# FALSCH - neue Threads für jeden Request:
@app.route('/process', methods=['POST'])
def process():
    threading.Thread(target=heavy_work).start()  # Memory leak!

# RICHTIG - Thread Pool:
from concurrent.futures import ThreadPoolExecutor
executor = ThreadPoolExecutor(max_workers=5)

@app.route('/process', methods=['POST'])
def process():
    executor.submit(heavy_work)  # Max 5 parallele Tasks
```

## Testing vor dem Release

```python
# test_plugin.py
import requests
import time

def test_basic():
    # Plugin sollte auf Port 7878 laufen
    r = requests.get("http://localhost:7878/health")
    assert r.status_code == 200

def test_webhook():
    r = requests.post("http://localhost:7878/webhook", json={
        "event": "player_death",
        "message": "Test"
    })
    assert r.status_code == 200
    time.sleep(1)
    # Prüfe ob Effekt sichtbar ist...

if __name__ == "__main__":
    test_basic()
    test_webhook()
    print("Alle Tests bestanden!")
```

Dann tests starten:
```bash
python test_plugin.py
```

> [!TIP]
> Es wird empfohlen das Projekt zu bauen mit denn `build.ps1` script und
> es dann im `release` Ordner zu testen weil gewisse Plugins/Hauptprogramm   abhänigkeiten
> haben die nur im realse ordner richtig vorhanden sind.

## Checkliste vor Release

- Globales try-except um Main-Logik
- Logging auf Critical/Error/Info Ebene
- Alle Config-Zugriffe mit `.get()` + Fallback
- Timeouts bei allen Netzwerk-Requests
- `/health` Endpoint
- Paths mit `get_root_dir()` etc., nicht hardcoded
- Encoding utf-8 bei Datei-Operationen
- Threading statt blockierende Ops in Main
- Memory + Thread Leaks minimiert
- README dokumentiert und aktuell

---

## Zusammenfassung

- **Dein Plugin ist allein** – Kein automatisches Crash-Handling
- **Logging:** Nutze `logs/` Ordner, speichere Debug-Infos
- **Fehlerbehandlung:** Try-except global + bei jeder Netzwerk-Op
- **Timeouts:** Immer setzen bei Requests
- **Threading:** Blockierende Ops in Threads auslagern
- **Testing:** Vor Release manuell/automatisch testen

Das war's für die Grundlagen! Von hier an geht es um deine Kreativität und die speziellen Anforderungen deines Plugins. Viel Erfolg!
