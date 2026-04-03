## The PLUGIN_REGISTRY: Central Plugin Registration

### Concept: What Is the Registry?

The app can control multiple processes (core app, GUI, server, plugins). They must be **centrally registered** and **configurable**. There are two registries for this:

1. **BUILDIN_REGISTRY** — core modules firmly defined in `start.py`
2. **PLUGIN_REGISTRY** — plugins dynamically loaded from `PLUGIN_REGISTRY.json`

### The AppConfig Class

Each registry entry is an `AppConfig` instance (defined in `core/models.py`):

```python
@dataclass(slots=True)
class AppConfig:
    name: str      # Unique name (e.g. "Timer")
    path: Path     # Absolute path to the EXE
    enable: bool   # Should the plugin start?
    level: int     # Log level for visibility
    ics: bool      # Has GUI? (Interface Control System)
```

### The Five Parameters

| Parameter | Type | Example | Function |
|-----------|------|---------|----------|
| `name` | str | `"Timer"` | Unique identity (logs, status) |
| `path` | Path | `Path("plugins/timer/main.exe")` | Absolute path to EXE |
| `enable` | bool | `True` | Start plugin at boot? |
| `level` | int | `4` | Log level for terminal visibility |
| `ics` | bool | `True` | Supports GUI window (pywebview)? |

> [!IMPORTANT]
> All five parameters are **mandatory**. If one is missing or an unknown key is present, a `ValueError` is thrown.

### Log Level Meaning

The `level` parameter controls the **terminal visibility** depending on `log_level` in the `config.yaml`:

| Level | Name | Description |
|-------|------|-------------|
| **0** | Off | Hides everything, including GUI windows |
| **1** | Silent | Hides console windows, GUI remains active |
| **2** | Default | Shows only main programs |
| **3** | Advanced | Also shows background services |
| **4** | Debug | Shows all activated processes |
| **5** | Override | Shows **every** process, even if `enable=False` |

**Logic:** A plugin is visible if `log_level >= plugin.level`.

**Level 0** and **Level 5** are special cases:
- Level 0 hides everything and sets `gui_hidden=True`
- Level 5 overrides all `enable` values and shows everything

---

### BUILDIN_REGISTRY (Core Modules)

The core modules are defined directly in `start.py`:

```python
BUILDIN_REGISTRY: list[AppConfig] = [
    AppConfig(name="App",              path=APP_EXE_PATH,    enable=True,        level=2, ics=False),
    AppConfig(name="Minecraft Server", path=SERVER_EXE_PATH, enable=True,        level=2, ics=False),
    AppConfig(name="GUI",              path=GUI_EXE_PATH,    enable=GUI_ENABLED, level=2, ics=False),
]
```

These cannot be changed from outside — they are an integral part of the system.

---

### PLUGIN_REGISTRY (Dynamic Plugins)

Plugins are stored in `PLUGIN_REGISTRY.json`. This file is automatically loaded at startup:

```json
[
  {
    "name": "Timer",
    "path": "C:\\...\\plugins\\timer\\main.exe",
    "enable": true,
    "level": 4,
    "ics": true
  },
  {
    "name": "Death Counter",
    "path": "C:\\...\\plugins\\deathcounter\\main.exe",
    "enable": true,
    "level": 4,
    "ics": true
  }
]
```

---

### How Plugins Register

Plugins register via the `--register-only` flag. The process:

```
1. registry.exe finds all main.exe in plugins/
   ↓
2. For each main.exe: starts with --register-only
   ↓
3. Plugin outputs AppConfig as JSON (REGISTER_PLUGIN: {...})
   ↓
4. registry.exe writes to PLUGIN_REGISTRY.json
   ↓
5. start.py reads PLUGIN_REGISTRY.json and starts plugins
```

**In the plugin (main.py):**
```python
from core import parse_args, register_plugin, AppConfig, get_base_file
from core.utils import load_config

args = parse_args()

if args.register_only:
    register_plugin(AppConfig(
        name="Timer",
        path=get_base_file(),
        enable=cfg.get("Timer", {}).get("Enable", True),
        level=4,
        ics=True
    ))
    sys.exit(0)

# ... rest of the plugin code
```

> [!IMPORTANT]
> **Time limit:** The registration process has a hard limit of **5 seconds**.
> Before `register_plugin()` there must be no slow code (no network access, no I/O operations).
> After `register_plugin()`, `sys.exit(0)` must follow immediately.

---

### How start.py Processes the Registry

`start.py` goes through **both** registries and starts the plugins:

```python
for registry in (BUILDIN_REGISTRY, PLUGIN_REGISTRY):
    for app in registry:
        if LOG_LEVEL == 0:
            # Level 0: Hide everything
            start_exe(path=app.path, name=app.name, hidden=True, gui_hidden=True)
        elif LOG_LEVEL == 5:
            # Level 5: Show everything
            start_exe(path=app.path, name=app.name, hidden=False)
        else:
            if app.ics and CONTROL_METHOD == "DCS" and app.enable:
                # GUI plugin in DCS mode: hide GUI, server only
                start_exe(path=app.path, name=app.name,
                          hidden=get_visibility(app.level), gui_hidden=True)
            elif app.enable:
                # Normal start
                start_exe(path=app.path, name=app.name,
                          hidden=get_visibility(app.level))
```

---

### Scan Cache (Performance)

To speed up the registration process, `registry.py` uses a **scan cache** (`plugin_registry_scan_cache.json`). If a plugin EXE has not changed (same file size and modification time), the result from the cache is used instead of restarting the plugin.

---

### Summary

| Component | File | Content |
|-----------|------|---------|
| **AppConfig** | `core/models.py` | Dataclass with 5 mandatory fields |
| **BUILDIN_REGISTRY** | `start.py` | Firmly defined core modules |
| **PLUGIN_REGISTRY** | `PLUGIN_REGISTRY.json` | Dynamically registered plugins |
| **Registration** | `registry.py` | Scans plugins with `--register-only` |
| **Scan cache** | `plugin_registry_scan_cache.json` | Speeds up repeated scans |

### → Continue to [GUI Architecture](./ch04-03-GUI-Architecture.md)
