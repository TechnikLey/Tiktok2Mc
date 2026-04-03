## Threading & Queues: Asynchrone Verarbeitung

### Warum können wir Events nicht direkt ausführen?

Stell dir vor, ein Event-Handler würde Dinge **direkt** ausführen:

```python
# FALSCH - direkt ausführen:
@client.on(GiftEvent)
def on_gift(event):
    execute_minecraft_command(...)   # ← Blockt!
    wait_for_response()              # ← Dauert lange!
    update_overlay(...)              # ← Noch länger!
    # In der Zeit: Neue Events stauen sich auf
```

**Das Problem:** Während wir auf die Minecraft-Response warten, können keine **neuen TikTok-Events** verarbeitet werden. Die TikTok-Verbindung "hängt" und wir verlieren Events!

**Die Lösung:** Events in eine **Queue (Warteschlange)** legen und **asynchron** verarbeiten!

```python
# ✓ RICHTIG - in Queue legen:
@client.on(GiftEvent)
def on_gift(event):
    trigger_queue.put_nowait((target, username))  # ← Sehr schnell!
    # Fertig! Event-Handler kehrt sofort zurück
    
# Ein anderer Thread verarbeitet die Queue:
while True:
    target, username = trigger_queue.get()  # ← Warte auf nächste Aktion
    execute_minecraft_command(...)          # ← Kein Problem, wenn es dauert
```

---

### Die Queue-Architektur visualisiert

```
TIKTOK-VERBINDUNG
  (sehr schnell, darf nicht blocken)
        ↓
  Event-Handler
  (auch schnell!)
        ↓
  Trigger-Queue
  (Warteschlange)
   [GIFT_ROSE]
   [FOLLOW]
   [LIKE_GOAL_100]
   [GIFT_DIAMOND]
        ↓
  Worker-Thread
  (kann auch langsam sein)
        ↓
  Minecraft-Befehle
  (können lange dauern)
```

**Der Vorteil:** Die TikTok-Verbindung wird **nie** blockiert, egal wie überlastet der Worker-Thread ist!

---

### Queue Operations: put, get, put_nowait

```python
import queue
from threading import Thread

trigger_queue = queue.Queue(maxsize=1000)

# Operation 1: PUT (mit Warten)
trigger_queue.put((target, username))  
# Wenn Queue voll: Warte bis Platz frei wird

# Operation 2: PUT_NOWAIT (ohne Warten)
trigger_queue.put_nowait((target, username))
# Wenn Queue voll: Exception (QueueFull)
# → Das ist gut! Es wir ntuns, wenn was schiefläuft

# Operation 3: GET (mit Warten)
item = trigger_queue.get()
# Wenn Queue leer: Warte bis Item kommt
# → BLOCKT den Worker-Thread, bis etwas zu tun ist

# Operation 4: GET_NOWAIT (ohne Warten)
try:
    item = trigger_queue.get_nowait()
except queue.Empty:
    # Queue war leer, mach was anderes
```

---

### call_soon_threadsafe: Thread-sichere Aufrufe

In unserem Streaming-Tool verwenden wir `call_soon_threadsafe` statt normalem `put`:

```python
# Normaler put() - unsicher wenn MainLoop aktiv:
trigger_queue.put_nowait((target, username))  # Könnte Race Condition sein

# Besser: call_soon_threadsafe
MAIN_LOOP.call_soon_threadsafe(
    trigger_queue.put_nowait,
    (target, username)
)  # ✓ Thread-sicher!
```

**Warum?** `call_soon_threadsafe` sorgt dafür, dass die Operation im **MainLoop-Thread** ausgeführt wird, nicht im Event-Handler-Thread. Das vermeidet Race Conditions!

---

### Race Conditions und Locks (nochmal wiederholt)

Eine Race Condition tritt auf, wenn **zwei Threads gleichzeitig auf die gleiche Daten** zugreifen:

