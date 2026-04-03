# Plugin Structure & Setup

### Building a Plugin

Every plugin is an **isolated Python program** with a standard structure. Benefits:
- **Boilerplate code** already prepared
- **Core modules** for common tasks (config, logging, paths)
- **Automatic registration** in PLUGIN_REGISTRY

### Folder Structure

**Automatically created via PowerShell script (create_plugin.ps1):**
```
src/plugins/
└── my_plugin/
    ├── main.py           ← Plugin core
    ├── README.md        
    └── version.txt       
```

### Creating a Plugin: 2 Steps

If you use the PowerShell script `create_plugin.ps1`, it will ask you for the name of your plugin. It then automatically creates the complete folder structure for you. This then looks like this:

```text
.
├── your_plugin_name
│   ├── main.py
│   ├── README.md
│   └── version.txt
```

The new folder will be created at `src/plugins/` with the name you specified during creation.

## The Individual Files

### `main.py` – The Heart of Your Plugin

This is the most important file! This is where you write the actual logic of your plugin. If you create a plugin with `create_plugin.ps1`, you automatically get base code inserted. It looks something like this:

```python
from core import load_config, parse_args, get_root_dir, get_base_dir, get_base_file, register_plugin, AppConfig
import sys

BASE_DIR = get_base_dir()
ROOT_DIR = get_root_dir()
CONFIG_FILE = ROOT_DIR / "config" / "config.yaml"
DATA_DIR = ROOT_DIR / "data"
MAIN_FILE = get_base_file()
args = parse_args()

cfg = load_config(CONFIG_FILE)

gui_hidden = args.gui_hidden
register_only = args.register_only

if register_only:
    register_plugin(AppConfig(
        name="test",
        path=MAIN_FILE,
        enable=True,
        level=4,
        ics=False
    ))
    sys.exit(0)
```

> [!TIP]
> If you want to use a `config.yaml` file directly in the plugin folder, replace:
> ```python
> CONFIG_FILE = ROOT_DIR / "config" / "config.yaml"
> ```
>
> With this code:
> 
> ```python
> CONFIG_FILE = BASE_DIR / "config.yaml"
> CONFIG_FILE.touch(exist_ok=True)  # Creates the file if you haven't already done it yourself.
> ```

#### What Exactly Is Happening?

**Imports**  
You import functions and classes from the `core` module. This saves you a lot of writing work:
- `load_config`: Loads the configuration file
- `parse_args`: Reads command-line arguments
- `get_root_dir`, `get_base_dir`, `get_base_file`: Determine important directories and file paths
- `register_plugin`: Registers your plugin
- `AppConfig`: A class that stores the plugin configuration

**Setting Up Important Paths**  
```python
BASE_DIR = get_base_dir()     # The base folder of the application
ROOT_DIR = get_root_dir()     # The root path, two levels above BASE_DIR
CONFIG_FILE = ROOT_DIR / "config" / "config.yaml"  # Path to configuration
DATA_DIR = ROOT_DIR / "data"  # Folder for user data
MAIN_FILE = get_base_file()   # The path to main.exe (main.py in the dev folder)
```

You will need these variables later in your code — for example to save files or load the config.

**Reading Startup Arguments**  
```python
args = parse_args()
gui_hidden = args.gui_hidden       # Was the --gui-hidden flag set?
register_only = args.register_only # Was the --register-only flag set?
```

The program can start your plugin with certain flags:
- `--gui-hidden`: The GUI is started hidden
- `--register-only`: The plugin is only registered but not executed

**Registering the Plugin (if `--register-only` is set)**  
```python
if register_only:
    register_plugin(AppConfig(
        name="test",
        path=MAIN_FILE,
        enable=True,
        level=4,
        ics=False
    ))
    sys.exit(0)
```

If the plugin just needs to be registered, the following happens:

- **`name`**: The name of your plugin (e.g. "test")
- **`path`**: The path to the executable file
- **`enable`**: `True` = Plugin is active, `False` = Plugin is deactivated  
  *Tip: Instead of hardcoding `True/False`, you can also use config values:*  
  ```python
  enable=cfg.get("custom_name", {}).get("enable", True)
  ```  
  This is how users can turn your plugin on and off in the `config.yaml`!

