## Creating Your Own `$` Commands

The Streaming Tool has an **event hook system** that lets developers write custom `$` commands — without modifying `main.py`.

You create a `.py` file in the `src/event_hooks/` folder, define a `register(api)` function inside it, and add the corresponding `$` command to the `actions.mca` file. When the bot starts next, your hook is loaded automatically and ready to use.

> [!WARNING]
> **Custom imports are restricted.**
>
> Hook scripts run inside the bundled application (`app.exe`). You are **not allowed to import arbitrary modules** — only the following are permitted:
>
> - `random`
> - `time`
> - (more in the future)
>
> All other functionality is available through the `api` object (e.g. sending RCON commands, firing triggers, logging, reading config).
> **Do not** use your own `import` statements for external packages like `requests`, `flask`, `aiohttp`, etc. — they are not available inside hook scripts and will cause a load error.

---

### How It Works

When the bot starts, all `.py` files in the `event_hooks/` folder are automatically loaded and integrated into the running process. No separate process and no separate executable is started per hook — everything runs directly inside the main application.

> [!NOTE]
> **Development vs. Release:**
> During development, the folder is located at `src/event_hooks/`. The build script copies it to `event_hooks/` in the release build. The bot always loads hooks from the release path (`event_hooks/`), not from `src/`.

The loading sequence in detail:

1. **Parsing:** `generate_datapack()` reads `actions.mca` and collects all `$` command names (e.g. `$welcome_message` → `welcome_message`)
2. **Import:** All `.py` files in `event_hooks/` are dynamically imported via `importlib`
3. **Registration:** For each loaded module, `register(api)` is called — this is where handlers are registered
4. **Execution:** When a TikTok event arrives and its trigger points to a `$` command, the matching handler is called immediately

---

### Creating a Hook

#### Step 1: Create the Hook Script

Create a new `.py` file in the `src/event_hooks/` folder.

**Example:** `src/event_hooks/welcome_message.py`

```python
def register(api):
    def welcome_message(user, trigger, context):
        api.rcon_enqueue([
            f"say {user} just followed!",
            "effect give @a minecraft:glowing 5 0 true",
        ])

    api.register_action("welcome_message", welcome_message)
```

What's happening here?

- `register(api)` is the **mandatory function** called by the system. Without it, the script is ignored.
- Inside `register()`, you define your handler as a closure — this gives it automatic access to `api`.
- `api.register_action("welcome_message", welcome_message)` registers the handler under the name `welcome_message`. This name must exactly match the `$` command in `actions.mca`.

#### Step 2: Add to `actions.mca`

The user (or you as a developer for testing) adds the command to `actions.mca`. The trigger key on the left side of `:` determines which TikTok event fires the hook:

```
follow: $welcome_message
```

In this example: every time someone follows on TikTok, the `welcome_message` hook is called.

#### Step 3: Start or Restart the Bot

Start the bot — or restart it if it's already running. The hook is loaded automatically and active immediately.

---

### The `register(api)` Function

Every hook file **must** provide a `register(api)` function at the top level. If it's missing, the script is **skipped** during loading and an error message is printed.

`register()` is called exactly once when the bot starts. Define all your handlers inside this function as closures — this way they automatically have access to the `api` object without needing global variables.

```python
def register(api):
    def my_handler(user, trigger, context):
        # Your logic here
        api.log(f"{user} triggered {trigger}")

    api.register_action("my_action", my_handler)
```

> [!WARNING]
> Files without a `register()` function are **not** loaded. The console will show:
> ```
> [HOOK] [ERROR] filename.py has no register() function — skipped.
> ```

---

### Handler Signature

Every handler must accept exactly **three arguments**:

| Argument | Type | Description |
|---|---|---|
| `user` | `str` | The TikTok username that triggered the event (e.g. `"max_mustermann"`) |
| `trigger` | `str` | The name of the `$` command currently being executed (e.g. `"welcome_message"`) |
| `context` | `dict` | Reserved for future extensions — currently always an empty `{}` |

