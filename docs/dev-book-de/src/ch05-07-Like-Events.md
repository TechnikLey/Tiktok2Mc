## Like-Events

### Das Besondere an Likes: Kontinuierliche Zählung

Like-Events sind **völlig anders** als Gifts und Follows:

| Merkmal | Gifts | Follows | Likes |
|--------|-------|---------|-------|
| **Event-Typ** | Diskrete Events ("Gift gesendet") | Diskrete Events ("Folgt") | Kontinuierliche Zählung |
| **Häufigkeit** | Selten (User sendet Geschenk) | Selten (User folgt) | **SEHR OFT** |
| **Benutzernamen** | Ja, sichtbar | Ja, sichtbar | Eher selten sichtbar |
| **Trigger-Logik** | "Wenn Gift" | "Wenn Follow" | "Wenn Zähler erreicht z.b. 100er-Marke" |
| **Threading-Problem** | Nein, einfach | Nein, einfach | **JA, Race Conditions!** |

**Das Kernproblem:** Like-Events kommen so schnell an, dass **mehrere Threads gleichzeitig** auf die gleichen Daten zugreifen können. Das führt zu **Race Conditions** wenn wir nicht aufpassen.

---

### Das Problem der Race Conditions erklärt

Stell dir vor, zwei Like-Events kommen **gleichzeitig** an:

```
Thread 1:  Liest Like-Zähler:  100
Thread 2:  Liest Like-Zähler:  100
           ↓
Thread 1:  Berechnet: 100 > last_blocks? JA → Trigger!
Thread 2:  Berechnet: 100 > last_blocks? JA → Trigger!
           ↓
Thread 1:  Schreibt: last_blocks = 100
Thread 2:  Schreibt: last_blocks = 100
           ↓
ERGEBNIS: Trigger ausgelöst 2x statt 1x! 
```

**Lösung: Lock (Mutex)**

Ein Lock sorgt dafür, dass nur **ein Thread gleichzeitig** den kritischen Code ausführt:

```
Thread 1:  Wartet auf Lock... ⏳
Thread 2:  BEKOMMT LOCK ✓
           Liest, berechnet, schreibt
           GIBT LOCK FREI
           ↓
Thread 1:  BEKOMMT LOCK ✓
           Liest, berechnet, schreibt (mit aktualisierten Daten!)
           GIBT LOCK FREI
           ↓
ERGEBNIS: Trigger ausgelöst 1x (+ 1x, richtig sequenziell) ✓
```

---

### Like-Zählung visualisiert: Der Unterschied zu anderen Events

```
GIFTS/FOLLOWS (Diskret):
  
  00:00 - Event "Gift Rose"        → Trigger: "GIFT_ROSE"
  00:05 - Event "Follow"           → Trigger: "FOLLOW"
  00:10 - (nichts)
  00:15 - Event "Gift Diamond"     → Trigger: "GIFT_DIAMOND"

LIKES (Kontinuierlich):

  00:00 - LikeEvent: total=1000
  00:01 - LikeEvent: total=1000
  00:02 - LikeEvent: total=1000
  00:03 - LikeEvent: total=1005  ← +5 Likes!
  00:04 - LikeEvent: total=1012  ← +7 Likes!
  
  Wenn wir jede 10er-Marke triggern wollen:
  
  1000-1009: keine Trigger
  1010+    : 1 Trigger
  1020+    : 1 Trigger
  1030+    : 1 Trigger
  etc.

  Mit unserem Code:
  
  current_blocks = 1012 // 10 = 101
  last_blocks = 100
  diff = 101 - 100 = 1
  → Trigger 1x ausgelöst ✓
```

---

### LikeEvent Struktur

Ein `LikeEvent` enthält diese Informationen:

```python
event.total              # Gesamte Like-Anzahl bis jetzt: 1005, 1010, 1025 etc.
event.likeCount          # Likes in dieser Session/Streak: 5, 7, 15 etc.

event.user.nickname      # Benutzername manchmal nicht verfügbar
event.timestamp          # Zeitpunkt des Events
```

---

### Like-Event Processing: Der 6-Schritt-Ablauf

Wenn Like-Events ankommen, passiert folgendes:

