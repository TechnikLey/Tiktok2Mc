# Hook Structure & Manifest

Each hook lives in its own directory under `src/hooks/<name>/`. The `hook.json` manifest identifies it.

```
src/hooks/<name>/
├── hook.json          # Manifest (required)
├── main.py            # Hook code (required)
└── config.yaml        # Configuration (optional, created automatically)
```

## hook.json — The Manifest

### Required Fields

| Field | Type | Description | Example |
|------|-----|--------------|----------|
| `name` | String | Unique hook name (lowercase, digits, hyphens, underscores) | `"jump"` |
| `version` | String | Semantic version | `"1.0.0"` |
| `display_name` | String | Display name | `"Super Jump"` |

### Important Optional Fields

| Field | Type | Description |
|------|-----|--------------|
| `description` | String | Short description |
| `author` | String | Developer name |
| `min_api_version` | String | Minimum Hook API version (currently `1.0.0`, see `src/core/version.py`) |
| `capabilities` | Array | List of capabilities, e.g., `["hook:random"]` — discovery/advertising tags, not permissions |
| `permissions` | Array | Granted API permissions: any of `"rcon"`, `"triggers"`, `"overlay"`, `"store"`, `"network"` (see [Hook API](./ch04-03-hook-api.md)); guarded calls without a matching permission are denied |
| `depends_on` | Array | List of plugin names that must be active |
| `plugin` | String | For plugin-bundled hooks: the plugin name |
| `config_schema` | Object | Schema for the hook configuration (see [Configuration](./ch03-03-configuration.md)) |
| `update_url` | String | URL for auto-updates, e.g., `"https://api.github.com/repos/TechnikLey/Tiktok2Mc/releases/latest"` |

### Complete Example

```json
{
  "name": "jump",
  "version": "1.0.0",
  "display_name": "Super Jump",
  "description": "Gives all players jump boost",
  "author": "Your Name",
  "min_api_version": "1.0.0",
  "capabilities": ["hook:jump"],
  "permissions": ["rcon", "overlay"],
  "config_schema": {
    "version": 1,
    "fields": [
      {
        "key": "duration",
        "type": "integer",
        "default": 10,
        "min": 1,
        "max": 300,
        "label": "Effect Duration (seconds)"
      }
    ]
  }
}
```

## main.py — The Entry Point

The hook **must** export a `register` function at the top level:

```python
from core.hook_api import HookAPI

def register(api: HookAPI):
    def handler(user, trigger, context):
        duration = api.get_hook_config("jump").get("duration", 10)
        api.rcon_enqueue([f"effect give @a minecraft:jump_boost {duration} 5 true"])

    api.register_action("jump", handler)
```

### Important Rules

- The function **must** be named `register` (case-sensitive)
- Without `register`, the hook will not be loaded (error: `HOOK-0007`)
- First `register_action` call wins — duplicate names do not overwrite
- The handler function must accept three parameters: `(user, trigger, context)`

## How Hooks Are Loaded

1. **Discovery**: `_discover_hook_dirs()` scans `src/hooks/*/hook.json`
2. **Import check**: AST check for disallowed imports (see [Import Restrictions](./ch04-05-import-restrictions.md))
3. **Import**: The hook is loaded via `importlib.util.spec_from_file_location()` + `module_from_spec()` (not `importlib.import_module`), allowing direct file-path imports without package structure.
4. **Register**: `module.register(api)` is called
5. **Flat vs. Tree**: In flat layout, `src/hooks/` is searched; in tree layout, subdirectories are also searched

## Enable/Disable Hooks

- **Via the GUI**: The API server manages `data/hook_registry.json`
- **Via the API**: `POST /api/v1/hooks/<name>/enable` or `.../disable`

## Next Chapter

The [Hook API Reference](./ch04-03-hook-api.md) describes all available methods.
