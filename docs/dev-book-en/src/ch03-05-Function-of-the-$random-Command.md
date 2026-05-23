## Function of the `$random` Command

### What Is `$random`?

`$random` is an **event hook command included with the Streaming Tool** that **randomly executes another trigger**.

Example:

```
likes:$random
```

When a like event arrives → instead of always doing the same thing → **choose a different trigger at random!**

---

### Practical Use Case

You like chaotic live streams? Then:

```
likes:$random         # Every like event has a RANDOM effect!
```

**Result:** The stream is unpredictable and fun!

---

### How Does `$random` Work Internally?

`$random` is implemented as an event hook in `src/event_hooks/random.py`. At startup, the hook registers a handler via `api.register_action("random", random_handler)`. When a TikTok event triggers `$random`:

```python
# 1. Parser sees: "likes:$random"
# → Registers "random" as a $-command linked to its hook

# 2. At startup, event_hooks/random.py registers the handler:
api.register_action("random", random_handler)

# 3. Like event occurs at runtime → handler is called:
def random_handler(user, trigger, context):
    # Get all valid triggers from the current context
    all_valid = api.get_valid_functions()
    
    # Read the random_triggers config section
    cfg = api.config.get("random_triggers", {})
    mode = cfg.get("mode", "deny-all")
    configured = cfg.get("triggers", [])
    
    # Build the candidate pool based on the filter mode
    candidates = []
    for func in all_valid:
        if mode == "deny-all":
            if func not in configured:  # Deny only the listed triggers
                candidates.append(func)
        else:
            if func in configured:  # Allow only the listed triggers
                candidates.append(func)
    
    # Pick ONE at random and enqueue it
    if candidates:
        chosen = random.choice(candidates)
        api.enqueue_trigger(chosen, user)
```

---

### Example: Random Trigger Pool

```
# Definition
follow:/say Welcome!
5655:/give @a diamond
8913:/summon minecraft:evoker
likes:$random  ← Starts the random selection

# When likes:$random comes:
# 0% chance: /say Welcome!
# 50% chance: /give @a diamond
# 50% chance: /summon minecraft:evoker
# 0% chance: $random
```

> [!NOTE]
> The command `/say Welcome!` will never be executed,
> since `follow` is in the exclusion list by default.
> Which triggers are excluded is configurable in `config.yaml` under
> `random_triggers`. Use `mode: deny-all` to exclude only the listed triggers,
> or `mode: allow-all` to allow only the listed triggers.

---

### Special Features

**1. Loop protection**

If `$random` picks a trigger that itself contains `$random` (or another hook that calls back), the system's chain depth limit (3 levels) prevents infinite loops. After exceeding the limit, the trigger is permanently banned for the current session.

**2. Trigger filter is configurable**

In `config.yaml` under `random_triggers` you can define which triggers are allowed or blocked:

```yaml
random_triggers:
  mode: deny-all
  triggers:
    - likes
    - like_2
    - follow
```

With `deny-all`, only the listed triggers are excluded from `$random`.  
With `allow-all`, only the listed triggers remain eligible (all others are excluded).

**3. All triggers are equally likely**

```python
chosen = random.choice(possible_triggers)  # Uniform distribution
```

Every trigger has the **same chance** of being selected.

---

### When Do You Need This?

- **Chaos events** on the stream
- **Surprise effects** at milestones
- **Gameplay variability** (not always the same)
- **Mini games** (random rewards)

---

### Summary

`$random` is a **meta command** that:
- Randomly chooses another trigger
- Is evaluated at runtime (not at startup!)

> [!NOTE]
> Since v0.5.0 `$random` is now implemented as a standard event hook, you can study its
> source code at `src/event_hooks/random.py` as a real-world example of the hook API.

**Next chapter:** How do you write your own `$` command?

→ [Own $ command](./ch03-06-Creating-Your-Own-$-Command.md)