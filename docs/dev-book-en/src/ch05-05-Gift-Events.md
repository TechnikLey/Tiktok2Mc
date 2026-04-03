## Gift Events

### What's Special About Gifts: Combos and Streaks

Gifts are not simple like follows. A gift can arrive in **three different ways**:

| Situation | What happens | How often is the handler called? |
|-----------|--------------|----------------------------------|
| **Single gift** | Viewer sends gift 1x | 1x (immediately) |
| **Combo gift** | Viewer sends the **same** gift multiple times in quick succession | Multiple times (`repeat_count`) |
| **Streaking** | TikTok sends notifications about the current status of the combo | Multiple times (but: we want to SKIP these) |

This is important to understand **before** we write code:

```
Viewer sends 5 roses in a row:
  
  00:00 - Event: Gift='Rose', repeat_count=1, streaking=False
  00:01 - Event: Gift='Rose', repeat_count=2, streaking=False  
  00:02 - Event: Gift='Rose', repeat_count=3, streaking=False
  00:03 - Event: Gift='Rose', repeat_count=4, streaking=False
  00:04 - Event: Gift='Rose', repeat_count=5, streaking=True  ← Streak end!
  
TikTok also sends status updates:
  
  00:01 - Event: Gift='Rose', repeat_count=2, streaking=True ← IGNORE!
  00:02 - Event: Gift='Rose', repeat_count=3, streaking=True ← IGNORE!
  00:03 - Event: Gift='Rose', repeat_count=4, streaking=True ← IGNORE!
```

**Why is this important?** If we processed every status update, we would queue the same action 3–5x too many times.

---

### Gift Event Structure: What Can We Read from a Gift?

A `GiftEvent` contains this most important information:

```python
event.gift.name        # Gift name: "Rose", "Diamond", etc.
event.gift.id          # Gift ID: 1, 2, 3 (numeric)
event.gift.combo       # Can this gift be comboed? True/False

event.repeat_count     # How many times was the gift sent in total? 1, 2, 3, 4, 5...
event.streaking        # Is this a status update of a running combo? True/False

event.user.nickname    # Viewer name: "anna_123"
event.user.user_id     # Viewer ID (numeric)

event.gift_type        # Type of gift (usually: "gift")
event.description      # Detailed description (e.g. "Sent Rose x5")
```

**The practical meaning:**

- We need `repeat_count` to **know how often the action should be carried out**
- We need `streaking` to **know whether we should ignore this event**
- We need `gift.name` OR `gift.id` to **find which action matches**
- We need `user.nickname` to **record who sent the gift**

---

### Gift Event Processing: The 5-Step Process

When a gift event arrives, the following happens:

```
1. ARRIVE
   Event arrives → is it streaking? YES → STOP, ignore
   
2. COUNT
   Is it a combo gift? YES → count = event.repeat_count
                       NO  → count = 1
   
3. IDENTIFY
   Read gift name: "Rose"
   Sanitize (make safe): "Rose" → OK
   Read username: "anna_123"
   
4. MATCH
   Does "Rose" match an action? Check valid_functions
   If yes → that is our `target`
   If no  → ignore event
   
5. QUEUE
   for i in range(count):  # 5x, because repeat_count=5
       Queue: (target, username)
       
   Now the action is processed asynchronously
```

**Visual:**

```
TikTok sends: Gift Event (Rose, repeat_count=5, streaking=False)
    ↓
[STEP 1] streaking==False? ✓ Continue
    ↓
[STEP 2] combo==True? repeat_count=5 → count=5
    ↓
[STEP 3] name="Rose", user="anna_123" (sanitized)
    ↓
[STEP 4] "Rose" in valid_functions? ✓ target="GIFT_ROSE"
    ↓
[STEP 5] 5x in queue: ("GIFT_ROSE", "anna_123")
    ↓
Worker thread processes all 5 in sequence
```

---

### Special: Streaking Flag

The `streaking` flag is important because TikTok sends **status updates** for long combo sequences:

```python
# What TikTok sends for a 5-combo:

Event 1: {gift: "Rose", repeat_count: 1, streaking: False}  ✓ Process
Event 2: {gift: "Rose", repeat_count: 2, streaking: False}  ✓ Process
Event 3: {gift: "Rose", repeat_count: 3, streaking: False}  ✓ Process
Event 4: {gift: "Rose", repeat_count: 4, streaking: False}  ✓ Process
Event 5: {gift: "Rose", repeat_count: 5, streaking: True}   ✗ SKIP!
```

**Why ignore the `streaking=True` event?**

If we processed it, we would queue the action 5x = 5x incorrectly!
The `streaking=True` event is just a message from TikTok: "The combo is now complete."

**How do we handle this?**

```python
if hasattr(event, 'streaking') and event.streaking:
    return  # Ignore, do not process!
```

