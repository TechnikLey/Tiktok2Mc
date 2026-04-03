## Event-System verstehen

Bevor wir spezifische Event-Typen (Gifts, Follows, Likes) analysieren, müssen wir verstehen, wie Events **strukturiert** sind und wie sie **fließen**.

---

## Event-Struktur

Ein Event ist nicht einfach "etwas ist passiert" – es enthält **Daten** über das, was passiert ist.

### GiftEvent Beispiel

```python
# Ein echtes GiftEvent hat diese Struktur:
{
    "user": {
        "id": "123456789",
        "nickname": "Streamer123",
        "signature": "Ich liebe Minecraft",
        # ... mehr User-Daten
    },
    "gift": {
        "id": 1001,
        "name": "Rose",
        "repeat_count": 3,              # Wie oft wurde dieser Gift gesendet?
        "combo": True,                  # Kann dieser Gift kombiniert werden?
        "description": "A beautiful rose"
    },
    "total_count": 5,                   # Gesamt-Gifts von diesem User
}
```

Du greifst darauf zu mit:

```python
def on_gift(event: GiftEvent):
    event.user.nickname              # "Streamer123"
    event.gift.name                  # "Rose"
    event.gift.repeat_count          # 3
    event.gift.combo                 # True/False
    event.total_count                # 5
```

---

## Event-Objekte vs. Dictionaries

Die Ereignisse sind nicht einfach **Dictionaries** (wie `{"name": "Rose"}`), sondern **Objekte**:

```python
# Objekt (was wir nutzen)
event.gift.name      # ✓ Funktioniert, IDE gibt Autocomplete

# Dictionary (würde nicht funktionieren)
event["gift"]["name"]  # ✗ Komplizierter, keine IDE-Hilfe
```

**Warum Objekte besser sind:**

- IDE kann Autocomplete geben (z.B. `event.gift.<Vorschlag>`)
- Typ-Sicherheit (Python weiß, dass `event.gift.name` ein String ist)
- Weniger Fehler (falsche Schlüssel → sofort Error statt Silent-Fail)

---

## Event-Kategorien

Events werden in **mehrere Kategorien** eingeteilt:

| Kategorie | Beispiele | Zweck |
|-----------|----------|-------|
| **User Events** | Follow, Gift, Like | Aktion eines Zuschauers |
| **System Events** | Connect, Disconnect | System-Status |
| **Stream Events** | StreamStart, StreamEnd | Stream-Lebenszyklus |

**Für diese Dokumentation konzentrieren wir uns auf:**

- ✓ GiftEvent (Zuschauer sendet Gift)
- ✓ FollowEvent (Zuschauer folgt)
- ✓ LikeEvent (Zuschauer gibt Like)

---

## Event-Handler Workflow

Wenn ein Event kommt, passiert folgendes:

```
1. TikTok Live Stream (etwas passiert)
   ↓
2. TikTokLive API empfängt Event (über WebSocket)
   ↓
3. Client sucht passenden Handler (@client.on(...))
   ↓
4. Handler-Funktion wird aufgerufen mit Event-Daten
   ↓
5. Handler verarbeitet Event
   ↓
6. Next Event kann empfangen werden
```

**Timing:** Das alles passiert in **Millisekunden!**

---

## Event-Daten Validieren

Nicht alle Event-Daten sind garantiert vorhanden. Wir müssen **defensiv** programmieren:

```python
@client.on(GiftEvent)
def on_gift(event: GiftEvent):
    # ✓ Sicher: mit Fallback
    gift_name = getattr(event.gift, "name", "Unknown")
    
    # ✓ Sicher: try-except
    try:
        user_id = event.user.id
    except AttributeError:
        user_id = None
    
    # ✗ Unsicher: könnte None sein
    # repeat_count = event.repeat_count  # Was wenn Attribut fehlt?
```

**Regel:** Immer davon ausgehen, dass Daten **fehlen oder None sein können**.

---

## Event-Modifikationen & Flags

Manche Events haben zusätzliche **Flags** oder **Modifikatoren**:

### Combo-Flag

```python
if event.gift.combo:  # Kann dieses Gift kombiniert werden?
    # Ja: Der Zuschauer kann dieselbe Gift mehrfach senden
    # → event.repeat_count sagt wie oft
    count = event.repeat_count  # z.B. 5
else:
    # Nein: Immer nur einmal
    count = 1
```

### Streaking-Flag (Advanced)

```python
# Combo-Gifts können über mehrere Sekunden "streaken"
if getattr(event, "streaking", False):
    # Das ist ein Intermediate-Event (nicht das letzte)
    # Können wir überspringen wenn wir nur finale Events wollen
    return
```

---

## Fehler in Events (Exception Handling)

Events können problematisch sein. Wir müssen abfangen:

```python
@client.on(GiftEvent)
def on_gift(event: GiftEvent):
    try:
        # Event-Daten auslesen
        gift_name = event.gift.name
        user = event.user.nickname
        
        # Logik ausführen
        # ...
    
    except AttributeError:
        # Daten fehlen
        logger.error(f"Gift event missing data: {event}")
        return
    
    except Exception as e:
        # Unexpekted
        logger.error(f"Error processing gift: {e}", exc_info=True)
        return
```

**Wichtig:** Ein fehlerhaftes Event darf **nicht** das ganze Programm crashen. Andere Events müssen weiterlaufen.

---

## Event-Daten speichern & verarbeiten

Manchmal wollen wir Event-Daten **später** verarbeiten (z.B. in der Queue):

```python
@client.on(GiftEvent)
def on_gift(event: GiftEvent):
    # Nicht sofort verarbeiten – speichern!
    event_data = {
        "type": "gift",
        "gift_name": event.gift.name,
        "user": event.user.nickname,
        "count": event.repeat_count,
        "timestamp": event.created_at
    }
    
    # In Queue legen (wird später verarbeitet)
    trigger_queue.put_nowait(event_data)
```

**Warum?** Weil verschiedene Threads gleichzeitig arbeiten:

```
Thread 1: TikTok Events empfangen (schnell!)
Thread 2: Events verarbeiten (langsamer!)

Wenn Thread 2 langsam ist, staut sich Events in der Queue auf.
Das ist OK – das ist der Sinn der Queue.
```

---

## Zusammenfassung: Event-System

✓ Events sind **Objekte** mit strukturierten Daten  
✓ Unterschiedliche Event-Typen (Gift, Follow, Like, etc.)  
✓ Handler werden **automatisch** aufgerufen
✓ Daten müssen **validiert** werden  
✓ Fehler müssen **abgefangen** werden  
✓ Events werden **nicht sofort verarbeitet**, sondern gepuffert (Queue)  

---

## Nächster Schritt

Jetzt verstehst du das **System**. Der nächste Schritt ist, spezifische Event-Typen anzuschauen.

**→ [Gift-Events](./ch05-05-Gift-Events.md)**

Dort sehen wir, wie Gift-Events speziell funktionieren (mit Combos, Repeats, etc.).