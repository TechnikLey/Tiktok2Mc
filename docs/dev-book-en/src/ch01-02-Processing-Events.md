# Processing Events (Phase 2)

Now the raw data has arrived. But is it usable? In this chapter you will learn how the system "understands" events and prepares them for the next phase.

---

## The Problem: Data Is Raw

From Phase 1 we get raw data from TikTok:

```
{
  "type": "gift",
  "user": { "id": 12345, "name": "xyz" },
  "gift": { "id": 5, "count": 10, "repeatCount": 1 },
}
```

**Questions we need to answer:**

- ✓ "What kind of event is this?" (Gift / Follow / Like?)
- ✓ "Who does it come from?" (Which user?)
- ✓ "How much is it?" (Value, number, quantity?)
- ✓ "Is it important?" (Should the game react?)
- ✓ "What is the next action?" (Which command should be sent to Minecraft?)

---

## Solution: The Event Processing System

### Step 1: Classify

The program sorts the event into a category:

```
Raw data arrives
    ↓
"Is this a gift?"
    ↓
"Yes → This is the 'Gift' category"
    ↓
Event is registered as "GiftEvent"
```

The system knows different types:

| Type | Example |
|------|---------|
| **Gift** | User sends 5x gifts |
| **Follow** | User follows the channel |
| **Like** | User likes a stream |
| **Share** | User shares the stream |
| **Comment** | User comments |

### Step 2: Extract Data

The important information is extracted from the raw data:

```
Raw data: {
  "type": "gift",
  "user": { "id": 12345, "name": "streamer_fan_xyz", ... },
  "gift": { "id": 5, "count": 3, ... }
}

        ↓ [EXTRACTED]

Structured data:
├─ Event type: "gift"
├─ User name: "streamer_fan_xyz"
├─ Gift count: 3
```

Only the data that is relevant is kept.

### Step 3: Place in Queue

**The problem:** If 100 viewers send gifts at the same time, not all of them can go to Minecraft at once.

**The solution:** A **queue** – as already explained in [Basic concepts](./ch00-00-Fundamentals-and-Concepts.md).

The queue ensures that everything is processed in order – fairly and neatly.

---

## The Internal Process: How Events Are Processed

```
1. EVENT ARRIVES from Phase 1
   ↓
2. CLASSIFY
   "This is a gift"
   ↓
3. EXTRACT DATA
   User = "xyz", count = 5
   ↓
4. ENQUEUE
   Entry in the queue
   ↓
5. QUEUE PROCESSES
   One event after another
   ↓
6. PASS TO PHASE 3
   "Gift from xyz, 5x → Minecraft!"
```

---

## Multiple Events at the Same Time (Concurrency)

The system has to handle many events at the same time. The queue is the solution.

The queue is usually very small – events are processed immediately. It is not storage, but a **queue**.

---

## Special Filter: Not All Events Are Equal

The system can prioritize events – gifts are more important than likes, for example.

These priorities are set in the **configuration**, not in the code.

---

## Error Scenarios: What Can Go Wrong?

| Problem | Consequence | Solution |
|---------|-------------|----------|
| **Event structure unknown** | Classification failed | Error log, event is discarded |
| **Queue overflows** | Memory problem (very rare) | Delete older events |
| **Too many events per second** | Backlog builds up | Minecraft takes longer to react |
| **Event arrives damaged** | Data parse error | Validation in the system, faulty events ignored |

---

## Summary of Phase 2

**What happens here:**
- Raw events are classified
- Data is extracted and structured
- Events are placed in a queue
- The queue processes them one after the other

**What you should know:**
- The queue ensures order
- Multiple events are processed one after the other, not in parallel

**What does not happen here:**
- We do not write events to disk (optional)
- We don't send anything to Minecraft (next phase)
- We don't show anything in the GUI (done separately)

---

**Next chapter:** [Sending data to Minecraft](./ch01-03-Sending-Data-to-Minecraft.md) – Now it gets concrete: the command goes to the game!