```
1. ERSTES EVENT?
   Ist start_likes noch None? JA → Initialisieren, return
   
2. DELTA BERECHNEN  
   Likes seit Start: current_total - start_likes
   z.B.: 1025 - 1000 = 25
   
3. LOCK HOLEN
   Warte bis kein anderer Thread aktiv ist
   
4. REGELN DURCHGEHEN
   Für jede Like-Regel:
     - Intervall auslesen ("every": 100)
     - Berechnen, wie viele Intervalle erreicht wurden
     - Prüfen, ob neue Intervalle seit letztem Check
     
5. TRIGGERS QUEUEN
   Für jedes neue Intervall:
     - Aktion in die Queue legen
     
6. LOCK FREIGEBEN
   Nächster Thread kann jetzt arbeiten
```

---

### Intervall-Berechnung erklärt

Das ist die Kern-Logik für Like-Zählung:

```python
every = 100  # Alle 100 Likes einen Trigger

# Szenario 1: 1010 Likes gesamt
current_blocks = 1010 // 100  # = 10 (zehnte 100er-Marke)
last_blocks = 9               # (wir waren bei 900)
diff = 10 - 9 = 1             # → 1 Trigger

# Szenario 2: 1025 Likes gesamt  
current_blocks = 1025 // 100  # = 10 (immer noch zehnte Marke!)
last_blocks = 10              # (wir wissen schon von Marke 10)
diff = 10 - 10 = 0            # → Kein neuer Trigger

# Szenario 3: 1200 Likes gesamt
current_blocks = 1200 // 100  # = 12 (zwölfte Marke)
last_blocks = 10              # (alte Marke)
diff = 12 - 10 = 2            # → 2 Triggers hintereinander!
```

**Das `//` ist wichtig!** Das ist Integer-Division (ganzzahlig). Sie ist der Schlüssel für die Block-Berechnung.

---

### Fehlerbehandlung bei Like-Events

Like-Handler brauchen besondere Fehlerbehandlung wegen des Locks:

```python
like_lock = threading.Lock()

try:
    with like_lock:  # ← Python: Automatisch lock/unlock
        # Kritischer Code hier
except Exception as e:
    logger.error(f"Fehler im Like-Handler: {e}", exc_info=True)
    # Lock wird AUTOMATISCH freigegeben, auch wenn Error!
```

**Warum `with like_lock` verwenden?** 

Weil Python automatisch den Lock **immer** freigibt, selbst wenn ein Error passiert. Das ist wichtig - sonst würde der Lock "hängenbleiben" und alle anderen Threads warten ewig!

---

### Praktisches Beispiel: Ein vollständiger Like-Handler

Hier ist ein realer, funktionierender Like-Handler:

```python
import threading

# Global initialisieren
like_lock = threading.Lock()
start_likes = None
last_overlay_sent = 0
last_overlay_time = 0

LIKE_TRIGGERS = [
    {"id": "goal_100", "every": 100, "last_blocks": 0, "function": "LIKE_GOAL_100"},
    {"id": "goal_500", "every": 500, "last_blocks": 0, "function": "LIKE_GOAL_500"},
]

def initialize_likes(total):
    """Beim ersten Event: Startwert setzen"""
    global start_likes
    start_likes = total
    logger.info(f"Like-Tracking initialisiert mit: {total} Likes")

@client.on(LikeEvent)
def on_like(event: LikeEvent):
    """
    Verarbeitet Like-Events von TikTok.
    - Kontinuierliche Zählung statt einzelner Events
    - Thread-sicher mit Locks
    - Triggert beim Erreichen von Like-Marken (100, 500, 1000, etc.)
    """
    global start_likes, last_overlay_sent, last_overlay_time
    
    try:
        # SCHRITT 1: Erste Initialisierung?
        if start_likes is None:
            initialize_likes(event.total)
            return
        
        # SCHRITT 2: Berechne Likes seit Start
        total_since_start = event.total - start_likes
        
        logger.debug(f"Like-Event: {event.total} total, "
                    f"{total_since_start} seit Start")
        
        # SCHRITT 3: Lock holen (Thread-sicherheit!)
        with like_lock:
            
            # SCHRITT 4: Jede Like-Regel durchgehen
            for rule in LIKE_TRIGGERS:
                every = rule["every"]
                
                # Invalide Regeln überspringen
                if every <= 0:
                    continue
                
                # SCHRITT 5: Berechne aktuelle und letzte Block-Nummer
                current_blocks = total_since_start // every
                last_blocks = rule["last_blocks"]
                
                # Neue Blocks erreicht?
                if current_blocks > last_blocks:
                    diff = current_blocks - last_blocks
                    rule["last_blocks"] = current_blocks
                    
                    logger.info(
                        f"Like-Trigger '{rule['id']}': "
                        f"{current_blocks} Marken erreicht (+{diff})"
                    )
                    
                    # SCHRITT 6: Für jeden neuen Block: Action queuen
                    for _ in range(diff):
                        try:
                            MAIN_LOOP.call_soon_threadsafe(
                                trigger_queue.put_nowait,
                                (rule["function"], {})
                            )
                        except Exception as e:
                            logger.error(
                                f"Fehler beim Queuen von Like-Action: {e}",
                                exc_info=True
                            )
        
        # (Lock wird hier automatisch freigegeben)
        
    except Exception as e:
        logger.error(
            f"Unerwarteter Fehler im Like-Handler: {e}",
            exc_info=True
        )
```

