# Basic Concepts & Terms

Before we get into the architecture and code, we need to understand the **key ideas**. This chapter only covers the essential concepts – everything else is explained in detail in the following chapters.

---

## What Is This Streaming Tool?

The streaming tool connects **TikTok events** with **Minecraft** – in real time.

**The process:**

```
Viewers on TikTok
    ↓
send a gift / follow / like
    ↓
TikTok server notifies the tool
    ↓
The tool runs a Minecraft command
    ↓
Something happens in the Minecraft game
```

**Practical example:**
- Streamer is live on TikTok
- Viewer sends a gift
- Minecraft server receives: `/say "Danke für das Gift!"`
- All players see the message

---

## Core Idea: Events → Actions

The whole system is based on a simple principle:

```
EVENT (Something happened)
    ↓
PROCESSING (What does that mean?)
    ↓
ACTION (What should happen?)
```

**Three central concepts:**

### 1. **Events** – The Input Signal

An **event** means: Something happened.

Examples:
- User sends a gift
- User follows the channel
- User likes the stream

> [!NOTE]
> Events are structured data – they have properties such as "Who?", "When?", "What?", "How much?". More in [How the system works](./ch01-00-How-the-System-Works-Together.md).

### 2. **Processing** – "Understanding"

The program takes the event and asks:
- "What kind of event is this?" (Gift / Follow / Like?)
- "Who does it come from?"
- "Is this important?"

### 3. **Queue** – The Order

If 100 events arrive at the same time, they cannot all go to Minecraft at once. Instead:

```
Events arrive → are placed in the queue → processed one after the other
```

The queue prevents chaos and overload.

> [!NOTE]
> Imagine the supermarket: all the customers line up at the checkout. One after the other is served – fair, orderly processing.

---

## The 3 Phases (Overview)

The system works in 3 phases (details in [How the system works](./ch01-00-How-the-System-Works-Together.md)):

| Phase | What happens | Result |
|-------|--------------|--------|
| **1. Receive** | TikTok events are received | Structured event data |
| **2. Process** | Events are classified | Clear categories (Gift/Follow/Like/...) |
| **3. Execute** | Command is sent to Minecraft | Minecraft action is triggered |

---

## Configuration vs. Code

An important idea: **Configuration is separate from code.**

This means:
- **Code**: The logic – "how does the tool work?"
- **Configuration**: The rules – "what should happen when X happens?"

You can add new actions **without changing a single line of code** – only by editing the configuration.

> [!NOTE]
> Details about this in later chapters.

---

## Summary: The Basic Idea

The system works according to this pattern:

```
EVENTs arrive
    ↓
Place in queue
    ↓
Process one at a time
    ↓
Execute the appropriate action
    ↓
Minecraft responds
```

That's the whole concept. Everything else is **details and implementation**.

---

## Where to Go from Here?

Now that you know the basic idea:

- **[Next chapter: Setting up local development](./ch00-01-Setting-Up-Local-Development.md)** → Setup on your computer
- **[Then: How the system works together](./ch01-00-How-the-System-Works-Together.md)** → Architecture in moderate detail

After that we will go deeper into code, configuration, and specific features.

> [!NOTE]
> Don't worry if everything isn't clear right away. Each idea is explained later with examples and details!
