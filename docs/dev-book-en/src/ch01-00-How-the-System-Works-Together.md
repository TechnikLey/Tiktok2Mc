# How the System Works Together

In this chapter you will understand the **architecture** of the streaming tool – i.e. how the individual components fit together and how data flows from TikTok to Minecraft.

---

## The Big Picture: The Data Flow

The system works according to a clear, three-phase pattern:

```
┌─────────────────────────────────────────────────────────────────┐
│                    THE 3 PHASES OF THE SYSTEM                   │
└─────────────────────────────────────────────────────────────────┘

Phase 1: RECEIVE
    TikTok events
        ↓
    TikTokLive API
        ↓
    "User XY followed"

           ↓ ↓ ↓

Phase 2: PROCESS
    Analyze event
        ↓
    Filter and sort data
        ↓
    "Is this a follow? From whom? When?"

           ↓ ↓ ↓

Phase 3: EXECUTE
    Trigger action
        ↓
    Send RCON command
        ↓
    Minecraft executes
```

Each phase has a clear task:

| Phase | Task | Who does it? |
|-------|------|--------------|
| **1. Receive** | Collect data from TikTok servers | TikTokLive API (in our program) |
| **2. Process** | Understand & document events | Python scripts analyze the raw data |
| **3. Execute** | Send command to Minecraft | RCON via network connection |

---

## Phase 1: Receive Data from TikTok

**The problem:** How do we even know when someone sends a gift on TikTok?

TikTok does not have an open **official API** for developers. That's why we use the **TikTokLive library**.

The program connects to TikTok's servers and **listens**.

As soon as an action happens (gift, follow, like), we receive a message. This message is structured as follows:

```
{
  "Event": "Gift",
  "From": "UserName",
  "GiftID": "12345",
}
```

**What happens after that?** The data goes directly to the next phase → **Process**

> [!NOTE]
> **For beginners:** Imagine you are reading a message. The text is not yet sorted – you must first understand who is writing, what is being written, and when it was written.

---

## Phase 2: Process and Analyze Events

**The problem:** TikTok's raw data is unstructured. We have to classify and structure it before we can do anything with it.

The program takes the received event and asks:

- **"What happened?"** (Gift / Follow / Like / Etc.)
- **"Who was it?"** (username, user ID)
- **"How much?"** (number of gifts, size of gift)
- **"What should happen now?"** (Which Minecraft action does this trigger?)

The system **categorizes** events internally and **stores important metadata**. These are then placed in a queue so that they can be processed one after the other.

**Why a queue?**

If 100 viewers send gifts at the same time, not all events can go to Minecraft at once. That would overload the server. Instead, they are lined up and processed one after the other.

> [!NOTE]
> **For beginners:** Think of the supermarket cashier. If 10 people come at the same time, you line up. One by one pays. The queue ensures order.

---

## Phase 3: Send Data to Minecraft

**The problem:** How do we tell the Minecraft server what should happen?

Minecraft has a remote control system called **RCON** (Remote Console). This is like a remote control for the Minecraft server.

Through RCON we can send commands:

- `/say "Danke für das Gift!"`
- `/give @s diamond 5`
- `/function my_namespace:special_event`

The program:
1. Determines which command is necessary (based on the event)
2. Sends it to Minecraft via RCON
3. The Minecraft server executes the command

This all happens in **real time** – usually in milliseconds.

---

## Connection: How Everything Fits Together

The most important thing: **The 3 phases are interdependent:**

```
(1) Receive  →  (2) Process  →  (3) Execute
      ↓               ↓               ↓
  TikTok API     Python logic     RCON command
```

If one phase fails, the entire chain stops working:

| If phase fails | Consequence |
|----------------|-------------|
| **1 breaks** | No events from TikTok → Nothing happens |
| **2 breaks** | Events are not understood → Wrong action or none at all |
| **3 breaks** | Command doesn't reach Minecraft → Game has no response |

---

## Next Steps

Each of these 3 phases is explained in detail in this chapter:

- [Receiving data from TikTok](./ch01-01-Receiving-Data-from-TikTok.md) – How the API works
- [Processing events](./ch01-02-Processing-Events.md) – How the program analyzes data
- [Sending data to Minecraft](./ch01-03-Sending-Data-to-Minecraft.md) – How RCON works

Once you understand the basic idea, you can read the subsections to go deeper.

> [!NOTE]
> **Concepts:** Basic ideas (events, queue, etc.) have already been briefly explained in [Basic concepts & terms](./ch00-00-Fundamentals-and-Concepts.md). This chapter shows the **architecture**.
> 
> **Code & Details:** How handlers work (`@client.on`), how `actions.mca` is written, Control Methods (DCS/ICS), etc. – that comes in later chapters.

> [!TIP]
> If the architecture isn't 100% clear yet: That's completely normal. Many concepts will become more concrete in the coming chapters.
