## Understanding the Event System

Before we analyze specific event types (gifts, follows, likes), we need to understand how events are **structured** and how they **flow**.

---

## Event Structure

An event is not just "something happened" – it contains **data** about what happened.

### GiftEvent Example

```python
# A real GiftEvent has this structure:
{
    "user": {
        "id": "123456789",
        "nickname": "Streamer123",
        "signature": "I love Minecraft",
        # ... more user data
    },
    "gift": {
        "id": 1001,
        "name": "Rose",
        "repeat_count": 3,     # How many times was this gift sent?
        "combo": True,         # Can this gift be combined?
        "description": "A beautiful rose"
    },
    "total_count": 5,          # Total gifts from this user
}
```

You access it with:

```python
def on_gift(event: GiftEvent):
    event.user.nickname              # "Streamer123"
    event.gift.name                  # "Rose"
    event.gift.repeat_count          # 3
    event.gift.combo                 # True/False
    event.total_count                # 5
```

---

## Event Objects vs. Dictionaries

The events are not simple **dictionaries** (like `{"name": "Rose"}`), but **objects**:

```python
# Object (what we use)
event.gift.name      # ✓ Works, IDE gives autocomplete

# Dictionary (wouldn't work)
event["gift"]["name"] # ✗ More complicated, no IDE help
```

**Why objects are better:**

- IDE can provide autocomplete (e.g. `event.gift.<suggestion>`)
- Type-safety (Python knows that `event.gift.name` is a string)
- Fewer errors (wrong keys → immediate error instead of silent fail)

---

## Event Categories

Events are divided into **multiple categories**:

| Category | Examples | Purpose |
|----------|----------|---------|
| **User events** | Follow, Gift, Like | Action of a viewer |
| **System events** | Connect, Disconnect | System status |
| **Stream events** | StreamStart, StreamEnd | Stream lifecycle |

**For this documentation we will focus on:**

- ✓ GiftEvent (viewer sends a gift)
- ✓ FollowEvent (viewer follows)
- ✓ LikeEvent (viewer likes)

---

## Event Handler Workflow

When an event arrives, the following happens:

```
1. TikTok Live Stream (something happened)
   ↓
2. TikTokLive API receives event (via WebSocket)
   ↓
3. Client looks for a matching handler (@client.on(...))
   ↓
4. Handler function is called with event data
   ↓
5. Handler processes event
   ↓
6. Next event can be received
```

**Timing:** This all happens in **milliseconds!**

---

## Validating Event Data

Not all event data is guaranteed to be available. We have to program **defensively**:

```python
@client.on(GiftEvent)
def on_gift(event: GiftEvent):
    # ✓ Safe: with fallback
    gift_name = getattr(event.gift, "name", "Unknown")
    
    # ✓ Safe: try-except
    try:
        user_id = event.user.id
    except AttributeError:
        user_id = None
    
    # ✗ Unsafe: could be None
    # repeat_count = event.repeat_count  # What if attribute is missing?
```

**Rule:** Always assume data **can be missing or None**.

---

## Event Modifications & Flags

Some events have additional **flags** or **modifiers**:

### Combo Flag

```python
if event.gift.combo:    # Can this gift be combined?
    # Yes: The viewer can send the same gift multiple times
    # → event.repeat_count says how often
    count = event.repeat_count  # e.g. 5
else:
    # No: only once
    count = 1
```

### Streaking Flag (Advanced)

```python
# Combo gifts can "streak" for several seconds
if getattr(event, "streaking", False):
    # This is an intermediate event (not the last)
    # We can skip if we only want final events
    return
```

---

## Errors in Events (Exception Handling)

Events can be problematic. We have to intercept:

```python
@client.on(GiftEvent)
def on_gift(event: GiftEvent):
    try:
        # Read event data
        gift_name = event.gift.name
        user = event.user.nickname
        
        # Execute logic
        # ...
    
    except AttributeError:
        # Data is missing
        logger.error(f"Gift event missing data: {event}")
        return
    
    except Exception as e:
        # Unexpected error
        logger.error(f"Error processing gift: {e}", exc_info=True)
        return
```

**Important:** A faulty event must **not** crash the whole program. Other events must continue.

---

## Saving & Processing Event Data

Sometimes we want to process event data **later** (e.g. in the queue):

```python
@client.on(GiftEvent)
def on_gift(event: GiftEvent):
    # Do not process immediately – save!
    event_data = {
        "type": "gift",
        "gift_name": event.gift.name,
        "user": event.user.nickname,
        "count": event.repeat_count,
        "timestamp": event.created_at
    }
    
    # Place in queue (will be processed later)
    trigger_queue.put_nowait(event_data)
```

**Why?** Because different threads work at the same time:

```
Thread 1: Receive TikTok events (quickly!)
Thread 2: Process events (slower!)

If Thread 2 is slow, events will pile up in the queue.
That's OK – that's the point of the queue.
```

---

## Summary: Event System

✓ Events are **objects** with structured data  
✓ Different event types (gift, follow, like, etc.)  
✓ Handlers are called **automatically**  
✓ Data must be **validated**  
✓ Errors must be **caught**  
✓ Events are **not processed immediately**, but buffered (queue)  

---

## Next Step

Now you understand the **system**. The next step is to look at specific event types.

**→ [Gift Events](./ch05-05-Gift-Events.md)**

There we see how gift events work specifically (with combos, repeats, etc.).
