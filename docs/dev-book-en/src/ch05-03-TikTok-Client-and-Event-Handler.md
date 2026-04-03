## TikTok Client & Event Handler

This is the **centerpiece** of event processing. Here we create the connection to TikTok and register functions that react to events.

---

## How It Works

```
1. Create TikTok client
   ↓
2. Register handlers for specific events
   ↓
3. Handler is called AUTOMATICALLY when event arrives
```

This is not "polling" (constantly asking "is something going on?"), but rather **event-driven** (the system tells you when something happens).

Visualized:

```
TikTok Live Stream is running...
    ↓
↓ [Event arrives: someone sends a gift]
    ↓
TikTokLive API automatically calls: on_gift(event)
    ↓
on_gift() is executed
    ↓
We process the gift
```

---

## Step 1: Create Client

```python
from TikTokLive import TikTokLiveClient
from TikTokLive.events import GiftEvent, FollowEvent, LikeEvent

def create_client(user):
    """Create a TikTok Live client"""
    client = TikTokLiveClient(unique_id=user)
    return client
```

**What happens:**
- `TikTokLiveClient(unique_id=user)` connects to a specific TikTok account
- The client **listens** for all events from this stream
- No handlers registered yet – that's coming next

---

## Step 2: Register Handlers

A **handler** is simply a function that responds to an event. We use the **decorator approach**:

```python
@client.on(GiftEvent)
def on_gift(event: GiftEvent):
    print(f"Gift received: {event.gift.name}")
```

The `@client.on(...)` decorator says: "Call this function when a GiftEvent arrives."

**Similar for other events:**

```python
@client.on(FollowEvent)
def on_follow(event: FollowEvent):
    print(f"New follow: {event.user.nickname}")

@client.on(LikeEvent)
def on_like(event: LikeEvent):
    print(f"Total Likes: {event.total}")
```

---

## Step 3: Fill Handlers with Logic

This is where things get interesting. The handler must:

1. **Read event data** – What's in the event?
2. **Validate** – Is it a valid event?
3. **Find triggers** – Which action should be triggered?
4. **Place in queue** – Don't execute immediately, but wait in line!

**Reason for queue:** Events come very quickly. If we process them immediately, the next event processing could block or the RCON connection breaks.

**Simplified example:**

```python
@client.on(GiftEvent)
def on_gift(event: GiftEvent):
    # 1. Read event data
    gift_name = event.gift.name           # e.g. "Rose"
    gift_id = event.gift.id               # e.g. 1001
    repeat_count = event.repeat_count     # e.g. 3 (combo)
    user = event.user.nickname            # e.g. "Streamer123"
    
    # 2. Validate (is everything OK?)
    if not gift_name or not user:
        logger.warning("Invalid gift data")
        return
    
    # 3. Find triggers (is there an action for this gift?)
    trigger = None
    if gift_name in VALID_ACTIONS:
        trigger = gift_name
    elif str(gift_id) in VALID_ACTIONS:
        trigger = str(gift_id)
    
    if not trigger:
        logger.debug(f"No action configured for gift: {gift_name}")
        return
    
    # 4. Place in queue (don't run immediately!)
    for _ in range(repeat_count):
        MAIN_LOOP.call_soon_threadsafe(
            trigger_queue.put_nowait,
            (trigger, user)
        )
        logger.info(f"Gift queued: {gift_name} from {user}")
```

---

## Step 4: Error Handling

Events can fail – we have to catch it:

```python
@client.on(GiftEvent)
def on_gift(event: GiftEvent):
    try:
        # Your code here
        gift_name = event.gift.name
        # ... rest of the logic
        
    except AttributeError as e:
        logger.error(f"Gift data is incomplete: {e}")
    except Exception as e:
        logger.error(f"Unexpected error in on_gift: {e}", exc_info=True)
        # Important: exc_info=True shows the complete error stack
```

**Why important:**
- Event handlers must not crash the entire program
- Other events should continue to be processed
- Errors should be logged (for debugging)

---

## The Real Implementation (Production Code)

The real code is more complex because it has to deal with edge cases:

```python
@client.on(GiftEvent)
def on_gift(event: GiftEvent):
    try:
        # Combo gifts can be sent multiple times
        if event.gift.combo:
            # Check for "streak" (repeated combo)
            if getattr(event, 'streaking', False):
                try:
                    if event.streaking:
                        return  # Ignore streak intermediate events
                except AttributeError:
                    pass
            
            repeat_count = event.repeat_count
        else:
            repeat_count = 1  # Non-combo = once
        
        # Make gift data safe
        gift_name = sanitize_filename(event.gift.name)
        gift_id = str(event.gift.id)
        
        # Execute extra action (e.g. sound)
        execute_gift_action(gift_id)
        
        # Find triggers
        target = None
        if gift_name in valid_functions:
            target = gift_name
        elif gift_id in valid_functions:
            target = gift_id
        
        if not target:
            return
        
        username = get_safe_username(event.user)
        
        # Place in queue multiple times (for combos)
        for _ in range(repeat_count):
            MAIN_LOOP.call_soon_threadsafe(
                trigger_queue.put_nowait,
                (target, username)
            )
    
    except Exception:
        logger.error("ERROR in on_gift handler:", exc_info=True)
```

---

## Understanding the Complexity

The real code is more complex because:

| Complexity | Reason |
|------------|--------|
| `if event.gift.combo` | Some gifts can be repeated multiple times |
| `getattr(event, 'streaking', False)` | Attributes may not exist – check defensively |
| `sanitize_filename()` | Usernames might contain special characters |
| `call_soon_threadsafe()` | Thread-safe queue operation |
| Try-except | Events must not crash the entire system |

---

## Summary

A TikTok client handler:

1. ✓ Listens for events
2. ✓ Receives event data
3. ✓ Validates the data
4. ✓ Finds suitable action
5. ✓ Places in queue (does not execute immediately!)
6. ✓ Catches errors (does not crash)

---

## Next Step

Now you understand how handlers work. The next step is to understand what is in the event itself.

**→ [Understanding the Event System](./ch05-04-Understanding-the-Event-System.md)**

There we look at what data each event has and how we use it.
