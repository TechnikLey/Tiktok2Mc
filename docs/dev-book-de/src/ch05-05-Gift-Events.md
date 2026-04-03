## Gift-Events

### Das Besondere an Gifts: Combos und Streaks

Gifts sind nicht einfach wie Follows. Ein Geschenk kann auf **drei unterschiedliche Weisen** ankommen:

| Situation | Was passiert | Wie oft wird der Handler aufgerufen? |
|-----------|--------------|--------------------------------------|
| **Einfaches Gift** | Zuschauer sendet Geschenk 1x | 1x (sofort) |
| **Combo-Gift** | Zuschauer sendet **gleiches** Geschenk mehrfach schnell hintereinander | Mehrere Male (mit `repeat_count`) |
| **Streaking** | TikTok sendet Notifications zum aktuellen Stand der Combo | Mehrfach (aber: wir wollen das SKIPPEN) |

Das ist wichtig zu verstehen, **bevor** wir Code schreiben:

```
Zuschauer sendet 5x Rose hintereinander:
  
  00:00 - Event: Gift='Rose', repeat_count=1, streaking=False
  00:01 - Event: Gift='Rose', repeat_count=2, streaking=False  
  00:02 - Event: Gift='Rose', repeat_count=3, streaking=False
  00:03 - Event: Gift='Rose', repeat_count=4, streaking=False
  00:04 - Event: Gift='Rose', repeat_count=5, streaking=True  ← Streak-Ende!
  
  TikTok sendet auch noch Status-Updates:
  
  00:01 - Event: Gift='Rose', repeat_count=2, streaking=True  ← IGNORIEREN!
  00:02 - Event: Gift='Rose', repeat_count=3, streaking=True  ← IGNORIEREN!
  00:03 - Event: Gift='Rose', repeat_count=4, streaking=True  ← IGNORIEREN!
```

**Warum ist das wichtig?** Wenn wir jeden Status-Update verarbeiten würden, würden wir die gleiche Action 3-5x zu viel queuen.



---

### Gift-Event Struktur: Was können wir alles aus einem Gift auslesen?

Ein `GiftEvent` enthält diese wichtigsten Informationen:

```python
event.gift.name          # Giftname: "Rose", "Diamond", etc.
event.gift.id            # Gift-ID: 1, 2, 3 (numerisch)
event.gift.combo         # Kann dieses Gift gecomboet werden? True/False

event.repeat_count       # Wie oft wurde das Gift insgesamt gesendet? 1, 2, 3, 4, 5...
event.streaking          # Ist das ein Status-Update einer laufenden Combo? True/False

event.user.nickname      # Zuschauer-Name: "anna_123"
event.user.user_id       # Zuschauer-ID (numerisch)

event.gift_type          # Art des Gifts (normalerweise: "gift")
event.description        # Detailbeschreibung (z.B. "Sent Rose x5")
```

**Die praktische Bedeutung:**

- Wir brauchen `repeat_count`, um zu **wissen, wie oft die Action ausgeführt werden soll**
- Wir brauchen `streaking`, um zu **wissen, ob wir dieses Event ignorieren sollen**
- Wir brauchen `gift.name` ODER `gift.id`, um zu **finden, welche Aktion passt**
- Wir brauchen `user.nickname`, um zu **speichern, wer das Geschenk sendete**

---

### Gift-Event Processing: Der 5-Schritt-Ablauf

Wenn ein Gift-Event ankommt, passiert folgendes:

```
1. ANKOMMEN
   Event kommt an → ist es streaking? JA → STOPP, ignorieren
   
2. ZÄHLEN
   Ist es ein Combo-Gift? JA → count = event.repeat_count
                           NEIN → count = 1
   
3. IDENTIFIZIEREN
   Giftname auslesen: "Rose"
   Sanitieren (sicher machen): "Rose" → OK
   Benutzername auslesen: "anna_123"
   
4. MATCHEN
   Passt "Rose" zu einer Aktion? Nachschauen in valid_functions
   Wenn ja → das ist unser `target`
   Wenn nein → Event ignorieren
   
5. QUEUEN
   for i in range(count):  # 5x, weil repeat_count=5
       Queue: (target, username)
       
   jetzt wird die Action asynchron verarbeitet
```

