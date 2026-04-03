# The File `actions.mca`

> [!NOTE]
> In this and other files we use the term "plugin".
> There are two meanings: plugins for Minecraft and plugins for the streaming tool.
> Which plugin is meant depends on the context.

### What Is actions.mca?

The `actions.mca` is a simple text file that specifies **what happens in Minecraft** when a specific TikTok event arrives. Each line is a mapping from a trigger to one or more commands:

```
TRIGGER:<TYPE>COMMAND xNUMBER
```

- **TRIGGER** = name or ID (e.g. `follow`, `8913`)
- **TYPE** = prefix: `/` (vanilla), `!` (Plugin/Custom), `$` (special function)
- **COMMAND** = The command to execute
- **xNUMBER** = Optional: Repeat command N times

You can find the full syntax reference in the next chapter → [Syntax & Commands](./ch03-02-Structure.md)

---

### Where Is the File?

| Path | Purpose |
|------|---------|
| `defaults/actions.mca` | Template with example mappings |
| `data/actions.mca` | Actually loaded and used |

On first startup, `defaults/actions.mca` is copied to `data/actions.mca`. From then on, only `data/actions.mca` is used.

---

### Validation: Errors Are Detected Early

At startup, `generate_datapack()` in `main.py` parses every line of the `actions.mca`:

```python
# main.py - generate_datapack():
for line_num, original_line in enumerate(f, 1):
    line = original_line.split("#", 1)[0].strip()  # Remove comments
    if not line or ":" not in line:
        continue
    trigger, full_cmd_line = map(str.strip, line.split(":", 1))
    # ...
    if not cmd.startswith(("/", "!", "$")):
        print(f"[ERROR] Invalid command without prefix on line {line_num}: {cmd}")
```

**Every command needs a prefix** (`/`, `!` or `$`). Lines without a valid prefix are skipped at startup with an error message.

---

### A Real Example

From `defaults/actions.mca` (abbreviated):

```
# Basic Events
follow:/give @a minecraft:golden_apple 7
like_2:/clear @a *; /kill @a
likes:/execute at @a run summon minecraft:creeper ~ ~ ~ x2

# Gifts (TikTok gift IDs)
5655:!tnt 2 0.1 2 Notch
16111:/give @a minecraft:diamond
5487:/give @a minecraft:totem_of_undying

# Special ($random randomly selects another trigger)
16071:$random

# Complex (multiple command types mixed)
11046:/clear @a *; /execute at @a run summon minecraft:wither ~ ~ ~ x20; !tnt 20 0.1 2 Notch
```

**What happens here:**
- `follow` → Golden apples for all players
- `like_2` → Empty inventory + kill all players
- `likes` → 2 Creepers spawn (vanilla with `x2`)
- `16071` → Random trigger (`$random`)
- `11046` → Three commands in a row: Clear, 20 Wither, TNT

---

### The Process: From Event to Minecraft Command

```
Event handler:
  trigger_queue.put_nowait(
    ("follow", "anna_123")
  )                                ← TRIGGER in queue!
        ↓
Worker thread:
  trigger, user = trigger_queue.get()
  → "follow" is in valid_functions   ← Trigger recognized!
        ↓
Datapack / RCON:
  follow.mcfunction contains:
  give @a minecraft:golden_apple 7   ← Execution!
        ↓
RESULT: Everyone gets golden apples
```

---

### Summary

| Concept | Explanation |
|---------|-------------|
| **Format** | `TRIGGER:<TYPE>COMMAND xNUMBER` |
| **Files** | `defaults/actions.mca` (template) → `data/actions.mca` (active) |
| **Validation** | `generate_datapack()` checks syntax at startup |
| **Process** | Event → Queue → Worker → RCON/Datapack → Minecraft |

→ [Next chapter: Syntax & Commands](./ch03-02-Structure.md)

---
