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
| `event_subscriptions` | List of event types the plugin wants to receive via the EventBus. Supports exact types (`"tiktok.gift"`), prefix wildcards (`"tiktok.*"`, `"minecraft.*"`) and the catch-all `"*"`. TikTok events arrive as `tiktok_event`, all other sources as `bus_event`. **Without this field, no events will be delivered.** |
| `depends_on` | List of plugin names that must be active. If dependencies are not active or not registered, enabling the plugin fails (HTTP 422). |
| `capabilities` | List of capabilities the plugin provides. Used by the system for discovery, e.g., `["timer:countdown"]`. Other plugins can search for plugins with specific capabilities via the API. |
| `permissions` | Opt-in restriction of the plugin API surface: `["store", "network", "plugins", "events"]`. **A missing or empty list means the plugin runs unrestricted** (backward compatible). Once declared, every gated helper outside the list is denied with a safe fallback (`PLUGIN-0020`) — mirroring hook `permissions`. See [Permissions](./ch03-04-plugin-api.md#permissions-opt-in). |
| `config_schema` | Schema for the configuration (see [Configuration](./ch03-03-configuration.md)) |
| `comment_handler` | Object with `prefix` (string) and `enabled` (boolean). Declares that the plugin reacts to TikTok comments with a specific prefix (e.g., `"$"`). See [Receiving Events](./ch03-05-events-and-subscriptions.md). |
| `update_url` | URL for auto-updates, e.g., `"https://api.github.com/repos/TechnikLey/Tiktok2Mc/releases/latest"`. If empty string, no update check. |
| `platform` | Target platform: `"all"` (default), `"linux"`, or `"windows"`. Incompatible plugins cannot be enabled via the GUI or API. |
| `dashboard_ui` | `true` if the plugin provides a dashboard page (override `get_dashboard_html()` in your plugin class). The web dashboard then shows a tab with the plugin's page. See [Plugin API](./ch03-04-plugin-api.md#dashboard-pages). |
| `queries` | List of query names the plugin answers via `on_query()` (request/response channel), e.g. `["top", "stats"]`. Callers get an instant 404 for undeclared queries; without this field any query name is attempted. See [Querying Plugins](./ch03-04-plugin-api.md#querying-plugins-requestresponse). |
| `sandbox_profile` | `"light"`, `"moderate"` or `"strict"` — overrides the global sandbox profile for this plugin's process. Only takes effect when sandboxing is enabled in `config.yaml` (`plugin_sandbox.enabled`). See [Sandbox Profiles](#sandbox-profiles). |
| `icon` | Emoji shown in the GUI (Reactions tab). Defaults to `"🔌"`. |
| `emitted_events` | List of events this plugin publishes to the EventBus. Each entry: `key` (event id, e.g. `"my-plugin.thing"`), `name`, `desc`, `icon`. These appear as trigger options in the GUI "Create Reaction" wizard, automatically grouped under the plugin's own name. Optional: `name_i18n` (object with language codes as keys, e.g. `{"de": "Neues Ding"}`) and `desc_i18n` for localized display. |
| `accepted_commands` | Object of commands this plugin accepts via the command queue. Each command: `name`, `desc`, `args` (object of argument schemas with `type`, `label`, `default`, `min`, `max`, `options`, `placeholder`, `hint`). These appear as action options in the GUI "Create Reaction" wizard. Optional: `name_i18n`, `desc_i18n` for localized display. |

> [!NOTE]
> The internal fields `ics` (boolean, default `true`) and `level` (integer 1–4, default `4`) are set automatically. You usually do not need to specify them in the `plugin.json`.

### Sandbox Profiles

Plugin subprocesses can be restricted with resource limits
(`plugin_sandbox.enabled: true` in `config.yaml`). Instead of tuning raw
values, you can pick a **built-in profile** via `plugin_sandbox.profile`:

| Profile | Memory | CPU time | Files | Processes | Priority |
|---------|--------|----------|-------|-----------|----------|
| `light` | 1 GB | unlimited | 256 | 64 | below normal |
| `moderate` *(default values)* | 512 MB | 1 h | 256 | 32 | below normal |
| `strict` | 256 MB | 15 min | 128 | 8 | idle |

Individual plugins can override the global profile per process by adding
`"sandbox_profile": "strict"` to their `plugin.json`. Unknown names fall
back to the global configuration. Note that memory limits apply on Linux
directly and on Windows via a job object; CPU/file/process limits are
Linux-only.

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
  "icon": "⚡",
  "platform": "all",
  "emitted_events": [
    {
      "key": "my-plugin.thing",
      "name": "Thing Happened",
      "desc": "Fires when the plugin's thing happens",
      "icon": "✨"
    }
  ],
  "accepted_commands": {
    "do_thing": {
      "name": "Do Thing",
      "desc": "Triggers the thing",
      "args": {
        "count": { "type": "number", "label": "How many", "default": 1, "min": 1 }
      }
    }
  },
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

> [!NOTE]
> The `emitted_events` and `accepted_commands` fields power the **Reactions tab** in the dashboard. The GUI fetches them via `GET /api/v1/reactions/catalog`, which merges every plugin's declarations with the built-in core events (TikTok, Minecraft, Server). Plugin events are grouped under the plugin's own name in the "Create Reaction" wizard — a new plugin shows up automatically, no GUI code changes required.
>
> **Delivery-side use:** the declarations are also used at runtime. Subscriptions in `event_subscriptions` are checked against the unified event catalog (core events + all `emitted_events`) — an exact event name nobody declares produces a warning in the API log (typo protection; wildcards are never flagged). Likewise, commands delivered via `POST /plugins/{name}/command` that are not in `accepted_commands` are logged as a warning but still delivered. The catalog response carries a `version` field so tools can detect schema changes.

> [!NOTE]
> **Language of plugin content:** The application interface is available in English and German. However, text provided by plugins (event names, descriptions, command labels, config help text, overlay content) may appear in the plugin author's language if they have not been translated. Plugin authors can optionally provide localized strings via `name_i18n` / `desc_i18n` fields in `emitted_events` and `accepted_commands`, but this is not required. When no translation is available for the selected language, the original plugin string is shown.

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
