# Import Restrictions

Hooks run directly in the bridge process. For security reasons, hooks are not allowed to import arbitrary Python modules. The system checks all imports when loading and blocks disallowed modules.

## Allowed Imports

The following modules may be used in hooks:

| Module | Purpose |
|---|---|
| `time` | Time delays and timestamps |
| `random` | Random values |
| `logging` | Logging |
| `json` | JSON processing |
| `urllib` | HTTP requests (limited) |
| `requests` | HTTP requests (if installed) |
| `core.hook_api` | Hook API import for type annotations |
| `core.plugin_config` | Plugin configuration (if needed) |

## Why This Restriction?

1. **Security**: Hooks could otherwise perform dangerous operations.
2. **Stability**: External modules could destabilize the bridge process.
3. **Portability**: In a bundled application (`.exe`), only certain modules are available.

## What to Do When an Import Is Missing?

Most required functions are available through the Hook API:

| Required Function | API Alternative |
|---|---|
| Send Minecraft commands | `api.rcon_enqueue()` |
| Trigger triggers | `api.enqueue_trigger()` |
| Display overlay text | `api.send_overlay_text()` |
| Read configuration | `api.get_hook_config()` |
| Logging | `api.log()` |

## Example: Correct Hook

```python
from core.hook_api import HookAPI

def register(api: HookAPI):
    def my_handler(user, trigger, context):
        api.rcon_enqueue([f"say {user} triggered {trigger}!"])

    api.register_action("my-command", my_handler)
```

> [!NOTE]
> Importing `HookAPI` is optional, but recommended for type annotations and IDE support. At runtime, it is ignored.
