# Hook API Reference

All methods your hook can use via the `api` object in the `register()` function.

## Overview

| Method | Description |
|---------|--------------|
| `register_action(name, fn)` | Register handler for `$` commands |
| `rcon_enqueue(commands)` | Execute Minecraft commands |
| `enqueue_trigger(action_name, user="hook", context=None)` | Trigger another action (chained) |
| `get_hook_config(name)` | Read per-hook configuration |
| `send_overlay_text(title, subtitle="", duration=3, overlay_name="default")` | Display overlay text |
| `store_get(key, default=None)` | Read from this hook's persistent store |
| `store_set(key, value)` | Write to this hook's persistent store |
| `store_delete(key)` | Delete a key from the persistent store |
| `store_all()` | Read the whole persistent store |
| `log(msg)` | Log hook-specific message |
| `config` (Property) | Read global config (copy) |

## register_action(name, fn)

Registers a handler function in the global `HOOK_ACTIONS` dictionary.

```python
api.register_action("superjump", my_handler)
```

- **name**: Must match the name after `$` in `actions.mca`
- **fn**: `(user: str, trigger: str, context: HookContext) -> bool | None`
  — `user` is always the plain username string; event data lives in
  `context` (see below)
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
gift:$gate;$say_thanks
```

## Handler Context — Structured Event Data

The third handler argument is a **`HookContext`** — a `dict` subclass
describing the event that started the chain. It is built by the event
source and always contains at least:

| Key | Type | Meaning |
|-----|------|---------|
| `event` | `str` | Trigger family: `"gift"`, `"follow"`, `"like"`, `"comment"`, `"join"`, `"share"` or the trigger name for webhook/hook sources |
| `source` | `str` | Where the trigger came from: `"tiktok"`, `"webhook"` (custom_trigger/test/API dispatch) or `"hook"` |

Event-specific keys are added on top:

| Event | Extra keys |
|-------|------------|
| `gift` | `gift_name`, `gift_id`, `streak` (combo length; `1` for non-combo gifts), `combo` |
| `comment` | `comment`, `is_moderator`, `is_super_fan`, `in_fanclub` |
| `like` | `total_since_start`, `milestone_every`, `milestone_rule` |
| hook-enqueued (`enqueue_trigger`) | `hook` (your hook's name), plus whatever you pass via `context=` |

Keys are only present when meaningful (e.g. `combo` is absent for
non-gift events). Read required keys as attributes and optional keys via
`.get()`:

- `context.event`, `context.streak` — attribute access, fails fast with
  an `AttributeError` on unknown keys (typo protection)
- `context.get("combo", False)` — optional keys with defaults
- Full dict compatibility stays intact: `in`, iteration,
  `json.dumps(context)` all work

Internal machinery such as the trigger chain depth is deliberately
**not** part of the context — it describes the event, not the dispatcher.

### Example: Gift Combo Bonus

Because the context carries the finished streak length, a combo bonus is
a simple threshold check — combo gifts fire once when the streak ends,
with `streak` holding the total number of gifts:

```python
def register(api: HookAPI):
    def combo_bonus(user, trigger, context):
        if context.event != "gift":
            return
        if context.gift_name == "Rose" and context.streak >= 10:
            api.rcon_enqueue([f"say {user} sent a {context.streak}x Rose combo!"])
            api.enqueue_trigger(
                "mega_celebration", user,
                context={"event": "gift", "gift_name": "Rose",
                         "streak": context.streak},
            )

    api.register_action("combo_check", combo_bonus)
```

```mca
gift:$combo_check;$say_thanks
```

## Permissions

Side-effecting API calls are guarded by **permissions** declared in your
`hook.json` (separate from `capabilities`, which are discovery tags):

| Permission | Grants |
|------------|--------|
| `rcon` | `rcon_enqueue` |
| `triggers` | `enqueue_trigger` |
| `overlay` | `send_overlay_text` |
| `store` | `store_get`, `store_set`, `store_delete`, `store_all` |
| `network` | `request` (control-plane HTTP helper) |

Ungated methods that always work: `register_action`,
`register_lifecycle`/`on_live_start`/`on_live_end`, `log`,
`get_hook_config`, `config`, `get_valid_functions`.

- A call without the matching permission is **denied** (logged as
  `HOOK-0009`) and returns its safe fallback (`None`, `False`, `{}` or
  the given default) — the hook keeps running, nothing crashes.
- Unknown permission names in `hook.json` produce a warning at load time.
- Declare only what you use. Note: permissions guard the **HookAPI
  surface** only — a hook may still import raw `urllib`/`requests`
  directly; process-level sandboxing is a separate topic.

```json
{
  "name": "jump",
  "permissions": ["rcon", "overlay"]
}
```

## request(path, payload=None, method=None, timeout=5)

Synchronous request/response against the control plane (`J.2 Nr. 8`).
Returns the **parsed JSON body** (`dict`/`list`/str/...), or `None` when
the body is empty or the call fails — failures are logged, never raised.

- `path` is relative to the API base `/api/v1`, e.g.
  `"plugins/spotify/state"`.
- `payload=None` sends a GET; passing a payload sends it as JSON via POST
  (override with `method="PUT"` etc.).
- Requires the `network` permission.

```python
def register(api: HookAPI):
    def handler(user, trigger, context):
        state = api.request("plugins/spotify/state")
        track = (state or {}).get("state", {})
        if track.get("name"):
            api.send_overlay_text(title=track["name"], subtitle=track["artists"])
        else:
            api.send_overlay_text(title="Spotify", subtitle="No active track")

    api.register_action("spotify_current", handler)