---

### Error Handling for Gift Events

Gift handlers need to be robust because several things can go wrong:

| Problem | What can happen? | How do we protect ourselves? |
|---------|------------------|------------------------------|
| Event has no `gift` property | AttributeError | `getattr()` with fallback |
| Event has no `user` property | AttributeError | `get_safe_username()` with fallback |
| Gift name/ID does not match any action | Gift is ignored | `if not target: return` |
| Username contains invalid characters | Queue error | `sanitize_filename()` cleans it up |
| Queue is full (very rare) | `put_nowait()` exception | Try-except around queue operation |

**Solution:** Wrap everything in try-except:

```python
try:
    # Gift handler code here
except AttributeError as e:
    logger.error(f"Gift event has invalid structure: {e}")
except Exception as e:
    logger.error(f"Error in gift handler: {e}", exc_info=True)
```

---

### Practical Example: A Complete Gift Handler

Here is a real, working gift handler with all safety features:

```python
@client.on(GiftEvent)
def on_gift(event: GiftEvent):
    """
    Handles gift events from TikTok.
    - Handles combos (multiple times in a row)
    - Ignores streaking events (status updates)
    - Queues actions for asynchronous processing
    """
    try:
        # STEP 1: Ignore streaking event?
        if hasattr(event, 'streaking') and event.streaking:
            logger.debug(f"Ignoring streaking event: {event.gift.name}")
            return
        
        # STEP 2: How often should we perform the action?
        if event.gift.combo:
            count = event.repeat_count  # e.g. 5 for a 5-combo
        else:
            count = 1  # Single gift = 1x
        
        # STEP 3: Read gift data safely
        gift_name = event.gift.name      # "Rose", "Diamond", etc.
        gift_id = str(event.gift.id)     # "1", "2", etc.
        username = get_safe_username(event.user)  # "anna_123" (sanitized)
        
        logger.info(
            f"Gift received: {gift_name} (ID: {gift_id}) "
            f"from {username} (x{count})"
        )
        
        # STEP 4: Find the right trigger
        # First search by name, then by ID
        target = None
        if gift_name in TRIGGERS:
            target = gift_name
        elif gift_id in TRIGGERS:
            target = gift_id
        
        if not target:
            logger.warning(f"No trigger defined for gift '{gift_name}'")
            return
        
        # STEP 5: Place action in queue (count times)
        for _ in range(count):
            try:
                MAIN_LOOP.call_soon_threadsafe(
                    trigger_queue.put_nowait,
                    (target, username)
                )
            except Exception as e:
                logger.error(
                    f"Error queuing gift action: {e}",
                    exc_info=True
                )
        
        logger.debug(f"✓ {count}x action '{target}' queued")
        
    except AttributeError as e:
        logger.error(
            f"Gift event is incomplete (missing property): {e}",
            exc_info=True
        )
    except Exception as e:
        logger.error(
            f"Unexpected error in gift handler: {e}",
            exc_info=True
        )
```

**What does this code do?**

1. **Ignore streaking** – Only process real gift events
2. **Determine count** – 1x or multiple times?
3. **Read data** – Gift name, ID, username
4. **Logger info** – Visible feedback for debugging
5. **Find triggers** – By name, then by ID
6. **Queue operation** – Thread-safe with `call_soon_threadsafe`
7. **Error handling** – Everything is protected with try-except

---

### Even Simpler: Minimal Example

If the above handler is too long for you, here is a minimal example that also works:

```python
@client.on(GiftEvent)
def on_gift(event: GiftEvent):
    # Ignore streaking events
    if getattr(event, 'streaking', False):
        return
    
    # How often?
    count = event.repeat_count if event.gift.combo else 1
    
    # Which trigger?
    target = event.gift.name  # or: event.gift.id
    
    # Queue (count times)
    for _ in range(count):
        MAIN_LOOP.call_soon_threadsafe(
            trigger_queue.put_nowait,
            (target, event.user.nickname)
        )
```

This is significantly shorter and does the same thing – but **without** explicit error handling.

---

### Summary & Next Step

**What you know now:**

| Concept | Explanation |
|---------|-------------|
| **Combo gifts** | Same gift multiple times = `repeat_count` increases |
| **Streaking** | TikTok sends status updates = we ignore them |
| **Trigger matching** | Gift name or ID → to action (TRIGGERS dictionary) |
| **Asynchronous queue** | `call_soon_threadsafe` makes it thread-safe |
| **Error handling** | Try-except protects against unexpected structures |

**What happens AFTER the gift handler?**

The queued action is later processed by the worker thread.

→ [Next chapter: Follow events](ch05-06-Follow-Events.md)

---

> [!TIP]
> If you want to write your own gift handler, use the **minimal example** above and then add error handling as needed.
