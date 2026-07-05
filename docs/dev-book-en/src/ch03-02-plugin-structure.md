# Plugin Structure & Manifest

Each plugin lives in its own directory under `src/plugins/<name>/`. The system recognizes it by the `plugin.json`.

## Directory Structure

```
src/plugins/<name>/
├── plugin.json          # Manifest (required)
├── main.py              # Plugin code (required)
├── config.yaml          # Configuration (optional, created automatically)
├── hooks/               # Optional: Plugin-bundled hooks
├── version.txt          # Optional: Created by scaffolder
└── README.md            # Optional: Documentation
```

## plugin.json — The Manifest

This is the recognition file. The `PluginWatcher` scans `src/plugins/*/plugin.json` on startup.

### Required Fields

| Field | Description | Example |
|------|--------------|----------|
| `name` | Unique name (lowercase, digits, hyphens). Regex: `^[a-z0-9]([a-z0-9-]*[a-z0-9])?$` | `"my-plugin"` |
| `version` | Semantic version | `"1.0.0"` |
| `entry_point` | Path to `main.py` relative to project root | `"src/plugins/my-plugin/main.py"` |
| `display_name` | Display name for the GUI | `"My Plugin"` |

### Important Optional Fields

| Field | Description |
|------|--------------|
| `description` | Short description (1-2 sentences) |
| `author` | Developer name |
| `homepage` | Project URL (e.g., GitHub repository) |
| `min_api_version` | Minimum version of the plugin API (currently `1.0.0`, see `src/core/version.py`). If incompatible, the plugin will not be started. |
| `max_api_version` | Highest supported API version. If the field is missing or `null`, there is no upper limit. |
| `event_subscriptions` | List of event types the plugin wants to receive via the EventBus. Supports wildcards like `"tiktok.*"`. **Without this field, no events will be delivered.** |
| `depends_on` | List of plugin names that must be active. If dependencies are not active, the plugin will not start (error `PLUGIN-0005`). |
| `capabilities` | List of capabilities the plugin provides. Used by the system for discovery, e.g., `["timer:countdown"]`. Other plugins can search for plugins with specific capabilities via the API. |
| `config_schema` | Schema for the configuration (see [Configuration](./ch03-03-configuration.md)) |
| `comment_handler` | Object with `prefix` (string) and `enabled` (boolean). Declares that the plugin reacts to TikTok comments with a specific prefix (e.g., `"$"`). See [Receiving Events](./ch03-05-events-and-subscriptions.md). |
| `update_url` | URL for auto-updates, e.g., `"https://api.github.com/repos/TechnikLey/Tiktok2Mc/releases/latest"`. If empty string, no update check. |

> [!NOTE]
> The internal fields `ics` (boolean, default `true`) and `level` (integer 1–4, default `4`) are set automatically. You usually do not need to specify them in the `plugin.json`.

### Complete Example

```json
{
  "name": "my-plugin",
  "version": "1.0.0",
  "entry_point": "src/plugins/my-plugin/main.py",
  "display_name": "My Plugin",
  "description": "React to follows and gifts",
  "author": "Your Name",
  "homepage": "https://github.com/YourName/Tiktok2Mc",
  "min_api_version": "1.0.0",
  "event_subscriptions": ["tiktok.follow", "tiktok.gift"],
  "capabilities": ["my-plugin:counter"],
  "depends_on": [],
  "update_url": "https://api.github.com/repos/YourName/Tiktok2Mc/releases/latest",
  "config_schema": {
    "version": 1,
    "fields": [
      {
        "key": "threshold",
        "type": "integer",
        "default": 10,
        "min": 1,
        "label": "Threshold",
        "category": "Events"
      }
    ]
  }
}
```

## main.py — The Entry Point

The system starts the subprocess with: `python src/plugins/<plugin-dir>/main.py`

The file must contain:

1. A class that inherits from `BasePlugin`
2. The attribute `PLUGIN_NAME` (must match `name` in `plugin.json`)
3. The method `get_overlay_html()`
4. An `if __name__ == "__main__"` block

```python
from core.base_plugin import BasePlugin

class MyPlugin(BasePlugin):
    PLUGIN_NAME = "my-plugin"

    def get_overlay_html(self) -> str:
        return "<html><body>Active</body></html>"

if __name__ == "__main__":
    MyPlugin().run()
```

**Without the `if __name__` block**, the subprocess would only read the class definition, create no instance, and exit immediately.

## Naming Conventions

| Element | Convention | Example |
|---------|------------|----------|
| `name` in `plugin.json` | Kebab-case (lowercase, digits, hyphens) | `my-plugin` |
| Directory name | Identical to `name` | `my-plugin` |
| `PLUGIN_NAME` in Python | Exactly like `name` in plugin.json | `"my-plugin"` |
| `entry_point` | Relative path | `src/plugins/my-plugin/main.py` |

**Consequence of deviation**: The plugin will be registered, but the subprocess will not start correctly.

## How the System Processes plugin.json

1. **Scan**: `PluginWatcher` scans `src/plugins/*/plugin.json` (also at runtime)
2. **Validation**: JSON is parsed, required fields are checked
3. **Registration**: Data is stored in the API server's `PluginRegistry` (`data/api_plugin_registry.json`)
4. **Activation**: Only when enabled (via API or GUI) is the subprocess started
5. **Signal file**: The API server writes `core/runtime/plugin_start_<name>`. The supervisor then starts the process.

## version.txt

The scaffolding script creates a `version.txt` in YAML format:

```
version: v1.0.0
update_url: https://api.github.com/repos/...
```

Used by the system for update checks.

## Next Chapter

In the next chapter you will learn about [Configuration](./ch03-03-configuration.md) in detail.