- **`level`**: Determines when the terminal is visible (depending on the `log_level` in the `config.yaml`):
  - **Level 0**: Disables everything (should not be used)
  - **Level 1**: Terminal visible at `log_level: 1`
  - **Level 2**: Main programs (`log_level: 2`)
  - **Level 3**: Background services (e.g. checks, listeners)
  - **Level 4**: Debug/Development
  - **Level 5**: Overrides other settings (should not be used)

- **`ics`**: **I**nterface **C**ontrol **S**ystem – indicates whether the GUI is supported
  - `True` = GUI is supported
  - `False` = GUI is NOT supported (Direct Control System / DCS)

After registration, the program ends with `sys.exit(0)`.

---

> [!WARNING]
> **Plugin registration: order and time limit**
>
> The call to `register_plugin(...)` must occur as early as possible in the program.
> Before registration, **no executable code** may be present — except:
>
> * Imports
> * Configuration and path definitions
> * Argument parsing (e.g. `parse_args()`)
>
> **Not allowed before registration:**
>
> * Logic with side effects
> * Network access or file access
> * Initializations with external dependencies
> * `print` output or other I/O operations
>
> Background: The registration routine runs in a strictly limited environment and may otherwise fail.
>
> ---
>
> **Immediate exit required**
>
> After successfully calling `register_plugin(...)`, the program must be terminated immediately
> with `sys.exit(0)`.
>
> ```python
> if register_only:
>     register_plugin(AppConfig(
>         name="test",
>         path=MAIN_FILE,
>         enable=True,
>         level=4,
>         ics=False
>     ))
>     sys.exit(0)
> ```
>
> Without this immediate termination, you risk executing downstream code, which can corrupt or invalidate the registry.
>
> ---
>
> **Note the time limit**
>
> The registration process has a hard time limit of **5 seconds**.
> If this is exceeded, the program is terminated externally.

---

**Loading Configuration**  
```python
cfg = load_config(CONFIG_FILE)
```

Here the `config.yaml` is loaded. It contains all the settings for your plugin. `cfg` is now a dictionary you can access:
```python
# Example: Read out config value with default value
enable = cfg.get("custom_name", {}).get("enable", True)
```

This is what it should look like in the config.yaml:
```yaml
custom_name:
  enable: True
```

---

### `README.md` – Document Your Plugin

This file is your chance to show other developers what your plugin does. Write here:

- **What does the plugin do?** – A short description
- **Requirements** – What requirements does the user have to meet?
- **Configuration** – What options are available in the `config.yaml`?
- **Usage** – How is the plugin used?

A good README makes things easier for yourself and others later!

### `version.txt` – The Version Number

In this file you save the current version of your plugin. By default, when you create a new plugin it says:

```
v1.0.0
```

**Important:** Stick to this format! It follows the [Semantic Versioning](https://semver.org/) standard:
- **v1.0.0** = Major.Minor.Patch
- **Major**: Breaking changes (big changes)
- **Minor**: New features (backwards compatible)
- **Patch**: Bug fixes

Examples:
- v1.0.0 → v1.0.1 (small bug fix)
- v1.0.1 → v1.1.0 (new feature added)
- v1.1.0 → v2.0.0 (major conversion, no longer compatible)

---

## Plugins in Other Programming Languages

Can I also write my plugin in Java, C++, JavaScript etc.? **Yes, but...**

When you leave Python, you have to do a lot of things yourself that Python modules do for you. Just to give you an idea:
- Load config
- Read startup arguments
- Determine paths
- Register plugin
- Error handling

The basic structure can quickly require **several hundred lines of code** depending on the language — significantly more than the ~20 lines of Python above.

**Rule of thumb:** Python is the best place to start. If you need more performance later, you can always optimize performance-critical parts or create them in a different language.

---

**Next chapter:** [Webhook events and Minecraft integration](./ch02-02-webhook-events-and-minecraft-integration.md)

---
