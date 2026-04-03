## Threading & Queues: Asynchronous Processing

### Why Can't We Execute Events Directly?

Imagine if an event handler would execute things **directly**:

```python
# WRONG – execute directly:
@client.on(GiftEvent)
def on_gift(event):
    execute_minecraft_command(...)  # ← Blocks!
    wait_for_response(...)         # ← Takes a long time!
    update_overlay(...)            # ← Even longer!
    # Meanwhile: New events are piling up
```

**The problem:** While we wait for the Minecraft response, no **new TikTok events** can be processed. The TikTok connection "hangs" and we lose events!

**The solution:** Place events in a **queue** and process them **asynchronously**!

```python
# ✓ CORRECT – place in queue:
@client.on(GiftEvent)
def on_gift(event):
    trigger_queue.put_nowait((target, username))  # ← Very fast!
    # Done! Event handler returns immediately
    
# Another thread processes the queue:
while True:
    target, username = trigger_queue.get()   # ← Wait for next action
    execute_minecraft_command(...)            # ← No problem if it takes time
```

---

### The Queue Architecture Visualized

```
TIKTOK CONNECTION
  (very fast, must not block)
        ↓
Event handler
  (also fast!)
        ↓
  Trigger queue
  (buffer)
   [GIFT_ROSE]
   [FOLLOW]
   [LIKE_GOAL_100]
   [GIFT_DIAMOND]
        ↓
Worker thread
  (can also be slow)
        ↓
  Minecraft commands
  (can take a long time)
```

**The advantage:** The TikTok connection is **never** blocked, no matter how overloaded the worker thread is!

---

### Queue Operations: put, get, put_nowait

```python
import queue
from threading import Thread

trigger_queue = queue.Queue(maxsize=1000)

# Operation 1: PUT (with waiting)
trigger_queue.put((target, username))  
# If queue is full: Wait until space becomes free

# Operation 2: PUT_NOWAIT (without waiting)
trigger_queue.put_nowait((target, username))
# If queue is full: Exception (QueueFull)
# → That's fine! We catch it if something goes wrong

# Operation 3: GET (with waiting)
item = trigger_queue.get()
# If queue is empty: Wait until item arrives
# → BLOCKS the worker thread until something needs to be done

# Operation 4: GET_NOWAIT (without waiting)
try:
    item = trigger_queue.get_nowait()
except queue.Empty:
    # Queue was empty, do something else
```

---

### call_soon_threadsafe: Thread-Safe Calls

In our streaming tool we use `call_soon_threadsafe` instead of normal `put`:

```python
# Normal put() – unsafe if MainLoop is active:
trigger_queue.put_nowait((target, username))  # Could cause a race condition

# Better: call_soon_threadsafe
MAIN_LOOP.call_soon_threadsafe(
    trigger_queue.put_nowait,
    (target, username)
)  # ✓ Thread-safe!
```

**Why?** `call_soon_threadsafe` ensures that the operation is executed in the **MainLoop thread**, not in the event handler thread. This avoids race conditions!

---

### Race Conditions and Locks (Recap)

A race condition occurs when **two threads access the same data at the same time**:

```python
# Race condition:
counter = 0

Thread 1: counter = counter + 1  # Reads 0, writes 1
          ↓ (interrupt!)
Thread 2: counter = counter + 1  # Reads 0, writes 1
         
RESULT: counter = 1 (but should be 2!)

# ✓ With lock:
counter = 0
lock = threading.Lock()

Thread 1: with lock:              # Acquires lock
              counter = counter + 1  # Reads 0, writes 1
          # Lock released
          ↓
Thread 2: with lock:              # Waits for lock
              counter = counter + 1  # Reads 1, writes 2
          # Lock released
           
RESULT: counter = 2 ✓
```

**Pattern:** Always use `with threading.Lock()` for critical data!

---

### Practical Example: Worker Thread Implementation

The worker thread reads events from the queue and processes them:

```python
import threading
import queue

trigger_queue = queue.Queue()

def worker_thread():
    """This thread processes triggers from the queue"""
    while True:
        try:
            # Wait for next action
            target, username = trigger_queue.get(timeout=1)
            
            # Process action
            logger.info(f"Processing: {target} for {username}")
            
            try:
                execute_trigger(target, username)
            except Exception as e:
                logger.error(f"Error executing trigger {target}: {e}")
            
            # Mark as "done"
            trigger_queue.task_done()
            
        except queue.Empty:
            # Timeout: Nothing in queue, continue
            continue
        except Exception as e:
            logger.error(f"Worker thread error: {e}")

# Start worker thread (as daemon, runs in background)
worker = threading.Thread(target=worker_thread, daemon=True)
worker.start()
```

---

### Overlay Updates: A Practical Use Case

Overlay updates for like counters also use the queue:

```python
# Separate queue for overlay updates
like_queue = queue.Queue()

@client.on(LikeEvent)
def on_like(event):
    global start_likes, last_overlay_sent, last_overlay_time
    
    if start_likes is None:
        start_likes = event.total
        return
    
    # Calculate new likes
    delta = event.total - start_likes
    
    # Send update to overlay (but not too often!)
    now = time.time()
    if delta > 0 and (now - last_overlay_time) >= 0.5:  # Max 2x per second
        try:
            MAIN_LOOP.call_soon_threadsafe(
                like_queue.put_nowait,
                delta  # Only send the difference
            )
            last_overlay_sent = delta
            last_overlay_time = now
        except queue.Full:
            logger.warning("Like queue is full, update skipped")
```

**This is important:** Don't send every overlay update! With `OVERLAY_INTERVAL` (e.g. 0.5 seconds) we limit the updates. This saves bandwidth!

---

### Timing & Throttling: Don't Let Events Come Too Quickly

Sometimes events arrive SO quickly that we have to **throttle** them:

```python
import time

last_event_time = 0
THROTTLE_INTERVAL = 0.1  # At least 100ms between events

@client.on(LikeEvent)
def on_like(event):
    global last_event_time
    
    # Ignore events that are too close together
    now = time.time()
    if now - last_event_time < THROTTLE_INTERVAL:
        return  # Too fast! Skip.
    
    last_event_time = now
    
    # ... rest of the event handler ...
```

**Why?** If like events arrive every 50ms, we can't process them all. With throttling we deliberately slow down processing.

---

### Final Note

**The most important thing to understand:**

Events are **not** directly = action.

Instead:

```
TikTok event → handler → queue → worker thread → action
               (fast)   (buffer)  (can be slow)
```

This makes the system:
- ✓ Stable (events are not lost)
- ✓ Scalable (many events at the same time)
- ✓ Maintainable (action logic is separated)