**Was macht dieser Code?**

1. **Initialisieren** – Beim ersten Event den Startwert setzen
2. **Delta berechnen** – Wie viele Likes sind neu?
3. **Lock holen** – Thread-sicherheit aktivieren
4. **Regeln durchgehen** – Für jede Like-Marke (100, 500, etc.)
5. **Blocks berechnen** – Mit Integer-Division `//`
6. **Queuen** – Auf jede neue Marke eine Aktion

---

### Noch einfacher: Minimales Beispiel

Das absolute Minimum (funktioniert auch, braucht aber manuelle Lock-Verwaltung):

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
        # Wenn delta 100 erreicht: Trigger
        if delta >= 100 and delta - 100 < 1:  # Erste 100er-Marke
            MAIN_LOOP.call_soon_threadsafe(
                trigger_queue.put_nowait,
                ("LIKE_GOAL_100", {})
            )
```

Das ist viel kürzer, aber auch weniger flexibel. Der komplette Handler oben ist besser!

---

### Unterschied zwischen Gifts/Follows und Likes

Um zu verstehen, warum Like-Handler komplexer sind:

**Gifts/Follows:**
```python
# Event kommt → Sofort verarbeiten → Fertig
@client.on(GiftEvent)
def on_gift(event):
    queue.put(...)
```

**Likes:**
```python
# Events kommen SEHR OFT → Track wie viele → Trigger pro Intervall
@client.on(LikeEvent)
def on_like(event):
    # Zähle: Wie viele Likes seit Start?
    delta = event.total - start_likes
    
    # Berechne: Wie viele 100er-Marken?
    blocks = delta // 100
    
    # Vergleiche: Neue Marken seit letztmal?
    if blocks > last_blocks:
        # DANN: Triggern!
        queue.put(...)
```

Der Unterschied: **Aggregation statt direkte Weitergabe!**

---

### Edge Cases bei Like-Events

Was kann schiefgehen?

| Szenario | Problem | Lösung |
|----------|---------|--------|
| Like-Event vor Initialisierung | start_likes ist None | `if start_likes is None: initialize()` |
| Zwei Events gleichzeitig | Race Condition | `with like_lock` schützt |
| Intervall ist 0 | Division by Zero | `if every <= 0: continue` |
| Sehr schnelle Like-Flut | Viele Events/Sec | Blocks werden korrekt aggregiert |
| Lock hängt | Thread blockiert ewig | `with like_lock` auto-freigibt |

**Fazit:** Like-Handler versprechen die meiste Fehlerbehandlung, besonders wegen des Locks.

---

### Zusammenfassung & Nächster Schritt

**Was du jetzt weißt:**

| Konzept | Erklärung |
|---------|-----------|
| **Likes ≠ Gifts** | Kontinuierliche Zählung statt einzelner Events |
| **Race Conditions** | Mehrere Threads greifen gleichzeitig zu → Lock notwendig |
| **Block-Berechnung** | `blocks = total_likes // intervall` |
| **Initialisierung** | Beim ersten Event: Startwert setzen |
| **Lock-Pattern** | `with threading.Lock()` für Thread-Sicherheit |
| **Fehlerbehandlung** | Lock wird auch bei Errors freigegeben (`with` macht das) |

**Was passiert NACH dem Like-Handler?**

Die gequeuteten Like-Aktionen werden später vom Worker-Thread verarbeitet (z.B. "Gratuliere zu 100 Likes!").

→ [Nächstes Kapitel: Threading & Queues](ch05-08-Threading-and-Queues.md)

---

> [!NOTE]
> Like-Handler zeigen dir die echte Komplexität von Multi-Threading. Das ist nicht einfach, aber super wichtig für performante Systeme!