# Python in This Project

Python is the central language of this project. In this chapter you will learn how the project is organized and which parts work together.

---

## Why Python?

Python was chosen for this project because it:

- Is **quick to develop** with (little boilerplate code)
- Has a **good ecosystem** for web (Flask), async (asyncio), and APIs (TikTokLive)
- Remains **readable and maintainable**, even when it becomes complex
- Works **cross-platform** (Windows, macOS, Linux)

---

## The Main Components

### 1. **main.py** – The Heart

```python
# Simplified scheme
def main():
    1. Load config
    2. Set up TikTok client
    3. Register event handlers
    4. Connect client (parallel)
    5. Start startup services (server, GUI, plugins)
    6. Process event queue (main loop)
```

This file connects TikTok to the rest of the system.

### 2. **core/** – Reusable Modules

**What's inside:**

| Module | Purpose |
|--------|---------|
| `models.py` | Data structures (AppConfig, PluginInfo, etc.) |
| `cli.py` | Command-line argument parsing |
| `paths.py` | Path functions (ROOT_DIR, BASE_DIR, etc.) |
| `utils.py` | Helper functions (sanitize strings, etc.) |
| `validator.py` | Validation logic |

You can import these modules anywhere in the project:

```python
from core import load_config, register_plugin, get_root_dir
```

### 3. **server.py** – Minecraft Server Starter

Starts the Minecraft server as a subprocess:

```
config.yaml
    ↓ (Xms, Xmx, Port, RCON)
server.py
    ↓ java -jar server.jar
Minecraft server is running
```

> [!NOTE]
> The webhook endpoint (`/webhook`) is located in **main.py**, not in server.py.

### 4. **registry.py** – Plugin Management

Loads and manages all plugins:

```python
# Simplified
PLUGIN_REGISTRY = [
    {"name": "App", "path": ..., "enable": True, ...},
    {"name": "Timer", "path": ..., "enable": True, ...},
    # More plugins...
]
```

### 5. **plugins/** – Freely Expandable

Here you write your own plugins:

```
src/plugins/
├── timer/
│   ├── main.py          # Timer logic
│   ├── README.md
│   └── version.txt
│
├── my_custom_plugin/    # Your plugin!
│   ├── main.py
│   ├── README.md
│   └── version.txt
```

---

## The Data Flow (Simplified)

```
TikTok Live Stream
    ↓
TikTokLive API (WebSocket)
    ↓
main.py (receives events)
    ↓
Event handlers registered (e.g. on_gift, on_follow)
    ↓
Find trigger + place in queue
    ↓
Main loop processes queue
    ↓
RCON → Minecraft server
    ↓
Minecraft server runs command
```

**Important:** This is NOT synchronous. Events wait in a queue until they can be processed.

---

## Understanding Imports

When you open Python files in the project, you will see imports like:

```python
from TikTokLive import TikTokLiveClient, TikTokLiveConnection
from TikTokLive.events import GiftEvent, FollowEvent, LikeEvent
```

These are **external libraries** (not built into Python):

| Library | Purpose |
|---------|---------|
| `TikTokLive` | Connection to TikTok Live |
| `Flask` | Web framework for webhooks |
| `pywebview` | Desktop GUI windows |
| `pyyaml` | Reading config files |
| `asyncio` | Asynchronous programming |

All are listed in `requirements.txt`.

---

## Threading & Asynchrony (Brief Overview)

The project uses **threading** in several places:

```
TikTok event received (Thread 1)
    ↓
Fill queue
    ↓
Main loop processes (Thread 2)
    ↓
Send Minecraft command
```

Why? Because TikTok events can't wait. If the main loop is currently serving Minecraft, new events must still be able to arrive.

Threading can be complicated, so we'll cover that in more detail later in [Threading and Queues](./ch05-08-Threading-and-Queues.md).

---

## Which Files Do You Need to Understand?

We'll focus on these files:

1. **main.py** – How data comes in
2. **server.py** – How to start the Minecraft server
3. **registry.py** – How plugins are loaded
4. **core/** – Helper functions

For plugin development:
- **src/plugins/timer/main.py** – Good example
- **config.yaml** – Plugin configuration

**Not relevant for initial understanding:**
- Build scripts (build.ps1, upload.ps1)
- Migration code for config
- Template files

---

## Next Step

Now you understand the rough structure. The next part delves deeper.

**→ [The main.py file](./ch05-01-The-main.py-File.md)**

There we see how the main file is structured and what tasks it performs.
