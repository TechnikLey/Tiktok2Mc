# Syntax & Commands

### Structure of a Line

```
TRIGGER:<TYPE>COMMAND xNUMBER
```

```
trigger_name:<type>command xnumber
│            │     │       │
│            │     │       └─→ Repeat (optional)
│            │     └───────→ The actual command
│            └───────────→ Prefix: /! or $
└─────────────→ The name that event handlers use
```

Every part is important:

| Part | Meaning | Example |
|------|---------|---------|
| **TRIGGER** | Unique name or ID | `8913`, `follow`, `likes` |
| **:** | Separator | `:` (always required) |
| **\<TYPE\>** | Type of command | `/`, `!`, `$` |
| **COMMAND** | What should happen? | `give @a diamond`, `tnt 2 0.1 2` |
| **xNUMBER** | How often? (Optional) | `x3`, `x10` (without x = 1×) |

---

### Practical Examples with Explanations

**Example 1: Simple gift with repetition**

```
8913:/execute at @a run summon minecraft:evoker ~ ~ ~ x3
```

- **8913** = Gift ID (evoker gift)
- **:** = Separator
- **/** = Vanilla Minecraft Command
- **execute at @a run summon minecraft:evoker ~ ~ ~** = What should happen
- **x3** = This action 3 times in a row

**Result:** The command is **executed 3 times** = 3 Evokers spawn!

---

**Example 2: Follow without repeat**

```
follow:/give @a minecraft:golden_apple 7
```

- **follow** = Special trigger for follow events
- **:** = Separator
- **/** = Vanilla Command
- **give @a minecraft:golden_apple 7** = What should happen
- *(no x)* = Only execute once

**Result:** All players receive 1x 7 golden apples.

---

**Example 3: Custom Command (Plugin)**

```
6267:!tnt 600 0.1 2 Notch
```

- **6267** = Gift ID (TNT gift)
- **:** = Separator
- **!** = Custom/Plugin Command (not vanilla)
- **tnt 600 0.1 2 Notch** = What should happen (custom syntax!)
- *(no x)* = Execute 1x

**Result:** Plugin command `!tnt` is executed.

---

**Example 4: Special function**

```
16071:$random
```

- **16071** = Gift ID
- **:** = Separator
- **$** = Special function (not a normal command!)
- **random** = Randomly choose another trigger
- *(no x)* = Execute 1x


**Example 5: Overlay Output (On-Screen Text)**

```
follow: >>New Follower!|{user} is now following you!|5
```

- **follow** = Special trigger for follow events
- **:** = Separator
- **>>** = Overlay output (text is shown on stream, not a Minecraft command!)
- **New Follower!|{user} is now following you!|5** = Text, subtitle, and duration (seconds), separated by |
- **x** is not supported here

**Result:**
An overlay appears on stream with the text `New Follower!` and the subtitle `{user} is now following you!` for 5 seconds.

> [!NOTE]
> The duration is optional, default is 3 seconds.
> `{user}` is automatically replaced by the name of the person who triggered the action (for likes, this is `Community`).

---

### Trigger Types Explained

**1. Gift IDs (numbers)**

```
5655:!tnt 2 0.1 2 Notch
8913:/execute at @a run summon minecraft:evoker ~ ~ ~ x3
```

Gift IDs are numerical and unique for each gift type on TikTok.
You can find the complete list of all gift IDs in `core/gifts.json`.

---

**2. Special Trigger: follow**

```
follow:/give @a minecraft:golden_apple 7
```

Reserved word for follow events. Is **always** written as `follow` (lowercase).

---

**3. Like triggers**

```
likes:/execute at @a run summon minecraft:creeper ~ ~ ~ x2
like_2:/clear @a *; /kill @a
```

Predefined triggers for like events:
- `likes` = Standard like event (frequency configurable in `config.yaml`)
- `like_2` = Additional like trigger (e.g. for milestones)

Can be configured in `config.yaml`.

---

### Command Types Explained

**Type 1: Vanilla Commands (`/`)**

```
/give @a minecraft:diamond
/execute at @a run summon minecraft:wither ~ ~ ~
/clear @a *
/say Welcome!
```

Starts with `/` → Standard Minecraft command. Is written into a `.mcfunction` file and executed via the datapack.

---

**Type 2: Plugin Commands (`!`)**

```
5655:!tnt 2 0.1 2 Notch
6267:!tnt 600 0.1 2 Notch
```

Starts with `!` → Custom command. Is sent **directly via RCON** to the server, **not** written into a `.mcfunction` file.

→ [Why the difference? → The benefits of .mcfunction files](./ch03-08-The-Use-of-mcfunction-Files.md)

---

**Type 3: Special Functions (`$`)**

```
16071:$random
```

Starts with `$` → Internal special function of the streaming tool. Currently only `$random` is implemented.

`$random` chooses a **random other trigger** and executes it. This prevents endless loops: triggers with `$random` as well as basic triggers like `likes`, `like_2` and `follow` are automatically excluded.

→ [Details about $random → Function of the $random command](./ch03-05-Function-of-the-$random-Command.md)

---

### Repetitions: The xNUMBER System

```
x3   = 3 times in a row
x10  = 10× in a row
x100 = 100× in a row
```

Without `x` the command is executed exactly **1×**.

```
8913:/execute at @a run summon minecraft:evoker ~ ~ ~ x3
```

Is **equivalent** to:

```
/execute at @a run summon minecraft:evoker ~ ~ ~
/execute at @a run summon minecraft:evoker ~ ~ ~
/execute at @a run summon minecraft:evoker ~ ~ ~
```

→ 3 Evokers spawn instead of 1.

---

**Combine multiple commands with `;`:**

```
11046:/clear @a *; /execute at @a run summon minecraft:wither ~ ~ ~ x20; !tnt 20 0.1 2 Notch
```

Separate commands with `;` → all are executed one after the other!
<br> From left to right

---

### Comments and Disabling

What comes after `#` is **ignored**:

```
#8913:/give @a minecraft:diamond
5655:/give @a minecraft:emerald
```

- Line 1 is **commented out** (is not read)
- Line 2 is **active** (is read)

**Benefit:** For disabling without deleting, or for writing notes

---

### Valid and Invalid Syntax

**Valid trigger names:**

```
✓ Letters (a-z, A-Z)
✓ Numbers (0-9)
✓ Underscores (_)

✗ Spaces
✗ Special characters except _
✗ Umlauts (ä, ö, ü)
```

**✓ CORRECT:**
```
follow:/give @a minecraft:golden_apple 7
8913:/execute at @a run summon minecraft:evoker ~ ~ ~ x3
16071:$random
5655:!tnt 2 0.1 2 Notch
```

**✗ WRONG:**
```
follow /give @a diamond           # ← Missing :
8913:               /give @a diamond  # ← Space after :
likes $random                        # ← Missing :
follow:/give @a diamond x          # ← x without a number
```

---

### Summary

| Concept | Explanation |
|---------| ------------|
| **Triggers** | Gift ID, `follow`, `likes`, `like_2` |
| **Command types** | `/` (Vanilla → mcfunction), `!` (Plugin → RCON), `$` (Special) |
| **xNUMBER** | Repeat command N times |
| **Semicolon** | Multiple commands in one line |
| **Comments** | `#` to disable/document |

→ [Next chapter: Design decisions](./ch03-03-Design-Decisions.md)

---
