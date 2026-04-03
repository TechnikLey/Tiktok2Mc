## Function of the `$random` Command

### What Is `$random`?

`$random` is a **built-in special command** that **randomly executes another trigger**.

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

```python
# 1. Parser sees: "likes:$random"
# → Saves: kind = "built_in", body = "random"

# 2. Like event occurs at runtime:
actions = ACTIONS["likes"]
for action in actions:
    if action["kind"] == "script":
        if action["body"] == "random":
            # Collect all possible triggers
            possible_triggers = get_all_triggers_except("likes")
            
            # Pick ONE at random
            chosen = random.choice(possible_triggers)
            
            # Execute THIS one
            execute_trigger(chosen)
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
> since all `follow`, `like` and the `$random` trigger itself
> are excluded from random selection.

---

### Special Features

**1. Self-recursion avoided**

```python
# $random will NOT be included in the list
possible_triggers = get_all_triggers()  # Filters out $random itself!
```

Otherwise: `likes:$random` could choose `$random` again = endless loop!

**2. All triggers are equally likely**

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
> More `$` commands are expected to be added in the future.
> However, these will no longer be described in the developer documentation,
> but only briefly mentioned in the user documentation.
> If you're interested in how they work, you'll have to read and understand the code yourself.

**Next chapter:** How do you write your own `$` command?

→ [Own $ command](./ch03-06-Creating-Your-Own-$-Command.md)