**Visuell:**

```
TikTok sendet: Gift Event (Rose, repeat_count=5, streaking=False)
    ↓
[STEP 1] streaking==False? ✓ Weitermachen
    ↓
[STEP 2] combo==True? repeat_count=5 → count=5
    ↓
[STEP 3] name="Rose", user="anna_123" (sanitized)
    ↓
[STEP 4] "Rose" in valid_functions? ✓ target="GIFT_ROSE"
    ↓
[STEP 5] 5x in Queue: ("GIFT_ROSE", "anna_123")
    ↓
Worker-Thread verarbeitet alle 5 nacheinander
```

---

### Spezial: Streaking-Flag

Das `streaking`-Flag ist wichtig, weil TikTok bei langen Combo-Sequenzen **Status-Updates** sendet:

```python
# Was TikTok sendet bei 5er-Combo:

Event 1: {gift: "Rose", repeat_count: 1, streaking: False}  ✓ Verarbeiten
Event 2: {gift: "Rose", repeat_count: 2, streaking: False}  ✓ Verarbeiten
Event 3: {gift: "Rose", repeat_count: 3, streaking: False}  ✓ Verarbeiten
Event 4: {gift: "Rose", repeat_count: 4, streaking: False}  ✓ Verarbeiten
Event 5: {gift: "Rose", repeat_count: 5, streaking: True}   SKIPPEN!
```

**Warum das `streaking=True` Event ignorieren?**

Wenn wir es verarbeiten würden, würden wir die Aktion 5x queuen = 5x falsch!
Das `streaking=True` Event ist nur eine Nachricht von TikTok: "Die Combo ist jetzt komplett".

**Wie stellen wir sicher?**

```python
if hasattr(event, 'streaking') and event.streaking:
    return  # Ignorieren, nicht verarbeiten!
```

---

### Fehlerbehandlung bei Gift-Events

Gift-Handler müssen robust sein, weil mehrere Dinge schiefgehen können:

| Problem | Was kann passieren? | Wie schützen wir uns? |
|---------|--------------------|--------------------|
| Event hat keine `gift`-Eigenschaft | AttributeError | `getattr()` mit Default-Wert |
| Event hat keine `user`-Eigenschaft | AttributeError | `get_safe_username()` prüft |
| Gift-Name/ID passt zu keiner Aktion | Gift wird ignoriert | `if not target: return` |
| Benutzername enthält ungültige Zeichen | Fehler beim Queuen | `sanitize_filename()` bereinigt |
| Queue ist voll (sehr selten) | put_nowait() Exception | Try-except um Queue-Operation |

**Lösung:** Alles in try-except wrappen:

```python
try:
    # Gift-Handler-Code hier
except AttributeError as e:
    logger.error(f"Gift-Event hat ungültige Struktur: {e}")
except Exception as e:
    logger.error(f"Fehler im Gift-Handler: {e}", exc_info=True)
```

---

### Praktisches Beispiel: Ein vollständiger Gift-Handler

Hier ist ein realer, funktionierender Gift-Handler mit allen Sicherheits-Features:

