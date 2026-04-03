# The Benefits of mcfunction Files

### The Problem: RCON Is the Bottleneck

If someone defines an extreme event:

```
7168:/execute at @a run summon minecraft:wither ~ ~ ~ x500
```

This means: **500 Withers spawn!**

**Without optimization:**
- Send 500 individual RCON commands → **Connection breaks down!**
- With throttling: ~5 second delay for this event only
- Other events have to wait → **Queue is full**

**The solution:** `.mcfunction` files!

---

### What Are .mcfunction Files?

`.mcfunction` files store a list of vanilla commands that the Minecraft server executes **internally**.

**Instead of:**
```
RCON: /summon wither x1
RCON: /summon wither x1
...  (500x!)
```

**Now:**
```
# 7168.mcfunction (saved file)
/execute at @a run summon minecraft:wither ~ ~ ~
/execute at @a run summon minecraft:wither ~ ~ ~
... (500x as text!)
```

**And then just:**
```
RCON: function namespace:7168
```

→ **One command instead of 500!**

---

### The Process

```
1. Program start
   ↓
2. actions.mca is read
   ↓
3. For every `/` command with `xN` (N > 1):
   → Write N lines to a .mcfunction file
   ↓
4. At runtime:
   Event arrives
   → Send only: "function namespace:7168"
   ↓
5. Minecraft server:
   → Executes all 500 commands in one tick!
   (1/20 second = super fast)
```

---

### Advantages

| Aspect | Without .mcfunction | With .mcfunction |
|--------|---------------------|------------------|
| RCON load | 500 packets | 1 packet |
| Speed | 5+ seconds | ~1 tick |
| Queue load | High | Minimal |
| Data throughput | Huge | Tiny |

---

### Limitations

**1. Vanilla commands only**

```
✓ /summon, /give, /execute (OK!)
✗ /mods-custom-command (Not OK!)
```

Plugin commands cannot be in files.

**Solution:** Use `!` prefix instead of `/` to send via RCON directly.

---

**2. Static generation (at startup)**

```python
# When starting the program:
for trigger, command in actions.mca:
    write_to_mcfunction(trigger, command)

# Changes to actions.mca are NOT live!
# You have to restart to load changes!
```

**Important:** `actions.mca` changes will only become active after the next restart!

---

**3. Server performance warning**

```
x500 means: The server must execute 500 commands in 1 tick!

✓ x10, x50 = OK
⚠ x100+ = warning from the program
✗ x500+ = Probably server crash or severe lags
```

**Don't overdo it!**

---

### Example

```
# Simple (RCON direct)
follow:/give @a diamond

# Complex (becomes .mcfunction)
7168:/summon minecraft:wither ~ ~ ~ x50
```

The program creates:

```
# 7168.mcfunction
/summon minecraft:wither ~ ~ ~
/summon minecraft:wither ~ ~ ~
...
(50x repeat)
```

When event `7168` fires:
- ONLY sends: `/function namespace:7168`
- Server executes file (50 commands in one tick!)

---

### Summary

- **Vanilla commands (`/`)** with `xN` → are stored in .mcfunction files
- **Plugin commands (`!`)** & **Built-in (`$`)** → sent directly via RCON
- **.mcfunction files** are generated at startup, not updated live
- **Performance:** `xN` should be ≤ 100 in order not to overload the server

→ **End!** Now you understand: TikTok → Events → Minecraft Commands!

---

→ [Next chapter: System architecture](./ch04-00-System-Modules-and-Integration.md)
