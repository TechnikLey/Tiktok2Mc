# Konfiguration & Datenspeicherung

###  Config + State Trennung

**config.yaml** (vom User bearbeitet):
- Port-Nummern, Enable-Flags, UI-Theme
- Menschen-lesbares YAML-Format
- Wird beim Plugin-Start geladen

**DATA_DIR**:
- Zähler-States, Window-Positionen, Benutzerdaten
- JSON-Format (strukturiert)
- Bleibt über Updates erhalten

### Architektur

```
config/
└── config.yaml
    └── MyPlugin:
        ├── Enable: true
        ├── WebServerPort: 8001
        └── Theme: "dark"
                ↓
          [Plugin startet]
                ↓
data/
└── my_plugin_state.json
    └── {
          "counter": 42,
          "window_x": 100,
          "last_updated": 1234567890
        }
```

### Config laden (3 Schritte)

**Schritt 1: YAML öffnen**
```python
from pathlib import Path
import yaml

CONFIG_FILE = ROOT_DIR / "config" / "config.yaml"

# Mit Error-Handling
try:
    with open(CONFIG_FILE) as f:
        config = yaml.safe_load(f) or {}
except Exception as e:
    print(f"Config-Fehler: {e}")
    config = {}
```

**Schritt 2: Werte mit Defaults auslesen**
```python
# Mit .get() bleibst du sicher vor KeyErrors
port = config.get("MyPlugin", {}).get("WebServerPort", 8001)
enabled = config.get("MyPlugin", {}).get("Enable", True)
theme = config.get("MyPlugin", {}).get("Theme", "light")
```

**Schritt 3: Im Plugin nutzen**
```python
if enabled:
    app.run(port=port)
    set_theme(theme)
```

### Praktisches Beispiel: Daten speichern

```python
import json
from pathlib import Path

# Pfade
DATA_DIR = ROOT_DIR / "data"
STATE_FILE = DATA_DIR / "myplugin_state.json"

# Daten laden (oder Default)
def load_state():
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"counter": 0, "wins": 0}

# Daten speichern
def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

# Nutzung
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
    print(f"Config konnte nicht geladen werden: {e}")
    cfg = {}

# Wert auslesen mit Default-Wert
port = cfg.get("MeinPlugin", {}).get("WebServerPort", 8000)
enable = cfg.get("MeinPlugin", {}).get("Enable", True)
```

**Mit `.get()` Methode** kannst du sicher Werte abfragen, ohne dass dein Programm crasht, wenn der Schlüssel fehlt.

## Datenspeicherung: Wo speichere ich meine Daten?

Es gibt mehrere Möglichkeiten, je nach deinem Use-Case:

### 1. DATA_DIR (empfohlen für Plugin-spezifische Daten)

```
ROOT_DIR/
    data/
        window_state_timer.json
        window_state_deathcounter.json
```

**Verwendung:** Persistente Daten wie Zählerstände, Window-Positionen, Benutzervorgaben.

```python
from pathlib import Path

DATA_DIR = ROOT_DIR / "data"
STATE_FILE = DATA_DIR / "my_plugin_state.json"

# Daten speichern
import json
state = {"counter": 42, "width": 800}
with STATE_FILE.open("w") as f:
    json.dump(state, f)

# Daten laden
if STATE_FILE.exists():
    with STATE_FILE.open("r") as f:
        state = json.load(f)
else:
    state = {"counter": 0, "width": 800}
```

**Vorteil:** Data-Ordner bleibt bei Updates erhalten.

### 2. Im Plugin-Ordner selbst (Alternative)

```
src/plugins/mein_plugin/
    main.py
    README.md
    version.txt
    plugin_data.json  ← direkt hier speichern
```

```python
PLUGIN_DIR = get_base_dir()
MY_DATA_FILE = PLUGIN_DIR / "plugin_data.json"
```

### 3. runtime Ordner (nicht empfohlen)

```
build/release/core/runtime/
    meine_daten.json
```

**WARNUNG:** Der `runtime` Ordner wird bei jedem Update überschrieben! Nutze ihn nur für **temporäre** Daten, die neu generiert werden können.

## Praktisches Beispiel: Window-Zustand speichern

Der Timer und DeathCounter speichern ihre Fenster-Größe/Position:

```python
# Laden beim Start
def load_win_size():
    if STATE_FILE.exists():
        try:
            with STATE_FILE.open("r") as f:
                return json.load(f)
        except:
            pass
    return {"width": 400, "height": 200}

# Speichern wenn Fenster sich ändert
@app.route("/save_dims", methods=["POST"])
def save_dims():
    with STATE_FILE.open("w") as f:
        json.dump(request.json, f)
    return "OK"
```

Das Frontend ruft `/save_dims` auf, sobald der Nutzer das Fenster verschiebt oder vergrößert.

## YAML vs. JSON

**JSON:** Schneller zum Laden, einfache Struktur
```python
import json
data = json.load(f)
```

**YAML:** Lesbar für Menschen, komplexere Strukturen
```python
import yaml
data = yaml.safe_load(f)
```

**Empfehlung:** Für Plugin-Daten JSON verwenden (schneller, weniger Dependencies). YAML nur für die Haupt-Config.

## Daten zwischen Plugins teilen

Plugins können sich über Dateien austauschen:

```python
# Plugin A speichert Daten
shared_data = {"wins": 10, "deaths": 3}
with (DATA_DIR / "shared_counter.json").open("w") as f:
    json.dump(shared_data, f)

# Plugin B liest Daten
with (DATA_DIR / "shared_counter.json").open("r") as f:
    data = json.load(f)
    print(data["wins"])
```

**Aber:** Achte auf **Race Conditions**! Wenn beide Plugins gleichzeitig schreiben, kann es zu Datenverlust kommen. Nutze stattdessen HTTP-Kommunikation (siehe nächstes Kapitel).

---

## Zusammenfassung

- **Config laden:** `yaml.safe_load()` aus `config.yaml`
- **Daten speichern:** JSON in `DATA_DIR` für Persistenz
- **Fallback-Werte:** Immer `.get()` mit Defaults verwenden
- **Teilen:** über Dateien (Vorsicht Race Conditions) oder HTTP
- **Runtime Ordner:** Nur für temporäre Daten, wird überschrieben

**Nächstes Kapitel:** [GUI mit pywebview](./ch02-04-gui-with-pywebview.md)