```python
def my_handler(user, trigger, context):
    api.rcon_enqueue([f"say Hello {user}, trigger was: {trigger}"])
```

Missing or extra arguments will cause the handler to throw an error at call time (but the bot stays stable — see [Error Handling](#error-handling)).

---

### The `HookAPI`

The `api` object passed to `register()` is the only interface between your hook and the main system. It provides the following methods:

#### `api.register_action(name, fn)`

Registers a handler under the given name. The name must exactly match the `$` command in `actions.mca`.

```python
api.register_action("welcome_message", welcome_message)
```

> [!WARNING]
> If the same name is registered twice (e.g. in two different hook files), the **first** registration wins. The second is ignored and a warning is printed:
> ```
> [HOOK] [WARN] Duplicate action 'welcome_message' — first registration kept.
> ```

#### `api.rcon_enqueue(commands)`

Sends a list of Minecraft commands to the RCON queue. The commands are pushed into the queue in order and processed by the RCON worker from there.

```python
api.rcon_enqueue([
    "effect give @a minecraft:speed 10 2 true",
    f"say {user} triggered a speed boost!",
])
```

Each entry is a complete command as a string — **without** a leading `/`.

> [!NOTE]
> **Both vanilla and plugin commands are allowed.**
>
> Since everything goes through RCON, you can send not only vanilla Minecraft commands but also commands from installed server plugins (e.g. Bukkit/Paper/Spigot plugins). The server receives them exactly as if you had typed them into the server console.
>
> ```python
> api.rcon_enqueue([
>     "tnt 2 0.1 2 Notch",  # Example: plugin command
>     "say Boost active!",   # Vanilla command
> ])
> ```

#### `api.enqueue_trigger(trigger, user)`

Pushes a **trigger** into the trigger queue. The bot processes it exactly as if a TikTok event with that trigger had arrived — including **all** actions assigned to it in `actions.mca` (vanilla, RCON, overlay, further `$` commands).

> [!WARNING]
> **The first argument is a trigger — not a `$` command name.**
>
> A trigger is what stands **left** of the `:` in `actions.mca`.
> That includes gift IDs (`5655`), reserved event names (`follow`, `likes`), or custom triggers you defined yourself.
>
> What stands **right** of the `:` after the `$` — i.e. the command name like `welcome_message` or `superjump` — is **not** a valid trigger.
>
> ```
> follow: $welcome_message
> │         │
> │         └── $-command name (NOT a valid trigger)
> └──────────── trigger (this is what you pass to enqueue_trigger)
> ```
>
> `api.enqueue_trigger("welcome_message", user)` does **nothing** — silently ignored, no error, no warning.
> `api.enqueue_trigger("follow", user)` works — `follow` is on the left side of `actions.mca`.

> [!NOTE]
> The trigger is placed in the queue **asynchronously** — it is not processed immediately within the same handler call. The RCON commands from your current handler run first, then the forwarded trigger is picked up.

---

##### Variant A — Forwarding to an existing trigger

You can fire a trigger from inside a hook that is already registered in `actions.mca` for a different TikTok event.

`actions.mca`:
```
follow: $welcome_message; /give @a minecraft:golden_apple 7
5655:   $big_gift
```

```python
def register(api):
    def big_gift(user, trigger, context):
        api.rcon_enqueue([f"say Huge gift from {user}!"])
        # Also fire the "follow" trigger.
        # → The user gets the welcome message + golden apples on top.
        api.enqueue_trigger("follow", user)

    def welcome_message(user, trigger, context):
        api.rcon_enqueue([f"say Welcome {user}!"])

    api.register_action("big_gift", big_gift)
    api.register_action("welcome_message", welcome_message)
```

What happens on gift `5655`?

1. TikTok reports gift `5655` → trigger `5655` is processed
2. `execute_global_command("5655", …)` finds `$big_gift` → calls your handler
3. Handler sends the RCON message and pushes `"follow"` into the queue
4. Shortly after: `execute_global_command("follow", …)` runs — executes `$welcome_message` **and** `/give …`

This way a gift sender automatically gets the same treatment as a new follower, without duplicating the follow logic.

> [!WARNING]
> **Watch out for infinite loops!**
>
> Never forward to the trigger that fired your own handler:
>
> ```
> follow: $welcome_message
> ```
> ```python
> def welcome_message(user, trigger, context):
>     api.enqueue_trigger("follow", user)  # ← Loop!
> ```
>
> As soon as someone follows on TikTok, the `follow` trigger fires. The handler pushes `follow` back into the queue, the handler fires again, pushes `follow` again — and so on.
>
> The system detects this automatically at runtime. After 3 chain steps the trigger is blocked and permanently banned for the running session:
>
> ```
> [HOOK] [ERROR] enqueue_trigger('follow') blocked — chain depth 4 exceeds maximum (3).
>                Trigger 'follow' is now permanently banned for this session. Possible infinite loop.
> ```
>
> Every further `enqueue_trigger("follow", ...)` call — from any hook — is then immediately rejected:
>
> ```
> [HOOK] [ERROR] enqueue_trigger('follow') permanently blocked — trigger was banned after loop detection.
> ```
>
> **What still executes?**
>
> `enqueue_trigger` does not throw an exception — it simply does a silent `return` back to the caller. That means:
>
> - **The rest of the handler continues normally.** If `welcome_message` has more code after the `enqueue_trigger` call (e.g. more `rcon_enqueue` calls, logging, etc.), it runs in full. Only that one `enqueue_trigger` call is blocked.
>
> - **The remaining actions from the `actions.mca` line also run normally.** Given:
>   ```
>   follow: $welcome_message; /give @a minecraft:golden_apple 7
>   ```
>   The handler `welcome_message` is called (including all code after the blocked call), and the `/give` command is executed afterwards **as normal** — the ban only affects the `enqueue_trigger` call, nothing else.

---

##### Variant B — Creating your own trigger

Triggers in `actions.mca` do not have to be real TikTok events. You can define **your own triggers** — they are just as valid as `follow` or a gift ID, but are never fired automatically by TikTok. They only fire when you push them via `enqueue_trigger`.

`actions.mca`:
```
5655:      $small_gift
8913:      $big_gift
thank_you: $thank_you
```

Here `thank_you` is a custom key. No TikTok event is named that — it exists purely as an internal chain step that your hooks call via `enqueue_trigger`.

```python
def register(api):
    def small_gift(user, trigger, context):
        api.rcon_enqueue(["effect give @a minecraft:speed 5 1 true"])
        api.enqueue_trigger("thank_you", user)

    def big_gift(user, trigger, context):
        api.rcon_enqueue(["effect give @a minecraft:speed 20 3 true"])
        api.enqueue_trigger("thank_you", user)

    def thank_you(user, trigger, context):
        api.rcon_enqueue([f"say Thank you {user} for the gift!"])

    api.register_action("small_gift", small_gift)
    api.register_action("big_gift", big_gift)
    api.register_action("thank_you", thank_you)
```

What happens on gift `5655`?

1. `execute_global_command("5655", …)` → finds `$small_gift` → calls your handler
2. Handler gives the speed effect and pushes `"thank_you"` into the queue
3. `execute_global_command("thank_you", …)` → finds `$thank_you` → calls the `thank_you` handler
4. Handler sends the thank-you message

On gift `8913` the same happens via `big_gift`, but the same `thank_you` action runs at the end. The logic is written only once.

---

##### Why create your own trigger?

A custom trigger is a full `actions.mca` entry. That means you can assign it not just a `$` hook, but the **entire palette** of `actions.mca` syntax — vanilla commands, RCON, overlay text, all at once:

```
thank_you: $thank_you; /playsound minecraft:entity.player.levelup master @a; >>Thanks!|{user} just donated!|4
```

When a hook calls `api.enqueue_trigger("thank_you", user)`, everything happens together: your Python handler runs, the sound plays via the datapack, and the overlay text appears in the stream.

The concrete benefits:

- **Reusability:** Any number of hooks can call the same trigger. The shared logic lives in one place — in the hook and/or in `actions.mca`.
- **Separation of code and configuration:** The streamer can add commands, sounds, or overlay text to the trigger in `actions.mca` without touching the Python file. You write the logic, the streamer configures the rest.
- **Chaining:** Triggers can fire other triggers — letting you build complex sequences from simple, testable building blocks.
- **Extensible later:** If the streamer wants to add a firework effect later, they change one line in `actions.mca` — done. No code deployment needed.

> [!TIP]
> Want to test if your triggers are working?
> Take a look at the GUIDE.md, chapter "Test Your Triggers Without TikTok". There you’ll find a test tool that lets you try out your triggers without any TikTok connection.
>
> If you have Python installed, you can also run the file `tests/send_trigger.py` directly in the development structure to test triggers conveniently from the console—without using the .exe.
> Even when testing with `send_trigger.py`, the project must be built and all other components must be running in the release environment.

#### `api.log(msg)`

Prints a message to the console with an automatic `[HOOK]` prefix. Useful for debugging.

```python
api.log("Hook loaded successfully")
# Output: [HOOK] Hook loaded successfully
```

#### `api.config`

Read-only access to the loaded values from `config.yaml`. Returns a nested dictionary.

```python
port = api.config.get("RCON", {}).get("Port", 25575)
```

---

### Using One Handler for Multiple `$` Commands

Sometimes multiple `$` commands should react similarly but with slight differences. In this case, register the same function under multiple names and use the `trigger` argument in the handler to distinguish which command is currently active.

```python
def register(api):
    def power_up(user, trigger, context):
        effects = {
            "superjump": "minecraft:jump_boost",
            "superrun":  "minecraft:speed",
            "superheal": "minecraft:regeneration",
        }
        effect = effects.get(trigger)
        if effect:
            api.rcon_enqueue([f"effect give @a {effect} 10 5 true"])

    api.register_action("superjump", power_up)
    api.register_action("superrun", power_up)
    api.register_action("superheal", power_up)
```

The user then adds to `actions.mca`:
```
5655: $superjump
16111: $superrun
7934: $superheal
```

This way you only need **one** handler for any number of related commands.

---

### Multiple Actions in One File

A single `.py` file can register as many actions as needed. You are not limited to one handler per file:

```python
def register(api):
    def on_follow(user, trigger, context):
        api.rcon_enqueue([f"say {user} is now following!"])

    def on_big_gift(user, trigger, context):
        api.rcon_enqueue([
            "summon minecraft:firework_rocket ~ ~ ~",
            f"say Thank you {user}!",
        ])

    api.register_action("follow_effect", on_follow)
    api.register_action("big_gift_effect", on_big_gift)
```

---

### Error Handling

Errors inside a hook handler do **not** crash the bot. They are caught and printed to the console with a `[HOOK]` prefix:

```
[HOOK] [WARN] Error in action 'welcome_message': name 'undefined_var' is not defined
```

There is also a safety net during loading:

- **Syntax error** in a hook file → only that file is skipped, all others load normally
- **Missing `register()` function** → file is skipped with an error message
- **Exception in `register()`** → file is skipped, error is logged
- **Exception in handler at runtime** → error is logged, bot keeps running

---

### Built-in Commands Cannot Be Overridden

> [!WARNING]
> Certain $-commands are built into the system and cannot be overridden by your own hooks.
> 
> Currently reserved names:
> - `random`
> 
> If you try to register one of these names with `api.register_action("random", ...)`, you will see this error at load time:
> ```
> [HOOK] [ERROR] 'random' is a reserved built-in command — cannot be overridden by a hook.
> ```
> 
> These commands are handled internally by main.py and are blocked for custom hooks.

→ [Next Chapter: RCON and Its Limitations](./ch03-07-Rcon-and-Its-Limitations.md)
