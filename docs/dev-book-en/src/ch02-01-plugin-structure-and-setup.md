# Plugin Structure & Setup

### Building a Plugin

Every plugin is an **isolated Python program** with a standard structure. Benefits:
- **Boilerplate code** already prepared
- **Core modules** for common tasks (config, logging, paths)
- **Automatic registration** in PLUGIN_REGISTRY

### Folder Structure

**Automatically created via script (`create_plugin.py`):**
```
src/plugins/
└── my_plugin/
    ├── main.py           ← Plugin core
    ├── config.yaml       ← Plugin-specific configuration
    ├── README.md        
    └── version.txt       
```

### Creating a Plugin: 2 Steps

If you use the PowerShell script `create_plugin.py`, it will ask you for the name of your plugin. It then automatically creates the complete folder structure for you. This then looks like this:

```text
.
├── your_plugin_name
│   ├── main.py
│   ├── config.yaml
│   ├── README.md
│   └── version.txt
```

The new folder will be created at `src/plugins/` with the name you specified during creation.

## The Individual Files

### `main.py` – The Heart of Your Plugin

This is the most important file! This is where you write the actual logic of your plugin. If you create a plugin with `create_plugin.py`, you automatically get base code inserted. It looks something like this:

```python
import logging
import sys
from core import load_config, parse_args, get_plugin_dir, get_plugin_config_file, get_base_file, AppConfig
from python.registry import register_plugin

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S', stream=sys.stdout)
log = logging.getLogger(__name__)

PLUGIN_DIR = get_plugin_dir()
CONFIG_FILE = get_plugin_config_file()
MAIN_FILE = get_base_file()
args = parse_args()

cfg = load_config(CONFIG_FILE)

gui_hidden = args.gui_hidden
register_only = args.register_only

if register_only:
    register_plugin(AppConfig(
        name="test",
        path=MAIN_FILE,
        enable=cfg.get("Enable", True),
        level=4,
        ics=False,
        port=0
    ))
    sys.exit(0)
```

> [!TIP]
> Your plugin now has its own `config.yaml` in the plugin folder.
> It is automatically created and loaded – you don't need to worry about a thing.

#### What Exactly Is Happening?

**Imports**  
You import functions and classes from the `core` module. This saves you a lot of writing work:
- `load_config`: Loads the configuration file
- `parse_args`: Reads command-line arguments
- `get_plugin_dir`, `get_plugin_config_file`: Determine your plugin's directories and config file path
- `get_base_file`: Determines important file paths
- `register_plugin`: Registers your plugin (from `python.registry`)
- `AppConfig`: A class that stores the plugin configuration

**Setting Up Logging**  
```python
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S', stream=sys.stdout)
log = logging.getLogger(__name__)
```

The logging module is your primary tool for runtime diagnostics. This setup configures the root logger with:
- **`level=logging.INFO`**: Messages at INFO level and above (`INFO`, `WARNING`, `ERROR`, `CRITICAL`) are shown. Change to `logging.DEBUG` during development for more detail.
- **`format`**: Each log line includes a timestamp, severity level, and the message. Example: `14:32:07 [INFO] Plugin started successfully`
- **`stream=sys.stdout`**: Output goes to the console (stdout) so it appears in the plugin's terminal window.

After setup, use the logger throughout your plugin:
```python
log.info("Plugin started successfully")
log.warning("Config key missing, using default")
log.error("Something went wrong: %s", error_msg)
log.debug("Detailed debug info (only visible at DEBUG level)")
```

> [!TIP]
> This is the same logging pattern used across all built-in modules (`src/python/*.py`).  
> For file-based logging (writing to a `logs/` folder), see [Error Handling & Best Practices](./ch02-06-error-handling-and-best-practices.md).

**Setting Up Important Paths**  
```python
PLUGIN_DIR = get_plugin_dir()           # Your plugin's folder
CONFIG_FILE = get_plugin_config_file()  # Path to your plugin's config.yaml
MAIN_FILE = get_base_file()             # The path to main.exe (main.py in the dev folder)
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
        ics=False,
        port=0
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

- **`port`**: The network port your plugin's web server listens on (default `0` = no port / no web UI).  
  If your plugin serves an overlay or API, set this to its port number. The tool will show the URL (`http://localhost:<port>`) at startup so users can add it as an OBS Browser Source.

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
>         ics=False,
>         port=0
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

### `version.txt` – Version Number & Update URL

In this file you save the current version of your plugin and optionally a link
for the `plugin_updater.py` to check for updates. By default, when you create
a new plugin it says:

```
version: v1.0.0
update_url: 
```

**version:**  
The version number follows the [Semantic Versioning](https://semver.org/) standard:
- **v1.0.0** = Major.Minor.Patch
- **Major**: Breaking changes (big changes)
- **Minor**: New features (backwards compatible)
- **Patch**: Bug fixes

Examples:
- v1.0.0 → v1.0.1 (small bug fix)
- v1.0.1 → v1.1.0 (new feature added)
- v1.1.0 → v2.0.0 (major conversion, no longer compatible)

**update_url:**  
A GitHub API URL where the `plugin_updater.py` can check for new versions:
```
https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/releases/latest
```

The updater fetches the GitHub API, compares the `tag_name` version with the
local version, and downloads the matching release asset if a newer version
is found (Windows → `*.zip` with "Windows" in the name, Linux → `*.tar.gz`
with "Linux" in the name). The plugin's `config.yaml` is never overwritten.

If no `update_url` is set, the updater skips your plugin.

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

## Plugin Updates (plugin_updater.py)

External plugins can be updated automatically using `plugin_updater.py`
(compiled to `plugin_updater.exe`). It runs automatically when the streaming
tool starts (after the registry scan).

### How It Works

1. The updater scans all plugin directories for `version.txt` files.
2. If an `update_url` is set (GitHub API URL), it fetches the GitHub API.
3. The `tag_name` version of the release is compared to the local version.
4. If the release version is newer, the matching asset is downloaded.
5. The archive is extracted and the plugin files are replaced.
6. The plugin's `config.yaml` is **never overwritten**.

### Preparing a GitHub Release

For your plugin to be updatable, create a GitHub release with:

- **Tag**: e.g. `v1.1.0`
- **Asset (Windows)**: `myplugin-v1.1.0-Windows.zip`
- **Asset (Linux)**: `myplugin-v1.1.0-Linux.tar.gz`

The archive should have this structure:

```
myplugin-v1.1.0-Windows.zip
├── main.exe
├── version.txt
├── README.md
├── config.yaml     ← ignored (user config is preserved)
└── ...             ← additional resources
```

The `update_url` in your `version.txt` must look like this:
```
update_url: https://api.github.com/repos/{YOUR_USER}/{YOUR_REPO}/releases/latest
```

---

**Next chapter:** [Webhook events and Minecraft integration](./ch02-02-webhook-events-and-minecraft-integration.md)

---
