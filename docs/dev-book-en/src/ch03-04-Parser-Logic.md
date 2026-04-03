## How Is the Format Processed?

### The Process at Program Start

Processing of the `actions.mca` file takes place **at startup**:

```
1. Program start
   ↓
2. Load file "actions.mca"
   ↓
3. Validator checks for errors
   ↓
4. Parser parses each line:
   - Read trigger
   - Determine command type (/, !, $)
   - Extract repeats (x)
   ↓
5. Build in-memory dictionary:
   ACTIONS = {
     "follow": [...],
     "8913": [...],
     "likes": [...]
   }
   ↓
6. Done! File is loaded into RAM
   ↓
7. Worker thread: Lookup is very fast!
```

---

### Code Example: Parser Logic

```python
def parse_actions(filename):
    actions = {}
    
    with open(filename) as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            
            # Skip comments & empty lines
            if not line or line.startswith("#"):
                continue
            
            # Parse format: "trigger:command x repeat"
            if ":" not in line:
                print(f"[ERROR] Line {line_num} has no ':' separator")
                continue
            
            trigger, cmd_part = line.split(":", 1)
            trigger = trigger.strip()
            
            # Extract repetitions
            repeat = 1
            if " x" in cmd_part:
                cmd_part, repeat_str = cmd_part.rsplit(" x", 1)
                try:
                    repeat = int(repeat_str)
                except ValueError:
                    print(f"[ERROR] Line {line_num}: no number after x")
                    continue
            
            # Determine command type
            cmd = cmd_part.strip()
            if cmd.startswith("/"):
                cmd_type = "vanilla"
                body = cmd[1:].strip()
            elif cmd.startswith("!"):
                cmd_type = "plugin"
                body = cmd[1:].strip()
            elif cmd.startswith("$"):
                cmd_type = "built_in"
                body = cmd[1:].strip()
            else:
                print(f"[ERROR] Line {line_num}: Invalid prefix")
                continue
            
            # Store
            if trigger not in actions:
                actions[trigger] = []
            
            actions[trigger].append({
                "type": cmd_type,
                "command": body,
                "repeat": repeat
            })
    
    return actions
```

---

### Command Type Differentiation

When parsing, a distinction is made between 3 types:

**Type 1: Vanilla (`/`)**

```python
if cmd.startswith("/"):
    kind = "vanilla"
    body = cmd[1:]  # Remove "/"
```

→ Is saved to a `.mcfunction` file
→ Can be run directly by the Minecraft server

---

**Type 2: Plugin (`!`)**

```python
elif cmd.startswith("!"):
    kind = "plugin"
    body = cmd[1:]  # Remove "!"
```

→ Sent to Minecraft via RCON
→ Is a custom/plugin command (not vanilla)

---

**Type 3: Built-in (`$`)**

```python
elif cmd.startswith("$"):
    kind = "built_in"
    body = cmd[1:]  # Remove "$"
```

→ Processed by the program itself
→ Example: `$random` chooses another trigger

---

### Runtime: Lookup Is Very Fast

When an event occurs at runtime:

```python
# Event handler sends trigger
trigger = "follow"

# Worker thread performs lookup:
if trigger in ACTIONS:
    for action in ACTIONS[trigger]:
        execute(action["command"], repeat=action["repeat"])
```

**Super fast!** Dictionary lookup is very fast.

Regardless of whether 10 or 10,000 actions are defined — the lookup is **equally fast!**

---

### Why `kind` Is Important

```python
# kind determines the processing:

if kind == "vanilla":
    # Save to .mcfunction file
    # Runs natively by the server
    save_to_mcfunction(body)

elif kind == "plugin":
    # Send directly to server via RCON
    rcon_execute(body)

elif kind == "script":
    # Interpreted by the program (e.g. $random)
    execute_built_in(body, source_user)
```

The `kind` distinction determines **how** the command is executed!

---

### Performance Note

**All command types have the same performance!**

The cost of an action depends on:
- **What** the command does (not **which** type)
- E.g. `/summon` takes longer than `/say`
- E.g. `!tnt 1000` takes longer than `!tnt 1`

Type (/, !, $) doesn't matter from a performance perspective!
<br>It depends on the command.

---

### Summary

1. **Parser** disassembles actions.mca once at startup
2. **In-memory dictionary** is built
3. **Command types** are classified (/, !, $)
4. **Runtime** = fast dictionary lookups
5. **No parsing at runtime** = more performance

---
