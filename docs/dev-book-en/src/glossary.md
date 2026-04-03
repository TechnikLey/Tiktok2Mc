# Glossary

A complete reference of all technical terms and concepts. If you come across an unfamiliar term, you will find a quick explanation here.

---

## A

### Action
An operation that the system performs (e.g. "send command to Minecraft"). Actions are triggered by events and configured in `actions.mca`.

**Example:** The gift event "Rose" triggers the action "play_sound".

### Async / Asynchronous Programming
Programming in which multiple tasks run concurrently rather than sequentially. One process does not have to wait for another to finish.

**In this project:** TikTok events arrive (Async 1) while the main loop processes Minecraft commands (Async 2).

### API (Application Programming Interface)
An interface through which two programs communicate with each other.

**In this project:** We use the TikTokLive API (to receive events) and the RCON API (to send commands to Minecraft).

---

## C

### Combo Gift
A gift that can be sent multiple times in a row. The viewer sees an animation showing the total number of gifts.

**Example:** Someone sends the same rose 5 times → the viewer sees "Rose ×5".

**In code:** `event.gift.combo == True` and `event.repeat_count == 5`

### CORS (Cross-Origin Resource Sharing)
A security mechanism in web servers that determines which external websites are allowed to send requests.

**In this project:** Our Flask server uses CORS to give plugin GUIs access to the APIs.

### Command-Line Argument / Flag
A value passed when starting a program.

**Example:** 
```bash
python main.py --gui-hidden --register-only
```

Here, `--gui-hidden` and `--register-only` are flags.

---

## D

### DCS (Direct Control System)
A communication protocol in which data is transmitted directly via HTTP.

**Advantage:** Fast & reliable.  
**Disadvantage:** Requires open HTTP ports.

**Alternative:** ICS (Interface Control System).

### Decorator
A Python feature (`@...`) that "decorates" a function with additional behavior.

**Example:**
```python
@client.on(GiftEvent)
def handle_gift(event):
    pass
```

The `@client.on(...)` decorator registers this function as an event handler.

### Dependency
An external package that your project needs.

**In this project:**
- `TikTokLive` – dependency
- `Flask` – dependency
- All are listed in `requirements.txt`.

---

## E

### Event
An occurrence that happens in the system.

**Examples:**
- Someone sends a gift
- Someone follows
- A player dies in Minecraft
- The server starts

All events have properties (data), e.g. `event.user`, `event.gift.name`.

### Event Handler
A function that reacts to an event.

**Example:**
```python
@client.on(GiftEvent)
def on_gift(event):
    print(f"Gift received: {event.gift.name}")
```

`on_gift` is the event handler for GiftEvents.

---

## F

### Flask
A Python web framework for building web servers.

**Usage in our project:**
- Webhooks (receiving Minecraft events)
- GUIs (pywebview uses Flask for the backend API)

**Not to be confused with:** Django (different framework), FastAPI (newer standard).

### Function
See Handler / Function.

---

## G

### Glossary
This document! A reference of technical terms.

---

## H

### Handler
See Event Handler.

### HTTP / HTTPS
Network protocols for transferring data over the internet / network.

**HTTP** = unencrypted (but faster)  
**HTTPS** = encrypted (but more complex)

**In this project:** We use HTTP locally (not over the internet).

---

## I

### ICS (Interface Control System)
A communication protocol in which data is transmitted via GUI / screen capture.

**Advantage:** Works everywhere (including TikTok Live Studio).  
**Disadvantage:** Slower & more complex.

**Alternative:** DCS (Direct Control System).

### Import
Loading external code into your program.

**Example:**
```python
from core import load_config
```

This loads the `load_config` function from the `core` module.

---

## J

### JSON
A data format for storing and transmitting structured data.

**Format:**
```json
{
    "name": "John",
    "age": 30,
    "gifts": ["Rose", "Diamond"]
}
```

**In this project:** Used for configurations, window states, and data.

---

## L

### Logging / Logs
Recording program operations to a file or as output.

**Purpose:** Debugging & monitoring.

**Example:**
```python
logging.info("Gift received")
logging.error("Connection failed")
```

Logs end up in `logs/debug.log`.

---

## M

### main.py
The main program file of the project. It connects TikTok to the rest of the system.

### Middleware
Software that mediates between two other systems.

**In our project:** `main.py` contains the webhook endpoint and acts as middleware between Minecraft and the plugins. `server.py`, on the other hand, starts the Minecraft server itself.

### Migration
The process of transferring data from an old format to a new one.

**In this project:**
- Config migration: Old `config.yaml` is updated to match the new structure
- See [Config](./config.md) for details.

### Module
A reusable code building block that other files/projects can use.

**In this project:**
- `core/models.py` – data structures module
- `core/paths.py` – path module
- Always located in the `src/core/` folder.

---

## O

### Overlay
A visual element that is overlaid on the stream / screen.

