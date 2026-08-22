# Hook API Reference

All methods your hook can use via the `api` object in the `register()` function.

## Overview

| Method | Description |
|---------|--------------|
| `register_action(name, fn)` | Register handler for `$` commands |
| `rcon_enqueue(commands)` | Execute Minecraft commands |
| `enqueue_trigger(action_name, user="hook")` | Trigger another action (chained) |
| `get_hook_config(name)` | Read per-hook configuration |
| `send_overlay_text(title, subtitle="", duration=3, overlay_name="default")` | Display overlay text |
| `log(msg)` | Log hook-specific message |
| `config` (Property) | Read global config (copy) |

## register_action(name, fn)

Registers a handler function in the global `HOOK_ACTIONS` dictionary.

```python
api.register_action("superjump", my_handler)
```

- **name**: Must match the name after `$` in `actions.mca`
- **fn**: `(user: str, trigger: str, context: dict) -> bool | None`
- Duplicate registration is ignored (first call wins)

```python
def register(api: HookAPI):
    def handler(user, trigger, context):
        api.rcon_enqueue([f"say {user} triggered {trigger}!"])

    api.register_action("my-command", handler)
```

### Return Value — Veto Contract

A hook action may veto the trigger that called it by returning `False`:

| Return value | Effect |
|--------------|--------|
| `None` (default) / `True` | Chain continues as usual |
| `False` | The rest of this trigger's chain is aborted |

When a hook returns `False`, all following `$` actions of the same trigger
line are skipped, and overlay, vanilla, RCON and shell actions of that
trigger are not executed. Triggers already enqueued by earlier hooks
(via `enqueue_trigger`) are unaffected.

This enables gate-style hooks such as rate limiters or profanity filters:

```python
def register(api: HookAPI):
    recent: list[float] = []

    def anti_spam(user, trigger, context):
        now = time.time()
        recent[:] = [t for t in recent if now - t < 5]
        if len(recent) >= 10:
            return False  # too many events — block the whole trigger
        recent.append(now)

    api.register_action("gate", anti_spam)
```

In `data/actions.mca`, put the gate first so it runs before everything else:

```mca
gift:$gate|$say_thanks
```

## rcon_enqueue(commands)

Adds a list of Minecraft commands to the RCON queue.

```python
api.rcon_enqueue([
    "effect give @a minecraft:speed 30 2 true",
    f"say {user} triggered speed!",
])
```

- **commands**: `list[str]` — sent one after another to the Minecraft server
- The queue is asynchronous: the function does not block
- If the queue is full, commands are dropped and a `[HOOK] ... queue full` warning is logged

## enqueue_trigger(action_name, user="hook")

Triggers another action name (chained triggers).

```python
api.enqueue_trigger("explosion", user)
```

- Calls `execute_global_command(action_name, user)`
- **Maximum chain depth**: 3 (after which the trigger is locked)
- If exceeded, the action name is **permanently blocked for the session**

### Example: Chaining

```
actions.mca:
  follow: $greeting
  $greeting → enqueue_trigger("fireworks")
  fireworks → in actions.mca: fireworks: $effect
```

The hook reacts to `$greeting` and then triggers `fireworks`:

```python
def on_greeting(user, trigger, context):
    api.rcon_enqueue([f"say Hello {user}!"])
    api.enqueue_trigger("fireworks", user)
```

## get_hook_config(name)

Returns the configuration of a specific hook as a dict. The `name` parameter is the hook name (identical to the directory name and the `name` field in `hook.json`).

```python
config = api.get_hook_config("jump")
duration = config.get("duration", 10)
```

- Returns an empty dict `{}` if the hook has no configuration
- The configuration comes from the hook's `config.yaml` combined with the `config_schema`

## send_overlay_text(title, subtitle="", duration=3, overlay_name="default")

Displays an overlay text message.

```python
api.send_overlay_text("New Follower!", user, 5)
api.send_overlay_text("Gift", "Diamond", 3, "gift-overlay")
```

- **title**: Main text
- **subtitle**: Subtitle (optional)
- **duration**: Display duration in seconds (default: 3)
- **overlay_name**: Overlay channel (default: `"default"`)
- Returns `True` on success, `False` on error (e.g., when the API server is unreachable or the overlay is disabled)

## log(msg)

Writes a hook-specific log message.

```python
api.log(f"User {user} triggered an action")
```

- Appears in the log with `[HOOK]` prefix

## config (Property)

Read-only access to the global `config.yaml` (copy).

```python
glob_cfg = api.config
rcon_host = glob_cfg.get("server_host", "127.0.0.1")   # RCON host
```

## Error Codes for Hooks

| Code | Meaning |
|------|-----------|
| `HOOK-0001` | Hook manifest missing or invalid |
| `HOOK-0002` | `main.py` not found |
| `HOOK-0003` | Hook imports disallowed module |
| `HOOK-0004` | Hook failed to load |
| `HOOK-0005` | Hook registration failed |
| `HOOK-0006` | Hook script action failed |
| `HOOK-0007` | Hook has no `register()` function |

## Next Chapter

Learn how to define and read [Hook Configuration](./ch04-04-hook-configuration.md).
