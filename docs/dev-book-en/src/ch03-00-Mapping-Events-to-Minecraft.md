# Mapping Between Events and Minecraft

### The Big Mystery: How Does TikTok Connect to Minecraft?

You now know how **events** are processed in Python. But:

> How does the program tell Minecraft what to do?

**An event handler queued an action, but:** What is an action? How does it become a Minecraft command?

**The answer:** A **mapping system** that translates events into Minecraft commands.

```
TikTok Event (Gift, Follow, Like)
        ↓
Event handler
        ↓
Queue: ("GIFT_ROSE", "anna_xyz")
        ↓
MAPPING SYSTEM (this chapter!)
        ↓
Run Minecraft Command
        ↓
Something happens in the game!
```

---

### The Mapping Visualized

The mapping works like a large reference book:

```
TRIGGER (from event)  →  MINECRAFT COMMAND
─────────────────────────────────────────────────────
"GIFT_ROSE"           →       /give @s rose
"GIFT_DIAMOND"        →       /give @s diamond
"FOLLOW"              →       /say Welcome!
"LIKE_GOAL_100"       →       /summon firework_rocket
```

**The file `actions.mca`:** This is our mapping table! It *defines* what happens when a trigger arrives.

---

### The Complete Process (Overview)

When someone follows you on TikTok, this happens:

```
1. TikTok sends: FollowEvent
2. Python handler: on_follow() called
3. Handler queues: ("FOLLOW", username)
4. Worker thread: `for trigger, user in trigger_queue.get():`
5. Worker thread: `action = ACTIONS_MAP["FOLLOW"]`
6. Worker thread: `send_command_to_minecraft(action)`
7. RCON protocol: Command is sent (via network)
8. Minecraft server: `/say Welcome, anna_xyz!`
9. **Result:** The message appears in the chat
```

**This process can take < 100ms for a follow! From TikTok to Minecraft!**

---

### Important to Understand

**3 things together make up the system:**

1. **actions.mca** – The file with all mappings (static)
2. **Code in main.py** – Reads the file at startup
3. **RCON protocol** – Sends commands to Minecraft (network)

**Why this separation?**

- ✓ Users can edit `actions.mca` without changing code
- ✓ Errors in the file are detected at startup
- ✓ Commands can be generated dynamically

---

### After This Chapter You Will Understand:

- How a `.mca` file is structured
- Why the validator is important
- How to add your own commands
- Why RCON is "insecure" (and why that's OK)
- When you need .mcfunction files

Continue to:
→ [The actions.mca file](./ch03-01-The-actions.mca-File.md)

---
