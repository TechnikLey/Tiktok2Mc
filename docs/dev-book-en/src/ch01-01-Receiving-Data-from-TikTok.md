# Receiving Data from TikTok (Phase 1)

In this chapter you will understand how the system **notices** that something is happening on TikTok. This is the first component of the data chain.

---

## The Problem: How Do We Listen to TikTok?

**The challenge:**

TikTok is a closed platform. There is no official, free API for streamers that delivers real-time events. We have to get creative.

So we use **reverse engineering** – we observe how the TikTok app itself communicates with the servers and build on that.

---

## Solution: The TikTokLive API

We use the **TikTokLive** library (open source), which does exactly that: it imitates the TikTok app and receives events directly.

### How Does TikTokLive Work?

```
TikTok server
    ↓
    ├─→ (sends events to millions of apps)
    ├─→ Official TikTok app
    ├─→ Other live tool apps
    └─→ TikTokLive Library (our tool)
         ↓
    We see the events LIVE
```

The library:
1. **Connects** to TikTok servers (like the mobile app)
2. **Listens** on the WebSocket stream
3. **Receives events** (gifts, follows, likes) in real time
4. **Hands them over** to our Python program

### What Are Events?

An **event** is a structured message that TikTok sends:

```
Event type:    "Gift"
User:          "streamer_fan_123"
Gift count:     5
Gift value:     1000 coins
```

Each of these data points arrives. The program knows the structure and knows how to read it.

---

## What Do We Connect With? WebSocket vs. HTTP

### WebSocket (we use this)

```
┌─ Connection ──┐
│  open and     │  Both sides can send
│  persistent   │  data at any time. Perfect for real time.
└───────────────┘
```

**Advantages:**
- ✓ Real time (instant events)
- ✓ Efficient (always open, not constantly new connections)
- ✓ Bidirectional (we can also send data back)

**Disadvantage:**
- ✗ More complex than HTTP

### HTTP (old alternative)

```
We ask:   "Are there new events?"
Server:   "Yes, here!"
We ask:   "Are there new events?"
Server:   "No"
We ask:   "Are there new events?"
...
```

**Problem:** Constantly asking is inefficient. That's like constantly asking "Are you awake now?" instead of waiting for the person to call you.

---

## The Internal Process: How Events Enter the Program

```
1. START: Program starts
   ↓
2. CONNECT: Program connects to TikTok via WebSocket
   "Hello TikTok, it's your client"
   ↓
3. LISTEN: WebSocket remains open
   Program awaits events
   ↓
4. EVENT ARRIVES: User sends a gift
   TikTok sends: { "type": "gift", "user": "xyz", ... }
   ↓
5. EVENT RECEIVED: Our program accepts it
   ↓
6. EVENT FORWARDED: To Phase 2 (Processing)
```

---

---

## Summary of Phase 1

**What happens here:**
- TikTokLive library connects to TikTok
- It receives events as structured data
- These are immediately forwarded to Phase 2

**What you should know:**
- Events come LIVE (WebSocket, not HTTP)
- An event has structure: type, user, data
- The concept of events has already been explained in [Basic concepts & terms](./ch00-00-Fundamentals-and-Concepts.md)

**What does not happen here:**
- We do not analyze events (that is Phase 2)
- We don't send anything to Minecraft (that is Phase 3)
- We do not store events permanently

> [!TIP]
> The TikTokLive library is not necessarily very reliable, but it is the best free option. You are welcome to look at alternatives yourself.
> 
> You will learn the code implementation of the TikTokLive library in [Python in this project](./ch05-00-Python-in-This-Project.md).

---

**Next chapter:** [Processing events](./ch01-02-Processing-Events.md) – Now let's see what the program does WITH the events.