**Example:** A counter on the screen shows "Deaths: 5", "Likes: 200".

**In this project:** Plugins use overlays to display data visually.

---

## P

### Parameter
A value passed to a function.

**Example:**
```python
def create_client(user):  # 'user' is the parameter
    ...

create_client("my_streamer")  # 'my_streamer' is passed
```

### Path
A file path in the file system.

**Windows:** `C:\Users\...\config\config.yaml`  
**Linux:** `/home/.../config/config.yaml`

### Plugin
An independent program that integrates into the Streaming Tool.

**Examples:**
- Timer (countdown timer)
- DeathCounter (counts deaths)
- Your custom plugin

### Port
A virtual "port" through which a server accepts connections.

**Example:** `http://localhost:8080` – the port is `8080`.

**Config:** All ports are configurable in `config.yaml`.

### Pseudo Code
Simplified code that is not syntactically correct but illustrates the logic.

**Example:**
```
1. When gift arrives
2. Find configuration
3. Execute action
```

---

## Q

### Queue
A data structure that stores elements in the order in which they were added (FIFO: First-In-First-Out).

**In our project:**
- `trigger_queue`: Stores the triggers to be processed
- `like_queue`: Stores like updates for the overlay

---

## R

### Race Condition
A bug that occurs when two threads access the same resource at the same time.

**Example:** Thread 1 reads `event.total`, Thread 2 changes it → inconsistency!

**Solution:** Lock (Mutex) – only one thread may access at a time.

### Registry
A central management file or system.

**In this project:** `PLUGIN_REGISTRY` registers all modules & plugins with their settings.

### RCON (Remote Console)
A protocol through which you can send Minecraft commands remotely.

**Example:** Instead of typing directly in the Minecraft console, the tool sends the command `/say "Hey!"` via RCON.

### Reverse Engineering
Reconstructing a system by observing its behavior from the outside.

**In this project:** The TikTokLive API is based on reverse engineering (not officially provided by TikTok).

---

## S

### Streak
A combo that is triggered multiple times in a row.

**Example:** The same rose is sent 5 times in a row → "Streak: 5".

### SQL / Database
A system for structured data storage (not centrally relevant in this project).

---

## T

### Thread / Threading
An independent execution flow within a program.

**Analogy:** A program with 2 threads is like a streamer with 2 microphones – both can speak at the same time.

**Danger:** Race conditions (two threads modifying data in parallel).

### Trigger
A condition that causes an action to execute.

**Example:** 
- `gift_1001` is a trigger (when this gift arrives)
- `follow` is a trigger (when someone follows)
- When a trigger fires → the action is executed

### TikTokLive API
The external library through which we access TikTok live streams.

**Based on:** Reverse engineering (unofficial).

**Usage:** `from TikTokLive import TikTokLiveClient`

---

## U

### Update
A new release / version of the project.

**Process:**
1. New version is uploaded to GitHub  
2. User starts the program
3. Update script downloads the new version
4. Old data is retained (`config/`, `data/` are not overwritten)

**Details:** See [Update](./update.md).

---

## V

### Validator
A module that checks whether data is correct.

**Example:** `validator.py` checks whether `config.yaml` is valid YAML.

### Variable
A named container for data.

**Example:** `gift_name = event.gift.name` – `gift_name` is the variable.

---

## W

### Webhook
A mechanism where one system automatically sends data to another when something happens.

**In this project:**
- Minecraft server sends a webhook to our tool (when a player dies, spawns, etc.)
- Our tool then processes the webhook

**Format:** Typically HTTP POST with JSON data.

---

## X

### (no common terms)

---

## Y

### YAML
A data format for storing structured data (similar to JSON, but more human-readable).

**Format:**
```yaml
timer:
  enable: true
  start_time: 10
  max_time: 60
```

**In this project:** `config.yaml` is written in YAML.

---

## Z

### Centralization
The concept of managing everything in one place.

**In this project:** `PLUGIN_REGISTRY` is the central management system for all modules.

---

## Quick Index by Category

### **Event System**
- Event, Event Handler, Trigger, Action
- Webhook, RCON

### **Technology**
- API, HTTP/HTTPS, Port
- Thread/Threading, Race Condition
- Async, Middleware

### **Python & Code**
- Import, Module, Decorator
- Parameter, Variable, Handler
- Function, Logging

### **Data Formats**
- JSON, YAML, Database

### **Structure & Organization**
- Registry, Migration
- Queue
- Path

### **Control & Communication**
- DCS, ICS, Flask
- CORS

### **Debugging & Development**
- Logging, Validator
- Pseudo Code, Reverse Engineering

---

## "I still don't understand term XYZ!"

That's OK. Here are your options:

1. **Re-read:** Simply read it again
2. **Context:** Search for the term in the documentation – context helps
3. **Read code:** Look at how the term is used in actual code
4. **Ask:** Other developers or an AI for help
