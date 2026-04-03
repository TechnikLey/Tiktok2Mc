# Sending Data to Minecraft (Phase 3)

Now comes the action: the event is processed, and now Minecraft has to execute it. How does this communication work?

---

## The Problem: How Do We Tell Minecraft What to Do?

Minecraft is a game on a server. We are a Python program. **How do we communicate?**

Options:
- ✗ Write directly into the game code? (Too complicated, thousands of lines of code required)
- ✗ Chat messages? (Doesn't work technically)
- ✓ **Commands!** (This is the solution)

Minecraft has a **console** where you can enter commands:

```
/say "Hallo Welt!"
/give @s diamond 5
/function my_namespace:special_event
/tp @a 100 64 200
```

We just need to run these commands **remotely** (from outside). That's what **RCON** is for.

---

## Solution: RCON (Remote Console)

### What Is RCON?

**RCON** = Remote Console – a kind of "remote control" for Minecraft servers.

```
┌─────────────────────────────┐
│  Our Python program         │
│  "Run /say Thank you!"      │
└──────────────┬──────────────┘
               │ RCON command via network
               ↓
┌──────────────────────────────┐
│  Minecraft server            │
│  Console receives command    │
│  Executes /say               │
│  Result: Chat shows "Thanks!"│
└──────────────────────────────┘
```

### How RCON Works

1. **Establish connection**
   ```
   Program → "I am admin, here is the password"
   Server → Authentication OK, connection open
   ```

2. **Send command**
   ```
   Program → "/say User XY followed!"
   Server → Command is executed (visible in game)
   ```

3. **Confirmation** (optional)
   ```
   Server → Short response (usually empty or "ok")
   Program → Command processed
   ```

> [!NOTE]
> **Simplified representation!**
> 
> The above explanation is simplified for illustration. In reality:
> - RCON does not send meaningful replies like "5 players received a message"
> - The response is usually **empty**
> - We don't know if anything was actually executed
> - We don't know *what error* occurred if the command fails
> 
> This is a limitation of RCON. In practice: we send the command and hope it works.

### RCON Uses TCP/IP

RCON uses the **TCP/IP protocol** – the same Internet protocol used by email, websites, etc.

```
Our program       Network          Minecraft server
(Port XYZ)  ←------TCP/IP----→  (usually port 25575)
```

**Important details:**

- **Default behavior:** RCON normally connects for **each command individually** – open connection, send command, close connection.
- **The streaming tool:** Uses a **persistent connection** – the connection remains open. But this has to be set up specifically and is not the standard.
- **Reliability:** RCON is not guaranteed to be reliable. Commands can be lost and connections can drop. This is a known limitation.

> [!WARNING]
> **RCON has limitations:**
> - Not guaranteed reliable (commands may be lost)
> - Persistent connections must be implemented manually
> - No meaningful error responses
> - When a command fails, we often don't know it
> 
> The streaming tool handles this through:
> - Its own persistent connection management
> - Logging and retry mechanisms
> - Hoping it works

---

## From Event to Minecraft Command

### Example: User sends 5 gifts

```
1. PHASE 1: Event arrives
   TikTok: "User 'Streamer_Fan_123' sent 5x gifts"
   
   ↓
   
2. PHASE 2: Event is processed
   System: "This is a gift event, 5x"
   Data extracted: User = "Streamer_Fan_123", Quantity = 5
   Placed in queue → Waits for its turn
   
   ↓
   
3. PHASE 3: Command is sent to Minecraft
   System: "Which command should be triggered for 5x gifts?"
   (look up in `actions.mca`)
   
   Command: /say "Thanks to Streamer_Fan_123 for 5x gifts!"
   
   RCON: Send command to Minecraft
   
   ↓
   
4. RESULT: Minecraft executes
   Server: Chat shows "Thanks to Streamer_Fan_123 for 5x gifts!"
   All players see it
```

---

## The Internal Process: How Commands Are Processed

```
1. TAKE EVENT FROM QUEUE
   Gift event from Streamer_Fan_123
   
   ↓
   
2. LOOK UP ACTION
   "What should happen when a gift is received?"
   → Check actions.mca file
   → Command: /say "Thanks for the gift!"
   
   ↓
   
3. CHECK RCON CONNECTION
   Password: OK
   Port 25575: Reachable
   Server: Reachable
   
   ↓
   
4. SEND COMMAND
   Command: /say "Thanks for the gift!"
   
   ↓
   
5. HOPE THE COMMAND ARRIVES
   Server: ...
   
   ↓
   
6. LOGGING & COMPLETION
   Log: "Gift event processed, command successful"
   Event is done
```

---

## Error Scenarios: What Can Go Wrong?

| Problem | Consequence | Solution |
|---------|-------------|----------|
| **RCON server not reachable** | Commands cannot be sent | Check Minecraft server, firewall settings |
| **Incorrect password** | Authentication failed | Check password in config.yaml |
| **Wrong port** | Connection fails | Default: 25575, check in config.yaml |
| **Command syntactically incorrect** | Minecraft rejects it | Check command in actions.mca |
| **Too many commands per second** | Minecraft can't handle them all | Backlog builds up, player sees delayed reaction |
| **Minecraft server crashes** | RCON connection breaks | Auto-reconnect after restart |

---

## Summary of Phase 3

**What happens here:**
- Event is taken from the queue
- The matching Minecraft command is determined
- Command is sent to Minecraft via RCON
- Minecraft executes the command
- Commands are processed **one after the other** (not in parallel)

**What does not happen here:**
- We do not change the game code (that wouldn't work)
- We do not store events (that is a separate component)
- We do not show anything in the TikTok app (that is not possible)

> [!NOTE]
> RCON is synchronous and blocking. Bottlenecks can occur with many commands per second. That's why some tools use Minecraft functions (.mcfunction) for batch operations.
> (The streaming tool also does this – we'll talk about it later.)

---

## The Whole System Together

The 3 phases only work together:

```
Phase 1           Phase 2              Phase 3
RECEIVE      →   PROCESS         →    EXECUTE
  ↓                 ↓                    ↓
TikTokLive       Queue system         RCON commands
  ↓                 ↓                    ↓
Events in        Sort events          Minecraft reacts
```

**If a phase fails:**
- No Phase 1 → No events
- No Phase 2 → Commands are incorrect
- No Phase 3 → Minecraft does not respond

> [!TIP]
> If you understand how these 3 phases are connected, you understand the whole system. You will learn the details (exactly how RCON works, how to write commands, etc.) in the next chapters.

---

**Next chapter:** [Python in this project](./ch05-00-Python-in-This-Project.md) – Now let's look at how the code implements these 3 phases.
