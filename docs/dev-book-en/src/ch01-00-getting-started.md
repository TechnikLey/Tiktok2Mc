# Quickstart

In 5 minutes you will create your first plugin and see how it lives in the system.

## Prerequisites

- Python 3.12+ installed
- TikTok2Mc cloned: `git clone https://github.com/TechnikLey/Tiktok2Mc.git`
- Dependencies installed: `pip install -r requirements.txt`

> [!TIP]
> Check all dependencies and auto-install missing ones:
>
> ```bash
> python check_deps.py              # Check + install
> python check_deps.py --check-only # Check only, don't install
> python check_deps.py --requirements  # Also run requirements.txt
> ```

### Python Packages (requirements.txt)

| Package | Required for |
|---------|-------------|
| PyYAML, Flask, fastapi, uvicorn, pydantic | Core |
| requests, python-multipart, psutil | Core |
| TikTokLive, mcrcon | Streaming |
| pyinstaller, packaging, ruamel.yaml | Build |
| cryptography | Security |
| PyQt6, PyQt6-WebEngine, qtpy | GUI (pywebview backend) |
| pytest, pytest-timeout | Tests |

### System Tools

| Tool | Required for | Installation |
|------|-------------|--------------|
| **git** | Clone, updates | Usually pre-installed |
| **java** | Minecraft server | `sudo apt install openjdk-21-jre-headless` |
| **Node.js + npm** | `build.py vsix`, `build.py ci` | https://nodejs.org/ |
| **@vscode/vsce** | `build.py vsix` | `npm install -g @vscode/vsce` |
| **binutils** | PyInstaller on Linux | See below |
| **NSIS** (optional) | Windows installer | https://nsis.sourceforge.io/ |

> [!NOTE]
> **Linux**: Building with PyInstaller requires `binutils`:
>
> ```bash
> sudo apt install binutils   # Debian / Ubuntu
> sudo pacman -S binutils     # Arch
> sudo dnf install binutils   # Fedora
> ```
>
> MCA tests and VSIX builds also require `nodejs`:
>
> ```bash
> sudo apt install nodejs npm   # Debian / Ubuntu
> sudo pacman -S nodejs npm     # Arch
> sudo dnf install nodejs npm   # Fedora
> ```

## 1. Create Plugin

```bash
python create_plugin.py
```

The script asks for a name (a-z, 0-9, hyphens). Example: `my-plugin`

After creation, the plugin is located at `src/plugins/my-plugin/`:

```
src/plugins/my-plugin/
├── plugin.json         # Manifest
├── main.py             # Entry point
├── config.yaml         # Configuration
├── version.txt         # Version
└── README.md           # Documentation
```

## 2. Write Plugin Code

Replace the content of `src/plugins/my-plugin/main.py`:

```python
import logging
from core.base_plugin import BasePlugin

log = logging.getLogger(__name__)

class MyPlugin(BasePlugin):
    PLUGIN_NAME = "my-plugin"

    def __init__(self):
        super().__init__()
        self.register_handler("tiktok_event", self._on_tiktok_event)

    def _on_tiktok_event(self, args):
        event_type = args.get("event_type", "")
        user = args.get("user", "")
        if event_type == "tiktok.follow":
            log.info(f"{user} is now following!")

    def get_overlay_html(self) -> str:
        return "<html><body>My Plugin is running!</body></html>"

if __name__ == "__main__":
    MyPlugin().run()
```

**Important**: The subprocess starts `main.py` as a Python file. The `if __name__` block ensures that `run()` is called — without it, the process exits immediately.

## 3. Add Event Subscription

Add the `event_subscriptions` field to `src/plugins/my-plugin/plugin.json`:

```json
{
  "name": "my-plugin",
  "event_subscriptions": ["tiktok.follow", "tiktok.gift"]
}
```

Without this declaration, your plugin will not receive any TikTok events.

## 4. Start the System

```bash
python run.py
```

Starts the API server at `http://127.0.0.1:29185`. The plugin watcher automatically registers all plugins from `src/plugins/`.

## 5. Activate Plugin

```bash
curl -X PUT http://127.0.0.1:29185/api/v1/plugins/my-plugin/enable
```

The supervisor then starts the subprocess: `python src/plugins/my-plugin/main.py`

Confirmation in the console: The plugin logs that it has started.

## 6. Send Test Event

```bash
python tests/send_trigger.py --event tiktok.follow --user TestUser
```

The console should display: `TestUser is now following!`

## 7. Disable Plugin

```bash
curl -X PUT http://127.0.0.1:29185/api/v1/plugins/my-plugin/disable
```

The system terminates the subprocess.

## Troubleshooting

| Problem | Cause | Solution |
|---------|--------|---------|
| Plugin not recognized | `plugin.json` missing or invalid | Check JSON syntax |
| Plugin does not start | `entry_point` incorrect | Check path in `plugin.json` |
| Events not arriving | `event_subscriptions` missing | Add field in `plugin.json` |
| `PLUGIN_NAME` wrong | Does not match `name` | Set both to the same value |

## Next Steps

You have your first plugin running. Read [Core Concepts](./ch02-00-core-concepts.md) for the architecture or jump directly into [Plugin Development](./ch03-00-plugins.md).
