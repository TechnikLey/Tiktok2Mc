## Follow Events

### What's Special About Follows: Simple and Direct

Follows are much **simpler** than gifts, because:

| Feature | Gifts | Follows |
|---------|-------|---------|
| **Multiple processing** | Combo possible (5x, 10x, etc.) | Always only 1x |
| **Status updates** | Streaking: Multiple notifications | No notifications |
| **Trigger management** | Name AND ID possible | A single trigger: `"follow"` |
| **Error complexity** | High (combos, streaking, race conditions) | Low (linear flow) |

**The good news:** Follow handlers are **perfect for learning**, because they show the basic structure without much complexity.

---

### Follow Event Structure: What Can We Read?

A `FollowEvent` contains this information:

```python
event.user.nickname          # Viewer name: "anna_xyz"
event.user.user_id           # Viewer ID (numeric)

event.follow_user.nickname   # The account that was followed
event.follow_user.user_id    # ID of the followed account

event.timestamp              # Timestamp of the event
event.event_type             # Type of event (usually: "follow")
```

**In practice:** We mainly need `event.user.nickname` to know **who** followed.

---

### Follow Event Processing: The 3-Step Flow

When a follow event arrives, the flow is very simple:

```
1. RECEIVE EVENT
   FollowEvent arrives
   
2. READ & SANITIZE USERNAME
   username = get_safe_username(event.user)
   e.g.: "anna_xyz"
   
3. PLACE TRIGGER IN QUEUE
   There is only one trigger: "follow"
   → Execute action or ignore
```

**Visual:**

```
Viewer follows stream
        ↓
TikTok sends: FollowEvent
        ↓
[STEP 1] Event received ✓
        ↓
[STEP 2] Username = "anna_xyz" ✓
        ↓
[STEP 3] Trigger "follow" defined? 
         YES → Queue: ("follow", "anna_xyz")
         NO  → Ignore
        ↓
Worker thread processes
```

---

### Follow Data Structure in Code

If you want to debug in the follow handler, you can use these properties:

```python
@client.on(FollowEvent)
def on_follow(event: FollowEvent):
    # Who followed?
    follower_name = event.user.nickname
    follower_id = event.user.user_id
    
    # Who was followed?
    followed_user = event.follow_user.nickname
    followed_id = event.follow_user.user_id
    
    # When?
    timestamp = event.timestamp
    
    # Debug:
    print(f"{follower_name} follows {followed_user} at {timestamp}")
```

**Note:** In most cases we only care about `event.user.nickname`, because we want to know who followed.

---

### Simple Error Handling

Since follow events are simple, we need less error handling:

```python
try:
    username = get_safe_username(event.user)
    # ... rest of the code
except AttributeError:
    logger.error("Follow event is incomplete", exc_info=True)
except Exception as e:
    logger.error(f"Error in follow handler: {e}", exc_info=True)
```

**Main risks:**

- `event.user` doesn't exist? → `get_safe_username()` protects against this
- `get_safe_username()` returns an empty string? → OK, gets queued anyway
- Queue is full? → Very rare, try-except is sufficient

---

### Practical Example: A Complete Follow Handler

Here is the standard follow handler with best practices:

```python
@client.on(FollowEvent)
def on_follow(event: FollowEvent):
    """
    Processes follow events from TikTok.
    - Simple structure (no combos)
    - Works directly with trigger 'follow'
    """
    try:
        # STEP 1: Read username
        username = get_safe_username(event.user)
        
        # STEP 2: Logging
        logger.info(f"Follow received from: {username}")
        
        # STEP 3: Check if follow trigger is defined
        if "follow" not in TRIGGERS:
            logger.warning("No 'follow' trigger defined, ignoring event")
            return
        
        # STEP 4: Place follow action in queue
        try:
            MAIN_LOOP.call_soon_threadsafe(
                trigger_queue.put_nowait,
                ("follow", username)
            )
            logger.debug(f"✓ Follow action queued for: {username}")
        except Exception as e:
            logger.error(
                f"Error queuing follow action: {e}",
                exc_info=True
            )
    
    except AttributeError as e:
        logger.error(
            f"Follow event is incomplete: {e}",
            exc_info=True
        )
    except Exception as e:
        logger.error(
            f"Unexpected error in follow handler: {e}",
            exc_info=True
        )
```

**What does this code do?**

1. **Read & sanitize username** – With `get_safe_username()`
2. **Logging** – We see in the log who follows
3. **Check trigger** – Does the "follow" trigger exist?
4. **Queue** – With `call_soon_threadsafe()`
5. **Error handling** – Everything is protected

---

### Even Simpler: Minimal Example

The absolute minimal handler (also works!):

```python
@client.on(FollowEvent)
def on_follow(event: FollowEvent):
    username = get_safe_username(event.user)
    MAIN_LOOP.call_soon_threadsafe(
        trigger_queue.put_nowait,
        ("follow", username)
    )
```

**That's it!** Three lines, does exactly the same thing.

---

### Difference from Gifts (Comparison)

To understand why follow handlers are so simple:

**Gift handler:**
```
if streaking: return           # ← Check streaking
count = repeat_count or 1      # ← Multiple processing
for _ in range(count):         # ← Loop!
    queue.put(...)
```

**Follow handler:**
```
queue.put(...)                 # ← Direct, no loop needed!
```

That's the main difference!

---

### Edge Cases (When Things Go Wrong)

What can go wrong with follows?

| Scenario | Consequence | Solution |
|----------|-------------|----------|
| `event.user` is None | AttributeError | `get_safe_username()` raises exception |
| Username is empty string `""` | Gets queued as-is | Normal, no problem |
| "follow" trigger doesn't exist | Event is ignored | Early return |
| Queue full (extremely rare) | `put_nowait()` exception | Try-except catches it |
| TikTok sends follow 2x quickly | Two events in succession | Both are processed (intended!) |

**Conclusion:** Follow handlers are **very robust** – there's little that can go wrong.

---

### Summary & Next Step

**What you know now:**

| Concept | Explanation |
|---------|-------------|
| **Follow = Simple** | No combos, no streaking, only 1 trigger |
| **3-step flow** | Username → Check → Queue |
| **Trigger "follow"** | The only trigger for follow events |
| **Error handling** | Minimal needed, `get_safe_username()` covers a lot |
| **Best practice pattern** | Same as gifts, just much shorter |

**What happens AFTER the follow handler?**

The queued "follow" action is later processed by the worker thread (e.g. execute Minecraft command).

→ [Next chapter: Like events](ch05-07-Like-Events.md)

---

> [!TIP]
> Follow events are perfect for experimenting. Try extending the minimal handler (e.g. special handling for certain usernames).