```

Example — send a notification with self-contained channel settings.
Built-in channels are `log`, `overlay`, `sound`, `tts` and `discord`;
each entry carries its own parameters inline:

```python
result = api.request("notifications", payload={
    "title": f"Thanks for the follow, {user}!",
    "channels": {"discord": {"webhook_url": webhook_from_hook_config}},
})
# result -> {"sent": [...], "failed": [...], "skipped": [...]} or None
```

- `overlay`: `{"overlay_name": "default", "duration": 4}` — OBS overlay text
- `sound`: `{"file": "data/sounds/alert.wav"}` — plays a .wav file (Windows)
- `tts`: `{"rate": 0, "timeout": 15}` — speaks the text via Windows SAPI
- `discord`: `{"webhook_url": "https://discord.com/api/webhooks/..."}`

Every request carries its own parameters, so different actions can target
different webhooks or sounds independently; unknown channel names come back
as `skipped` (with a `NOTIF-0002` warning in the API log), failed
deliveries as `failed` (`NOTIF-0001`) — neither ever raises.

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

## enqueue_trigger(action_name, user="hook", context=None)

Triggers another action name (chained triggers).

```python
api.enqueue_trigger("explosion", user)
```

- Calls `execute_global_command(action_name, user)`
- **Maximum chain depth**: 3 (after which the trigger is locked)
- If exceeded, the action name is **permanently blocked for the session**
- **context**: optional dict forwarded to the new chain's hook actions
  (see [Handler Context](#handler-context--structured-event-data)). When
  omitted, the new chain starts with `{"source": "hook", "hook": <name>}`.

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

## Persistent Store

Every hook automatically gets its own namespace in the API's namespaced
persistent store (`data/plugin_data/<hook-name>.json`). The `api` object
handed to `register()` is already bound to your hook's name — no HTTP
boilerplate needed:

```python
def register(api: HookAPI):
    def track(user, trigger, context):
        count = api.store_get("count", 0)
        api.store_set("count", count + 1)

    api.register_action("track", track)
```

| Method | Behavior |
|--------|----------|
| `store_get(key, default=None)` | Returns the value, or `default` if the key does not exist / the store is unreachable |
| `store_set(key, value)` | Persists any JSON-serializable value; returns `True`/`False` |
| `store_delete(key)` | Deletes a key; returns `True` when it existed |
| `store_all()` | Returns all key/value pairs as a dict |

Keys must match `[A-Za-z0-9_.-]{1,128}`. Values survive restarts and are
written atomically. The dashboard can read the same data via
`GET /api/v1/plugins/<hook-name>/data`.

## Lifecycle Callbacks

Hooks can register callbacks that fire when the TikTok live connection is
established or when the live stream ends. These are useful for sending
startup/shutdown announcements, resetting internal state, or synchronizing
with external services.

```python
def register(api: HookAPI):
    def on_start():
        api.send_overlay_text("Stream Online!", "Hooks are active", 5)
        api.log("TikTok connection established — hook ready")

    def on_end():
        api.send_overlay_text("Stream Offline", "See you next time!", 5)
        api.log("TikTok stream ended — hook shutting down")

    api.on_live_start(on_start)
    api.on_live_end(on_end)
```

- **`on_live_start(fn)`** — Called once when the bridge successfully connects
  to the TikTok live stream (`ConnectEvent`). Runs in a background executor;
  exceptions in one hook never block other hooks.
- **`on_live_end(fn)`** — Called once when the live stream ends
  (`LiveEndEvent`). Also offloaded to the background executor.
- The generic form is `api.register_lifecycle(event, fn)` with `event` being
  `"live_start"` or `"live_end"`. The convenience methods are preferred.

> [!NOTE]
> Callbacks are synchronous (no `async def`). They run in a thread pool to
> avoid blocking the TikTok client thread. Keep them short; heavy work should
> be offloaded via `api.rcon_enqueue`, `api.enqueue_trigger`, or HTTP calls.

## Runtime Hook Reload

**Enable/disable hooks or change their config without restarting the bridge.**

When you:
- Enable or disable a hook via the dashboard (`POST /hooks/{name}/enable|disable`)
- Save hook configuration (`PUT /hooks/{name}/config`)
- Call `POST /reload` with `"hooks": true`

the bridge picks up the `reload_hooks` signal within ~1 second and
re-registers all enabled hooks automatically. Your hook's `register()` runs
again, so it reads the fresh config and re-registers its actions.

> [!IMPORTANT]
> - `register()` is called **every reload**, not just once. Write it to be
>   idempotent (e.g., `register_action` ignores duplicates, so re-registering
>   the same action name is safe).
> - Per-hook config is re-read at reload time via `get_hook_config()`.
> - If your hook holds external resources (files, connections), you may want
>   to detect reloads. One pattern:
>   ```python
>   def register(api: HookAPI):
>       if not hasattr(register, "_first_run"):
>           register._first_run = True
>           # One-time setup (open connection, etc.)
>       # Re-register actions (safe to call again)
>       api.register_action("my_action", handler)
>   ```

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
| `HOOK-0008` | Hook lifecycle callback failed |
| `HOOK-0009` | Hook permission denied (missing entry in `permissions`) |

## Next Chapter

Learn how to define and read [Hook Configuration](./ch04-04-hook-configuration.md).
