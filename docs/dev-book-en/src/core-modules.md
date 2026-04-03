# Core Modules and Infrastructure

> [!NOTE]
> This overview is aimed at **advanced developers** who want to understand how the system's infrastructure is structured. Intermediate Python knowledge is assumed.

---

## Overview

The **core modules** are located in `src/core/` and form the **infrastructure** of the system. They are not directly visible in the stream – but every plugin uses them in the background.

| Module | Purpose |
|-------|---------|
| **paths.py** | Directory management & paths |
| **utils.py** | Load configuration, helper functions |
| **models.py** | Data structures (AppConfig) |
| **validator.py** | Syntax validation (actions.mca) |
| **cli.py** | Command-line arguments |

---

## paths.py – Path Management

### What Is It?

`paths.py` handles **where everything is** in the file system.

### Short Examples

```python
from core.paths import get_root_dir, get_config_file

# Where is the project?
root = get_root_dir()  
# → "C:\Users\User\Streaming_Tool" or ".\build\release"

# Where is config.yaml?
config = get_config_file()  
# → "C:\Users\User\Streaming_Tool\config\config.yaml"
```

### Important Functions

- `get_root_dir()` – Project root
- `get_config_file()` – Path to config.yaml
- `get_base_dir()` – Base directory (distinguishes frozen vs. development)

**What do you need this for?**
So that plugins don't have to hard-code `C:\...\config.yaml`, but can simply call `get_config_file()`.

---

## utils.py – Configuration & Helper Functions

### What Is It?

`utils.py` loads and parses the **config.yaml** file. This is the central configuration file of the system.

### Short Examples

```python
from core.utils import load_config
from core.paths import get_config_file

# Load config
config = load_config(get_config_file())

# Access values
plugins = config["plugins"]
log_level = config["settings"]["log_level"]
```

### What Does load_config() Do?

1. Checks whether the file exists
2. Parses YAML
3. Returns a dictionary
4. **On error**: Terminates the program with a meaningful error message

**What do you need this for?**
Every plugin needs to read config.yaml. `load_config()` does this reliably – with error handling.

---

## models.py – Data Structures

### What Is It?

`models.py` defines **AppConfig** – the data structure that describes a plugin (how it is registered in the registry).

### The AppConfig Structure

```python
@dataclass
class AppConfig:
    name: str          # Name of the plugin
    path: Path         # Where is the plugin located?
    enable: bool       # Is it enabled?
    level: int         # Priority / log level
    ics: bool          # Does it have a GUI window?
```

### Short Examples

```python
from core.models import AppConfig
from pathlib import Path

# Define a plugin
timer = AppConfig(
    name="Timer",
    path=Path("src/plugins/timer"),
    enable=True,
    level=1,
    ics=True  # Has GUI
)

# As dictionary for config.yaml
plugin_dict = timer.to_dict()
# → {"name": "Timer", "path": "src/plugins/timer", ...}

# Back from dictionary
timer2 = AppConfig.from_dict(plugin_dict)
```

**What do you need this for?**
The PLUGIN_REGISTRY manages all plugins as AppConfig objects. This keeps management structured and validated.

---

## validator.py – Syntax Validation

### What Is It?

`validator.py` checks the **actions.mca** file for errors. It detects:
- Missing colons
- Invalid syntax
- Duplicate triggers
- Formatting errors

### Short Examples

```python
from core.validator import validate_text

text = """
5655:!tnt 2 0.1 2 Notch
follow:/give @a minecraft:golden_apple 7
invalid_line_without_colon
"""

diags = validate_text(text)  # List of errors

for diag in diags:
    print(f"[{diag.severity}] Line {diag.line}: {diag.message}")
    # → [ERROR] Line 3: Missing colon
```

### What Is Validated?

✓ Every line must have the `TRIGGER:...` format  
✓ No spaces immediately after `:`  
✓ No duplicate triggers  
✓ Correct command format  

**What do you need this for?**
So that users can quickly see errors in their actions.mca – with exact line numbers and error codes.

---

## cli.py – Command-Line Arguments

### What Is It?

`cli.py` parses command-line arguments at startup:

```
python main.py --gui-hidden --register-only
```

### Available Arguments

| Argument | Effect |
|----------|--------|
| `--gui-hidden` | Start without GUI window (headless) |
| `--register-only` | Only register plugins, then exit |

### Short Examples

```python
from core.cli import parse_args

args = parse_args()

if args.gui_hidden:
    print("Starting in headless mode")

if args.register_only:
    print("Only updating registry, then exit")
    # ... plugin registry update ...
    sys.exit(0)
```

**What do you need this for?**
It enables different start modes (for testing, automation, maintenance).

---

## Summary

The **core modules** are the **infrastructure layer**:

| Module | Benefit |
|-------|--------|
| **paths.py** | Finding the correct paths (dev vs. release) |
| **utils.py** | Loading config reliably |
| **models.py** | Managing plugin metadata |
| **validator.py** | Finding and reporting errors |
| **cli.py** | Different start modes |

**Practical for developers:**
- Plugin developers: Mainly use `paths.py` and `utils.py`
- System developers (core): Use all modules
- The system itself: Uses everything together for registration & management
