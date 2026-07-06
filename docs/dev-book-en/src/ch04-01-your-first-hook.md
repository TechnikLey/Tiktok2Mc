# Your First Hook

In this tutorial you will create your first hook. The hook will react to the `$superjump` command and give all Minecraft players a jump boost.

Along the way you will learn not only the code, but also how a hook lives in the bridge process: how it is loaded, how the `$` commands from `actions.mca` reach your handler, and how the system distinguishes hooks from plugins.

## Create Hook

The project includes a script that generates the basic structure for a hook:

```bash
python create_hook.py
```

The script asks for:

- **Hook name**: Only lowercase letters and digits, e.g., `jump`
- **Location**: Main hooks directory or plugin-bundled
- **Action name**: The name for the `$` command in `actions.mca`
- **Update URL**: Optional

After creation, you will find the hook at `src/hooks/jump/`:

```
src/hooks/jump/
├── hook.json
├── main.py
└── config.yaml
```

## Write Hook Code

Open `src/hooks/jump/main.py` and replace the content:

```python
from core.hook_api import HookAPI

def register(api: HookAPI):
    def superjump(user, trigger, context):
        api.rcon_enqueue([
            f"effect give @a minecraft:jump_boost 10 5 true",
            f"say {user} triggered a super jump!",
        ])

    api.register_action("superjump", superjump)
```

### What Happens Here Line by Line?

**`def register(api: HookAPI)`**: Every hook **must** define a function named `register` at the top level. The hook loader calls this function exactly once on startup and passes it a `HookAPI` object. Without this function, the hook will not be loaded (error `HOOK-0007`).

**`api.register_action("superjump", superjump)`**: Registers the handler function under the name `"superjump"` in the global `HOOK_ACTIONS` dictionary. When a `$superjump` command is later triggered in `actions.mca`, the system looks up the name in this dictionary and calls the associated function.

**`def superjump(user, trigger, context)`**: The handler function must accept three parameters:
- `user`: The TikTok username that triggered the event (string)
- `trigger`: The action name (here `"superjump"`)
- `context`: A dictionary for future extensions (currently empty)

**`api.rcon_enqueue([...])`**: Adds a list of Minecraft commands to the RCON queue. The commands are sent one after another to the Minecraft server.

## Add to actions.mca

Open the `actions.mca` (by default `data/actions.mca`) and add a line:

```
follow: $superjump
```

Every time someone follows on TikTok, the `$superjump` hook is triggered.

### How the `$` Command Flows – From TikTok Event to Handler

```
TikTok CommentEvent "follow"
       │
       ▼
on_comment() in main.py
       │
       ▼ Enqueue event into Trigger Queue
       │
trigger_worker() in main.py
       │
       ▼
execute_global_command("follow", user)
  │
  ├─ Checks: Is "follow" in ctx.script_actions?
  │   (Parsed from actions.mca on startup)
  │
  └─ Yes → For each action under "follow":
           ├─ Is "$superjump" registered in HOOK_ACTIONS?
           │   (Populated by register_action())
           │
           └─ Yes → superjump(user, "superjump", {}) called
                     │
                     ▼
                   api.rcon_enqueue(["effect give @a ...", "say ..."])
```

**Three Phases of Initialization:**

1. **Parse on startup**: The bridge process (`main.py`) reads the `actions.mca` and creates a dictionary `ctx.script_actions`. For each line like `follow: $superjump` it stores: `script_actions["follow"] = ["superjump"]`.
2. **Load hooks**: The hook loader iterates through `src/hooks/*/main.py`, imports each file, and calls `register(api)`. Handlers are registered in the global `HOOK_ACTIONS` dictionary.
3. **At runtime**: When a TikTok event arrives, `execute_global_command()` looks up the trigger in `script_actions`, then each action name in `HOOK_ACTIONS`, and calls the handler.

## Test the Hook

1. **Start TikTok2Mc**: `python start.py`
   The bridge process automatically loads all hooks from `src/hooks/`. In the console output you will see:
   ```
   [HOOK] Registered action: superjump
   ```

2. **Send a test trigger**:
   ```bash
   python tests/send_trigger.py --event tiktok.follow --user TestUser
   ```

3. **Check the output**: The console should display:
   ```
   TestUser triggered a super jump!
   ```

   If Minecraft is connected (RCON configured), all players will receive the jump boost effect.

## Disable Hook

Set `enabled: false` in the hook's `config.yaml` or disable the hook via the GUI. The system does not load disabled hooks. The `config.yaml` method is the recommended approach — removing from `src/hooks/` is only necessary if the hook should be permanently deleted.

## Difference from Plugin

| Aspect | Hook | Plugin |
|---|---|---|
| Execution location | Runs **directly in bridge process** | Own subprocess |
| Communication | **Direct function call** (no HTTP) | HTTP API (`send_command`, `api_post`) |
| Lifecycle | Loaded on startup, lives until shutdown | Started/stopped as subprocess |
| Latency | Milliseconds (no network) | Higher (polling interval 1s) |
| Complexity | Simple, just one function | Full class with threads |
| Use case | Simple `$` commands | Complex logic, GUI, state |

## Common Errors

| Error | Cause | Solution |
|---|---|---|
| Hook not loaded | `register()` function missing | Add `def register(api):` |
| `$superjump` does nothing | Action name in `actions.mca` doesn't match `register_action()` | Check both names for typos |
| Import error | Disallowed module imported (`os`, `sys`, etc.) | Use only the Hook API |
| `api.rcon_enqueue()` without effect | RCON not configured or Minecraft not connected | Check `config.yaml`: `rcon.host`, `rcon.port`, `rcon.password` |
| Trigger not fired | Trigger name not defined in `actions.mca` | Add `follow: $superjump` to `actions.mca` |

## Next Steps

In the next chapter you will learn about [Hook Structure & Manifest](./ch04-02-hook-structure-and-manifest.md) in detail.
