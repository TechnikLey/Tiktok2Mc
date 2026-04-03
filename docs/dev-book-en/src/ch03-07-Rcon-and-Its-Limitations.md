## RCON and Its Limitations

### What Is RCON?

**RCON = Remote Console** – A protocol to send commands to Minecraft from outside.

It works over **TCP/Port 25575** (by default). The Minecraft server must have `enable-rcon=true` in server.properties.

---

### The Problem: Limited Bandwidth

Imagine RCON like a **thin tube**:

```
TikTok commands
        ↓ (many arrive)
    RCON tube  ← Limited capacity!
        ↓ (must come out in order)
  Minecraft
```

**The problem:** If too many commands arrive at the same time → overload!

**The solution:** **Queues** – Process commands one after the other!

---

### Queue Limits

```python
trigger_queue = Queue(maxsize=10_000)  # Max 10k incoming events
rcon_queue = Queue(maxsize=10_000)     # Max 10k commands to Minecraft
like_queue = Queue()                   # ∞ (unlimited!)
```

**Why no limits on like_queue?**

Likes are small and come often → many in the queue is OK.
Like data is only `delta` (integer), not full commands!

---

### Dynamic Throttling

The system adjusts the sending speed:

```python
q_size = rcon_queue.qsize()
        wait_time = THROTTLE_TIME
        inner_pause = 0.01 

if q_size > 100:
    wait_time, inner_pause = 0.01, 0.001
elif q_size > 50:
    wait_time, inner_pause = 0.05, 0.005
elif q_size > 20:
    wait_time, inner_pause = 0.1, 0.01
```

**Effect:**
- If queue is large: process faster
- If queue is empty: send more slowly (save resources)

---

### Limitations & Edge Cases

| Problem | Consequence | Solution |
|---------|-------------|----------|
| Queue full | Events are lost | `put_nowait()` with exception handling |
| Connection breaks down | No commands arrive | Auto-reconnect |
| Command too big | RCON error | Split command |
| Sending too quickly | Minecraft crash | Adjust throttling |

---

### Best Practices

```python
# DO: Execute commands one after the other
while True:
    command = rcon_queue.get()
    minecraft_server.execute(command)
    time.sleep(0.05)  # Short pause for stability

# DON'T: Execute commands in parallel (leads to instability!)
for command in large_command_batch:
    minecraft_server.execute(command)  # ← Too fast!
```

> [!NOTE]
> This example is greatly simplified.
> Several hundred lines are necessary in the main program
> to operate RCON stably, catch errors cleanly,
> and reliably process all commands one after the other.

---

### Summary

- **RCON** = Network protocol for commands
- **Queued** = So as not to overload
- **Rate limiting** = Dynamically adjusted

→ [Next chapter: mcfunction files](./ch03-08-The-Use-of-mcfunction-Files.md)