```python
# Race Condition:
counter = 0

Thread 1: counter = counter + 1  # Liest 0, schreibt 1
         ↓ (interrupt!)
Thread 2: counter = counter + 1  # Liest 0, schreibt 1
         
RESULT: counter = 1 (sollte aber 2 sein!)

# ✓ Mit Lock:
counter = 0
lock = threading.Lock()

Thread 1: with lock:            # Sperrt Lock
           counter = counter + 1  # Liest 0, schreibt 1
           # Lock freigegeben
         ↓
Thread 2: with lock:            # Wartet auf Lock
           counter = counter + 1  # Liest 1, schreibt 2
           # Lock freigegeben
           
RESULT: counter = 2 ✓
```

**Pattern:** Immer `with threading.Lock()` für kritische Daten verwenden!

---

### Praktisches Beispiel: Worker-Thread Implementation

Der Worker-Thread liest Events aus der Queue und verarbeitet sie:

```python
import threading
import queue

trigger_queue = queue.Queue()

def worker_thread():
    """Dieser Thread verarbeitet Trigger aus der Queue"""
    while True:
        try:
            # Warte auf nächste Aktion
            target, username = trigger_queue.get(timeout=1)
            
            # Verarbeite Aktion
            logger.info(f"Verarbeite: {target} für {username}")
            
            try:
                execute_trigger(target, username)
            except Exception as e:
                logger.error(f"Fehler bei Trigger {target}: {e}")
            
            # Markiere als "done"
            trigger_queue.task_done()
            
        except queue.Empty:
            # Timeout: Nichts in der Queue, weitermachen
            continue
        except Exception as e:
            logger.error(f"Worker-Thread Fehler: {e}")

# Starte Worker-Thread (als Daemon, läuft im Hintergrund)
worker = threading.Thread(target=worker_thread, daemon=True)
worker.start()
```

---

### Overlay-Updates: Ein praktisches Anwendungsbeispiel

Overlay-Updates für Like-Counter verwenden auch die Queue:

```python
# Separate Queue für Overlay-Updates
like_queue = queue.Queue()

@client.on(LikeEvent)
def on_like(event):
    global start_likes, last_overlay_sent, last_overlay_time
    
    if start_likes is None:
        start_likes = event.total
        return
    
    # Berechne neue Likes
    delta = event.total - start_likes
    
    # Sende Update an Overlay (aber nicht zu oft!)
    now = time.time()
    if delta > 0 and (now - last_overlay_time) >= 0.5:  # Max. 2x pro Sekunde
        try:
            MAIN_LOOP.call_soon_threadsafe(
                like_queue.put_nowait,
                delta  # Nur die Differenz senden
            )
            last_overlay_sent = delta
            last_overlay_time = now
        except queue.Full:
            logger.warning("Like-Queue ist voll, Update übersprungen")
```

**Das ist wichtig:** Nicht jedes Overlay-Update senden! Mit `OVERLAY_INTERVAL` (z.B. 0.5 Sekunden) begrenzen wir die Updates. Das spart Bandbreite!

---

### Timing & Throttling: Events nicht zu schnell kommen lassen

Manchmal kommen Events SO schnell an, dass wir sie **drosseln** (throttle) müssen:

```python
import time

last_event_time = 0
THROTTLE_INTERVAL = 0.1  # Mindestens 100ms zwischen Events

@client.on(LikeEvent)
def on_like(event):
    global last_event_time
    
    # Ignoriere Events die zu dicht beieinander liegen
    now = time.time()
    if now - last_event_time < THROTTLE_INTERVAL:
        return  # Zu schnell! Skippen.
    
    last_event_time = now
    
    # ... rest des Event-Handlers ...
```

**Warum?** Wenn Like-Events alle 50ms ankommen , können wir sie nicht alle verarbeiten. Mit Throttling verlanagsamen wir gezielt die ausführung.

---

### Finale Anmerkung

**Das Wichtigste zu verstehen:**

Events sind **nicht direkt** = Aktion.

Stattdessen:

```
TikTok-Event → Handler → Queue → Worker-Thread → Aktion
               (schnell)   (Puffer)    (kann langsam sein)
```

Das macht das System:
- ✓ Stabil (Events gehen nicht verloren)
- ✓ Skalierbar (viele Events gleichzeitig)
- ✓ Wartbar (Aktion-Logik ist getrennt)