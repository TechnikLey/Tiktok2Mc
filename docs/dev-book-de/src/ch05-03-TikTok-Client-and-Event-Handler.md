## TikTok-Client & Event-Handler

Das ist das **Herzstück** der Event-Verarbeitung. Hier erstellen wir die Verbindung zu TikTok und registrieren Funktionen, die auf Events reagieren.

---

## Funktion

```
1. Erstelle TikTok-Client
   ↓
2. Registriere Handler für bestimmte Events
   ↓
3. Handler wird AUTOMATISCH aufgerufen, wenn Event kommt
```

Das ist nicht "Polling" (ständig fragen "ist was los?"), sondern **Event-Driven** (das System sagt dir, wenn was los ist).

Visualisiert:

```
TikTok Live Stream läuft...
    ↓
    ↓ [Event kommt: jemand sendet Gift]
    ↓
TikTokLive API ruft automatisch: on_gift(event)
    ↓
on_gift() wird ausgeführt
    ↓
Wir verarbeiten das Gift
```

---

## Schritt 1: Client erstellen

```python
from TikTokLive import TikTokLiveClient
from TikTokLive.events import GiftEvent, FollowEvent, LikeEvent

def create_client(user):
    """Erstelle einen TikTok-Live-Client"""
    client = TikTokLiveClient(unique_id=user)
    return client
```

**Was passiert:**
- `TikTokLiveClient(unique_id=user)` verbindet sich mit einem bestimmten TikTok-Account
- Der Client **lauscht** auf alle Events aus diesem Stream
- Noch keine Handler registriert – das kommt als Nächstes

---

## Schritt 2: Handler registrieren

Ein **Handler** ist einfach eine Funktion, die auf ein Event reagiert. Wir nutzen den **Dekorator-Ansatz**:

```python
@client.on(GiftEvent)
def on_gift(event: GiftEvent):
    print(f"Gift empfangen: {event.gift.name}")
```

Das `@client.on(...)` Dekorator sagt: "Rufe diese Funktion auf, wenn ein GiftEvent kommt."

**Ähnlich für andere Events:**

```python
@client.on(FollowEvent)
def on_follow(event: FollowEvent):
    print(f"Neue Follow: {event.user.nickname}")

@client.on(LikeEvent)
def on_like(event: LikeEvent):
    print(f"Likes insgesamt: {event.total}")
```

---

## Schritt 3: Handler mit Logik füllen

Das ist wo's interessant wird. Der Handler muss:

1. **Event-Daten auslesen** – Was ist im Event?
2. **Validieren** – Ist es ein gültiges Event?
3. **Trigger finden** – Welche Aktion soll ausgelöst werden?
4. **In Queue legen** – Nicht sofort ausführen, sondern queuen!

**Grund für Queue:** Events kommen sehr schnell. Wenn wir sie sofort verarbeiten, könnte die nächste Event-Verarbeitung blockieren oder die RCON verbindung bricht ab.

**Vereinfachtes Beispiel:**

```python
@client.on(GiftEvent)
def on_gift(event: GiftEvent):
    # 1. Event-Daten auslesen
    gift_name = event.gift.name           # z.B. "Rose"
    gift_id = event.gift.id               # z.B. 1001
    repeat_count = event.repeat_count     # z.B. 3 (Combo)
    user = event.user.nickname            # z.B. "Streamer123"
    
    # 2. Validieren (ist alles OK?)
    if not gift_name or not user:
        logger.warning("Invalid gift data")
        return
    
    # 3. Trigger finden (gibt's eine Action für dieses Gift?)
    trigger = None
    if gift_name in VALID_ACTIONS:
        trigger = gift_name
    elif str(gift_id) in VALID_ACTIONS:
        trigger = str(gift_id)
    
    if not trigger:
        logger.debug(f"No action configured for gift: {gift_name}")
        return
    
    # 4. In Queue legen (nicht sofort ausführen!)
    for _ in range(repeat_count):
        MAIN_LOOP.call_soon_threadsafe(
            trigger_queue.put_nowait,
            (trigger, user)
        )
        logger.info(f"Gift queued: {gift_name} from {user}")
```

---

## Schritt 4: Fehlerbehandlung

Events können fehlschlagen – wir müssen es abfangen:

```python
@client.on(GiftEvent)
def on_gift(event: GiftEvent):
    try:
        # Dein Code hier
        gift_name = event.gift.name
        # ... Rest der Logik
        
    except AttributeError as e:
        logger.error(f"Gift data is incomplete: {e}")
    except Exception as e:
        logger.error(f"Unexpected error in on_gift: {e}", exc_info=True)
        # Wichtig: exc_info=True zeigt den kompletten Error-Stack
```

**Warum wichtig:**
- Event-Handler darf nicht das ganze Programm crashen
- Andere Events sollten weiterhin verarbeitet werden
- Fehler sollten geloggt werden (für Debugging)

---

## Die echte Implementierung (Production Code)

Der echte Code ist komplexer, weil er mit Edge Cases umgehen muss:

```python
@client.on(GiftEvent)
def on_gift(event: GiftEvent):
    try:
        # Combo-Gifts können mehrfach gesendet werden
        if event.gift.combo:
            # Prüfe auf "Streak" (wiederholte Combo)
            if getattr(event, 'streaking', False):
                try:
                    if event.streaking:
                        return  # Ignoriere Streak-Intermediate Events
                except AttributeError:
                    pass
            
            repeat_count = event.repeat_count
        else:
            repeat_count = 1  # Non-Combo = einmal
        
        # Gift-Daten sicher machen
        gift_name = sanitize_filename(event.gift.name)
        gift_id = str(event.gift.id)
        
        # Extra-Aktion ausführen (z.B. Sound)
        execute_gift_action(gift_id)
        
        # Trigger finden
        target = None
        if gift_name in valid_functions:
            target = gift_name
        elif gift_id in valid_functions:
            target = gift_id
        
        if not target:
            return
        
        username = get_safe_username(event.user)
        
        # Mehrfach in Queue legen (bei Combos)
        for _ in range(repeat_count):
            MAIN_LOOP.call_soon_threadsafe(
                trigger_queue.put_nowait,
                (target, username)
            )
    
    except Exception:
        logger.error("ERROR in on_gift handler:", exc_info=True)
```

---

## Die Komplexität verstehen

Der echte Code ist komplexer wegen:

| Komplexität | Grund |
|-------------|-------|
| `if event.gift.combo` | Manche Gifts können mehrfach wiederholt werden |
| `getattr(event, 'streaking', False)` | Attribute existieren vielleicht nicht – sicher prüfen |
| `sanitize_filename()` | Benutzernamen könnten spezielle Zeichen haben |
| `call_soon_threadsafe()` | Multiple Threads – müssen thread-safe kommunizieren |
| Try-Except | Events dürfen nicht das ganze System crashen |

---

## Zusammenfassung

Ein TikTok-Client-Handler:

1. ✓ Lauscht auf Events
2. ✓ Empfängt Event-Daten
3. ✓ Validiert die Daten
4. ✓ Findet passende Aktion
5. ✓ Legt in Queue (nicht sofort ausführen!)
6. ✓ Fehler abfangen (crasht nicht)

---

## Nächster Schritt

Jetzt verstehst du, wie Handler arbeiten. Der nächste Schritt ist verstehen, was im Event selbst steckt.

**→ [Event-System verstehen](./ch05-04-Understanding-the-Event-System.md)**

Dort schauen wir, welche Daten jedes Event hat und wie wir sie nutzen.