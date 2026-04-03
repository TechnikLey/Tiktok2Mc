## The `main.py` File

`main.py` is the **centerpiece** of the project. It is responsible for staying connected to TikTok and receiving all events.

---

## What Does main.py Do?

When you start the program, `main.py` performs these steps (simplified):

```
1. Load configuration (config.yaml)
     ↓
2. Set up TikTok client
     ↓
3. Register event handlers ("Listen for gifts, follows, likes")
     ↓
4. Connect to TikTok (stay connected)
     ↓
5. Receive events (continuously)
     ↓
6. Process events & queue them
     ↓
7. [While step 6 is running: Main loop processes queue]
```

This is **not linear**. Steps 5, 6, and 7 run **at the same time** (in parallel).

---

## Structure of main.py (High Level)

```python
# 1. IMPORTS
from TikTokLive import TikTokLiveClient
from TikTokLive.events import GiftEvent, FollowEvent, LikeEvent
from core.validator import validate_file, print_diagnostics
from core.paths import get_base_dir

# 2. GLOBAL VARIABLES
MAIN_LOOP = ...          # Reference to the main loop
trigger_queue = Queue()  # Queue for triggers
like_queue = Queue()     # Queue for likes

# 3. CLIENT CREATION FUNCTIONS
def create_client(user):
    client = TikTokLiveClient(unique_id=user)
    
    @client.on(GiftEvent)
    def on_gift(event):
        # Respond to gift
        pass
    
    # Similar: on_follow, on_like, etc.
    return client

# 4. MAIN FUNCTION
def main():
    # Load config
    cfg = load_config(...)
    
    # Start client
    client = create_client(cfg["tiktok_user"])
    
    # Start other services (server, GUI, plugins)
    # ...
    
    # Main loop (processes queue)
    while True:
        event = trigger_queue.get()  # Get next event
        process_trigger(event)       # Process
```

---

## The Role of Imports

At the beginning of `main.py` you see:

```python
from TikTokLive import TikTokLiveClient
from TikTokLive.events import GiftEvent, FollowEvent, ConnectEvent, LikeEvent
```

This means:

- **TikTokLiveClient**: An object that connects to TikTok
- **GiftEvent**: Triggers when a gift is received
- **FollowEvent**: Fires when someone follows
- **LikeEvent**: Triggered when likes arrive

These will be used later to register event handlers.

Further imports:

```python
from core.validator import validate_file, print_diagnostics
from core.paths import get_base_dir
```

These are **core modules** (from the project itself), not external libraries.

---

## Step 1: Load Configuration

```python
CONFIG_FILE = get_root_dir() / "config" / "config.yaml"

try:
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
except Exception as e:
    print(f"ERROR: Config could not be loaded: {e}")
    sys.exit(1)  # Exit program
```

This reads the `config.yaml`:

```yaml
tiktok_user: "a_tiktoker"
Timer:
  Enable: true
  StartTime: 10
```

If that fails, the program aborts (because it doesn't work without config).

---

## Step 2 & 3: Create Client & Register Handlers

```python
def create_client(user):
    """Create a TikTok Live client for the specified user"""
    client = TikTokLiveClient(unique_id=user)
    
    # Now let's register event handlers
    # Handler = "Functions that are executed when an event occurs"
    
    @client.on(GiftEvent)
    def on_gift(event: GiftEvent):
        # This function is called EVERY TIME a gift arrives
        pass  # Logic comes later
    
    @client.on(FollowEvent)
    def on_follow(event: FollowEvent):
        # This function is called when someone follows
        pass
    
    @client.on(LikeEvent)
    def on_like(event: LikeEvent):
        # This function is called when likes arrive
        pass
    
    return client  # Return the configured client
```

The `@client.on(...)` is a **decorator** – a Python construct that says: "Call this function when this event occurs."

---

## Step 4: Connect to TikTok

```python
client = create_client(cfg["tiktok_user"])

# Start connection (asynchronous)
asyncio.run(client.connect())
```

This connects to the TikTok stream and **stays connected**. When an event comes, the client automatically calls the corresponding handler.

---

## Why Is main.py Complex?

If you open the real `main.py`, you'll see a lot more code than explained here:

```python
# Real main.py also has:
- Error handling (what if an error occurs?)
- Combo gifts (repeated gifts)
- Race conditions (multi-threading)
- Streams (video events)
- and much more...
```

This makes the code complicated. But **the core idea remains the same**:

1. Create client
2. Register handlers
3. Connect
4. Process events

---

## What's in the Event Handlers?

The actual **magic** happens in the event handlers:

```python
@client.on(GiftEvent)
def on_gift(event: GiftEvent):
    # 1. Read gift details
    gift_name = event.gift.name
    user = event.user.nickname
    
    # 2. Check if this gift is configured
    if gift_name in valid_functions:
        # 3. Queue trigger
        MAIN_LOOP.call_soon_threadsafe(
            trigger_queue.put_nowait,
            (gift_name, user)
        )
```

But this will be discussed in detail later.

---

## The Role of the Main Program

`main.py` is **not** the only file that runs. There are also:

- **server.py**: Starts the Minecraft server (Java subprocess, RCON configuration, server.properties)
- **registry.py**: Loads and starts all plugins
- **gui.py**: Shows an admin interface

---

## Summary

`main.py` does:

✓ Load configuration  
✓ Create TikTok client  
✓ Register event handlers  
✓ Connect with TikTok  
✓ Receive and process events  
✓ Place in queue  

Everything runs **in parallel – not one after the other.**

---

## Next Step

Now you understand the **structure**. The next step is to understand the **imports** more precisely.

**→ [Imports](./ch05-02-Imports.md)**

There you will see what is done with the imported modules.
