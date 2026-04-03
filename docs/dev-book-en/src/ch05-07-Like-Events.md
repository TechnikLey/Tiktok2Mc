## Like Events

### What's Special About Likes: Continuous Counting

Like events are **completely different** from gifts and follows:

| Feature | Gifts | Follows | Likes |
|---------|-------|---------|-------|
| **Event type** | Discrete events ("gift sent") | Discrete events ("followed") | Continuous counting |
| **Frequency** | Rare (user sends gift) | Rare (user follows) | **VERY FREQUENT** |
| **Usernames** | Yes, visible | Yes, visible | Rarely visible |
| **Trigger logic** | "When gift" | "When follow" | "When counter reaches e.g. 100 mark" |
| **Threading problem** | No, simple | No, simple | **YES, race conditions!** |

**The core problem:** Like events arrive so quickly that **multiple threads** can access the same data simultaneously. This leads to **race conditions** if we're not careful.

---

### The Race Condition Problem Explained

Imagine two like events arrive **at the same time**:

```
Thread 1:  Reads like counter:  100
Thread 2:  Reads like counter:  100
           ↓
Thread 1:  Calculates: 100 > last_blocks? YES → Trigger!
Thread 2:  Calculates: 100 > last_blocks? YES → Trigger!
           ↓
Thread 1:  Writes: last_blocks = 100
Thread 2:  Writes: last_blocks = 100
           ↓
RESULT: Trigger fired 2x instead of 1x! 
```

**Solution: Lock (Mutex)**

A lock ensures that only **one thread at a time** executes the critical code:

```
Thread 1:  Waiting for lock... ⏳
Thread 2:  GETS LOCK ✓
           Reads, calculates, writes
           RELEASES LOCK
           ↓
Thread 1:  GETS LOCK ✓
           Reads, calculates, writes (with updated data!)
           RELEASES LOCK
           ↓
RESULT: Trigger fired 1x (+ 1x, correctly sequential) ✓
```

---

### Like Counting Visualized: The Difference from Other Events

```
GIFTS/FOLLOWS (Discrete):
  
  00:00 - Event "Gift Rose"        → Trigger: "GIFT_ROSE"
  00:05 - Event "Follow"           → Trigger: "FOLLOW"
  00:10 - (nothing)
  00:15 - Event "Gift Diamond"     → Trigger: "GIFT_DIAMOND"

LIKES (Continuous):

  00:00 - LikeEvent: total=1000
  00:01 - LikeEvent: total=1000
  00:02 - LikeEvent: total=1000
  00:03 - LikeEvent: total=1005  ← +5 likes!
  00:04 - LikeEvent: total=1012  ← +7 likes!
  
  If we want to trigger every 10-mark:
  
  1000-1009: no triggers
  1010+    : 1 trigger
  1020+    : 1 trigger
  1030+    : 1 trigger
  etc.

  With our code:
  
  current_blocks = 1012 // 10 = 101
  last_blocks = 100
  diff = 101 - 100 = 1
  → Trigger fired 1x ✓
```

---

### LikeEvent Structure

A `LikeEvent` contains this information:

```python
event.total              # Total like count so far: 1005, 1010, 1025 etc.
event.likeCount          # Likes in this session/streak: 5, 7, 15 etc.

event.user.nickname      # Username (sometimes not available)
event.timestamp          # Timestamp of the event
```

---

### Like Event Processing: The 6-Step Flow

When like events arrive, the following happens:

```
1. FIRST EVENT?
   Is start_likes still None? YES → Initialize, return
   
2. CALCULATE DELTA
   Likes since start: current_total - start_likes
   e.g.: 1025 - 1000 = 25
   
3. ACQUIRE LOCK
   Wait until no other thread is active
   
4. CHECK RULES
   For each like rule:
     - Read interval ("every": 100)
     - Calculate how many intervals have been reached
     - Check if new intervals since last check
     
5. QUEUE TRIGGERS
   For each new interval:
     - Place action in queue
     
6. RELEASE LOCK
   Next thread can now proceed
```

---

### Interval Calculation Explained

This is the core logic for like counting:

```python
every = 100  # Trigger every 100 likes

# Scenario 1: 1010 likes total
current_blocks = 1010 // 100  # = 10 (tenth 100-mark)
last_blocks = 9               # (we were at 900)
diff = 10 - 9 = 1             # → 1 trigger

# Scenario 2: 1025 likes total
current_blocks = 1025 // 100  # = 10 (still the tenth mark!)
last_blocks = 10              # (we already know about mark 10)
diff = 10 - 10 = 0            # → No new trigger

# Scenario 3: 1200 likes total
current_blocks = 1200 // 100  # = 12 (twelfth mark)
last_blocks = 10              # (old mark)
diff = 12 - 10 = 2            # → 2 triggers in succession!
```

**The `//` is important!** This is integer division (whole number). It is the key to the block calculation.

---

### Error Handling for Like Events

Like handlers need special error handling because of the lock:

```python
like_lock = threading.Lock()

try:
    with like_lock:  # ← Python: Automatic lock/unlock
        # Critical code here
except Exception as e:
    logger.error(f"Error in like handler: {e}", exc_info=True)
    # Lock is AUTOMATICALLY released, even if an error occurs!
```

**Why use `with like_lock`?**

Because Python automatically **always** releases the lock, even if an error occurs. This is important – otherwise the lock would "hang" and all other threads would wait forever!

---

### Practical Example: A Complete Like Handler

Here is a real, working like handler:

```python
import threading

# Initialize globally
like_lock = threading.Lock()
start_likes = None
last_overlay_sent = 0
last_overlay_time = 0

LIKE_TRIGGERS = [
    {"id": "goal_100", "every": 100, "last_blocks": 0, "function": "LIKE_GOAL_100"},
    {"id": "goal_500", "every": 500, "last_blocks": 0, "function": "LIKE_GOAL_500"},
]

def initialize_likes(total):
    """Set starting value on first event"""
    global start_likes
    start_likes = total
    logger.info(f"Like tracking initialized with: {total} likes")

@client.on(LikeEvent)
def on_like(event: LikeEvent):
    """
    Processes like events from TikTok.
    - Continuous counting instead of individual events
    - Thread-safe with locks
    - Triggers when like milestones are reached (100, 500, 1000, etc.)
    """
    global start_likes, last_overlay_sent, last_overlay_time
    
    try:
        # STEP 1: First initialization?
        if start_likes is None:
            initialize_likes(event.total)
            return
        
        # STEP 2: Calculate likes since start
        total_since_start = event.total - start_likes
        
        logger.debug(f"Like event: {event.total} total, "
                     f"{total_since_start} since start")
        
        # STEP 3: Acquire lock (thread safety!)
        with like_lock:
            
            # STEP 4: Check each like rule
            for rule in LIKE_TRIGGERS:
                every = rule["every"]
                
                # Skip invalid rules
                if every <= 0:
                    continue
                
                # STEP 5: Calculate current and last block number
                current_blocks = total_since_start // every
                last_blocks = rule["last_blocks"]
                
                # New blocks reached?
                if current_blocks > last_blocks:
                    diff = current_blocks - last_blocks
                    rule["last_blocks"] = current_blocks
                    
                    logger.info(
                        f"Like trigger '{rule['id']}': "
                        f"{current_blocks} milestones reached (+{diff})"
                    )
                    
                    # STEP 6: For each new block: queue action
                    for _ in range(diff):
                        try:
                            MAIN_LOOP.call_soon_threadsafe(
                                trigger_queue.put_nowait,
                                (rule["function"], {})
                            )
                        except Exception as e:
                            logger.error(
                                f"Error queuing like action: {e}",
                                exc_info=True
                            )
        
        # (Lock is automatically released here)
        
    except Exception as e:
        logger.error(
            f"Unexpected error in like handler: {e}",
            exc_info=True
        )
```

**What does this code do?**

1. **Initialize** – Set starting value on first event
2. **Calculate delta** – How many likes are new?
3. **Acquire lock** – Activate thread safety
4. **Check rules** – For each like milestone (100, 500, etc.)
5. **Calculate blocks** – With integer division `//`
6. **Queue** – Queue an action for each new milestone

---

### Even Simpler: Minimal Example

The absolute minimum (also works, but requires manual lock management):

```python
like_lock = threading.Lock()
start_likes = None

@client.on(LikeEvent)
def on_like(event: LikeEvent):
    global start_likes
    
    if start_likes is None:
        start_likes = event.total
        return
    
    delta = event.total - start_likes
    
    with like_lock:
        # When delta reaches 100: trigger
        if delta >= 100 and delta - 100 < 1:  # First 100-mark
            MAIN_LOOP.call_soon_threadsafe(
                trigger_queue.put_nowait,
                ("LIKE_GOAL_100", {})
            )
```

This is much shorter, but also less flexible. The complete handler above is better!

---

### Difference Between Gifts/Follows and Likes

To understand why like handlers are more complex:

**Gifts/Follows:**
```python
# Event arrives → Process immediately → Done
@client.on(GiftEvent)
def on_gift(event):
    queue.put(...)
```

**Likes:**
```python
# Events arrive VERY OFTEN → Track how many → Trigger per interval
@client.on(LikeEvent)
def on_like(event):
    # Count: How many likes since start?
    delta = event.total - start_likes
    
    # Calculate: How many 100-marks?
    blocks = delta // 100
    
    # Compare: New marks since last time?
    if blocks > last_blocks:
        # THEN: Trigger!
        queue.put(...)
```

The difference: **Aggregation instead of direct forwarding!**

---

### Edge Cases for Like Events

What can go wrong?

| Scenario | Problem | Solution |
|----------|---------|----------|
| Like event before initialization | start_likes is None | `if start_likes is None: initialize()` |
| Two events simultaneously | Race condition | `with like_lock` protects |
| Interval is 0 | Division by zero | `if every <= 0: continue` |
| Very fast like flood | Many events/sec | Blocks are correctly aggregated |
| Lock hangs | Thread blocked forever | `with like_lock` auto-releases |

**Conclusion:** Like handlers require the most error handling, especially because of the lock.

---

### Summary & Next Step

**What you know now:**

| Concept | Explanation |
|---------|-------------|
| **Likes ≠ Gifts** | Continuous counting instead of individual events |
| **Race conditions** | Multiple threads access simultaneously → lock required |
| **Block calculation** | `blocks = total_likes // interval` |
| **Initialization** | Set starting value on first event |
| **Lock pattern** | `with threading.Lock()` for thread safety |
| **Error handling** | Lock is released even on errors (`with` does this) |

**What happens AFTER the like handler?**

The queued like actions are later processed by the worker thread (e.g. "Congratulations on 100 likes!").

→ [Next chapter: Threading & Queues](ch05-08-Threading-and-Queues.md)

---

> [!NOTE]
> Like handlers show you the real complexity of multi-threading. It's not easy, but super important for performant systems!