```python
@client.on(GiftEvent)
def on_gift(event: GiftEvent):
    """
    Verarbeitet Gift-Events von TikTok.
    - Handhabt Combos (mehrfach hintereinander)
    - Ignoriert Streaking-Events (Status-Updates)
    - Queued Aktionen für asynchrone Verarbeitung
    """
    try:
        # SCHRITT 1: Streaking-Event ignorieren?
        if hasattr(event, 'streaking') and event.streaking:
            logger.debug(f"Ignoriere Streaking-Event: {event.gift.name}")
            return
        
        # SCHRITT 2: Wie oft sollen wir die Aktion ausführen?
        if event.gift.combo:
            count = event.repeat_count  # z.B. 5 bei 5er-Combo
        else:
            count = 1  # Einzelnes Gift = 1x
        
        # SCHRITT 3: Gift-Daten sicher auslesen
        gift_name = event.gift.name  # "Rose", "Diamond", etc.
        gift_id = str(event.gift.id)  # "1", "2", etc.
        username = get_safe_username(event.user)  # "anna_123" (sanitized)
        
        logger.info(
            f"Gift empfangen: {gift_name} (ID: {gift_id}) "
            f"von {username} (x{count})"
        )
        
        # SCHRITT 4: Passendes Trigger finden
        # Zuerst nach Name suchen, dann nach ID
        target = None
        if gift_name in TRIGGERS:
            target = gift_name
        elif gift_id in TRIGGERS:
            target = gift_id
        
        if not target:
            logger.warning(f"Kein Trigger für Gift '{gift_name}' definiert")
            return
        
        # SCHRITT 5: Action in Queue legen (count-mal)
        for _ in range(count):
            try:
                MAIN_LOOP.call_soon_threadsafe(
                    trigger_queue.put_nowait,
                    (target, username)
                )
            except Exception as e:
                logger.error(
                    f"Fehler beim Queuen von Gift-Aktion: {e}",
                    exc_info=True
                )
        
        logger.debug(f"✓ {count}x Action '{target}' gequeuet")
        
    except AttributeError as e:
        logger.error(
            f"Gift-Event ist unvollständig (fehlende Property): {e}",
            exc_info=True
        )
    except Exception as e:
        logger.error(
            f"Unerwarteter Fehler im Gift-Handler: {e}",
            exc_info=True
        )
```

**Was macht dieser Code?**

1. **Streaking ignorieren** – Nur echte Gift-Events verarbeiten
2. **Count bestimmen** – 1x oder mehrfach?
3. **Daten auslesen** – Gift-Name, ID, Benutzername
4. **Logger-Info** – Sichtbarer Feedback für Debugging
5. **Trigger finden** – Nach Name, dann nach ID
6. **Queue-Operation** – Thread-sicher mit `call_soon_threadsafe`
7. **Fehlerbehandlung** – Alles ist geschützt mit try-except

---

### Noch einfacher: Minimales Beispiel

Wenn dir der obige Handler zu lang ist, hier ein minimales Beispiel, das auch funktioniert:

```python
@client.on(GiftEvent)
def on_gift(event: GiftEvent):
    # Streaking-Events ignorieren
    if getattr(event, 'streaking', False):
        return
    
    # Wie oft?
    count = event.repeat_count if event.gift.combo else 1
    
    # Welcher Trigger?
    target = event.gift.name  # oder: event.gift.id
    
    # Queuen (count-mal)
    for _ in range(count):
        MAIN_LOOP.call_soon_threadsafe(
            trigger_queue.put_nowait,
            (target, event.user.nickname)
        )
```

Das ist deutlich kürzer und macht das Gleiche – aber **ohne** explizite Fehlerbehandlung.

---

### Zusammenfassung & Nächster Schritt

**Was du jetzt weißt:**

| Konzept | Erklärung |
|---------|-----------|
| **Combo-Gifts** | Gleiche Gifts mehrfach = `repeat_count` erhöht sich |
| **Streaking** | TikTok sendet Status-Updates = wir ignorieren die |
| **Trigger-Matching** | Gift-Name oder ID → zu Aktion (TRIGGERS dictionary) |
| **Asynchrone Queue** | `call_soon_threadsafe` macht es thread-sicher |
| **Fehlerbehandlung** | Try-except schützt vor unerwarteten Strukturen |

**Was passiert NACH dem Gift-Handler?**

Die gequeuete Action wird später vom Worker-Thread verarbeitet.

→ [Nächstes Kapitel: Follow-Events](ch05-06-Follow-Events.md)

---

> [!TIP]
> Wenn du deinen eigenen Gift-Handler schreiben willst, verwende das **Minimale Beispiel** oben und bau dann je nach Bedarf Fehlerbehandlung ein.