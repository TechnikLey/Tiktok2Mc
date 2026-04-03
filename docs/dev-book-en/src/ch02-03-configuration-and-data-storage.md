# Configuration & data storage

###  Config + State separation

**config.yaml** (edited by user):
- Port numbers, enable flags, UI theme
- Human-readable YAML format
- Loaded when the plugin starts

**DATA_DIR**:
- Counter states, window positions, user data
- JSON format (structured)
- Remains available across updates

### Architecture

```
config/
└── config.yaml
    └── MyPlugin:
        ├── Enable: true
        ├── WebServerPort: 8001
        └── Theme: "dark"
                ↓
          [Plugin starts]
                ↓
data/
└── my_plugin_state.json
    └── {
          "counter": 42,
          "window_x": 100,
          "last_updated": 1234567890
        }
```

### Load config (3 steps)

**Step 1: Open YAML**
```python
from pathlib import Path
import yaml

CONFIG_FILE = ROOT_DIR / "config" / "config.yaml"

# With error handling
try:
    with open(CONFIG_FILE) as f:
        config = yaml.safe_load(f) or {}
except Exception as e:
    print(f"Config error: {e}")
    config = {}
```

**Step 2: Read out values with defaults**
```python
# With .get() you stay safe from KeyErrors
port = config.get("MyPlugin", {}).get("WebServerPort", 8001)
enabled = config.get("MyPlugin", {}).get("Enable", True)
theme = config.get("MyPlugin", {}).get("Theme", "light")
```

**Step 3: Use in the plugin**
```python
if enabled:
    app.run(port=port)
    set_theme(theme)
```

### Practical example: saving data

```python
import json
from pathlib import Path

# Paths
DATA_DIR = ROOT_DIR / "data"
STATE_FILE = DATA_DIR / "myplugin_state.json"

# Load data (or default)
def load_state():
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"counter": 0, "wins": 0}

# Save data
def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

# Usage
state = load_state()
state["counter"] += 1
save_state(state)
```

```python
import yaml
from pathlib import Path

CONFIG_FILE = (ROOT_DIR / "config" / "config.yaml").resolve()

try:
    with CONFIG_FILE.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
except Exception as e:
    print(f"Config could not be loaded: {e}")
    cfg = {}

# Read out value with default value
port = cfg.get("MyPlugin", {}).get("WebServerPort", 8000)
enable = cfg.get("MyPlugin", {}).get("Enable", True)
```

**With the `.get()` method** you can safely query values without your program crashing if the key is missing.

## Data storage: Where do I store my data?

There are several options, depending on your use case:

### 1. DATA_DIR (recommended for plugin-specific data)

```
ROOT_DIR/
    data/
        window_state_timer.json
        window_state_deathcounter.json
```

**Usage:** Persistent data such as counter readings, window positions, user preferences.

```python
from pathlib import Path

DATA_DIR = ROOT_DIR / "data"
STATE_FILE = DATA_DIR / "my_plugin_state.json"

# Save data
import json
state = {"counter": 42, "width": 800}
with STATE_FILE.open("w") as f:
    json.dump(state, f)

# Load data
if STATE_FILE.exists():
    with STATE_FILE.open("r") as f:
        state = json.load(f)
else:
    state = {"counter": 0, "width": 800}
```

**Advantage:** Data folder is retained during updates.

### 2. In the plugin folder itself (alternative)

```
src/plugins/my_plugin/
    main.py
    README.md
    version.txt
    plugin_data.json ← save directly here
```

```python
PLUGIN_DIR = get_base_dir()
MY_DATA_FILE = PLUGIN_DIR / "plugin_data.json"
```

### 3. runtime folder (not recommended)

```
build/release/core/runtime/
    my_data.json
```

**WARNING:** The `runtime` folder is overwritten with every update! Use it only for **temporary** data that can be regenerated.

## Practical example: Save window state

The Timer and DeathCounter save their window size/position:

```python
# Load at startup
def load_win_size():
    if STATE_FILE.exists():
        try:
            with STATE_FILE.open("r") as f:
                return json.load(f)
        except:
            pass
    return {"width": 400, "height": 200}

# Save when window changes
@app.route("/save_dims", methods=["POST"])
def save_dims():
    with STATE_FILE.open("w") as f:
        json.dump(request.json, f)
    return "OK"
```

The front end calls `/save_dims` as soon as the user moves or enlarges the window.

## YAML vs JSON

**JSON:** Faster to load, simple structure
```python
import json
data = json.load(f)
```

**YAML:** Readable for humans, more complex structures
```python
import yaml
data = yaml.safe_load(f)
```

**Recommendation:** Use JSON for plugin data (faster, fewer dependencies). YAML only for the main config.

## Share data between plugins

Plugins can exchange files:

```python
# Plugin A saves data
shared_data = {"wins": 10, "deaths": 3}
with (DATA_DIR / "shared_counter.json").open("w") as f:
    json.dump(shared_data, f)

# Plugin B reads data
with (DATA_DIR / "shared_counter.json").open("r") as f:
    data = json.load(f)
print(data["wins"])
```

**But:** Pay attention to **race conditions**! If both plugins write at the same time, data loss may occur. Use HTTP communication instead (see next chapter).

---

## Summary

- **Load config:** `yaml.safe_load()` from `config.yaml`
- **Save data:** JSON in `DATA_DIR` for persistence
- **Fallback values:** Always use `.get()` with defaults
- **Share:** Via files (be careful of race conditions) or HTTP
- **Runtime folder:** Only for temporary data, will be overwritten

**Next chapter:** [GUI with pywebview](./ch02-04-gui-with-pywebview.md)
