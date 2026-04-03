## Follow-Events

### Das Besondere an Follows: Einfach und direkt

Follows sind deutlich **einfacher** als Gifts, weil:

| Merkmal | Gifts | Follows |
|--------|-------|---------|
| **Mehrfach-Verarbeitung** | Combo möglich (5x, 10x, etc.) | Immer nur 1x |
| **Status-Updates** | Streaking: Mehrfach Notifications | Keine Notifications |
| **Trigger-Verwaltung** | Name UND ID möglich | Ein einziger Trigger: `"follow"` |
| **Fehler-Komplexität** | Hoch (Combos, Streaking, Race Conditions) | Niedrig (linearer Ablauf) |

**Das Gute:** Follow-Handler sind **perfekt zum Lernen**, weil sie die Grundstruktur zeigen ohne viel Komplexität.

---

### Follow-Event Struktur: Was können wir auslesen?

Ein `FollowEvent` enthält diese Informationen:

```python
event.user.nickname      # Zuschauer-Name: "anna_xyz"
event.user.user_id       # Zuschauer-ID (numerisch)

event.follow_user.nickname    # Der Account, der gefolgt wurde
event.follow_user.user_id     # ID des gefolgten Accounts

event.timestamp          # Zeitpunkt des Events
event.event_type         # Art des Events (normalerweise: "follow")
```

**In der Praxis:** Wir brauchen vor allem `event.user.nickname`, um zu wissen, **wer** gefolgt hat.

---

### Follow-Event Processing: Der 3-Schritt-Ablauf

Wenn ein Follow-Event ankommt, ist der Ablauf sehr einfach:

```
1. EVENT EMPFANGEN
   FollowEvent kommt an
   
2. BENUTZERNAMEN AUSLESEN & SANITIEREN
   username = get_safe_username(event.user)
   z.B.: "anna_xyz"
   
3. TRIGGER IN QUEUE LEGEN
   Es gibt nur einen Trigger: "follow"
   → Aktion ausführen oder ignorieren
```

**Visuell:**

```
Zuschauer folgt Stream
        ↓
TikTok sendet: FollowEvent
        ↓
[STEP 1] Event empfangen ✓
        ↓
[STEP 2] Username = "anna_xyz" ✓
        ↓
[STEP 3] Trigger "follow" definiert? 
         JA  → In Queue: ("follow", "anna_xyz")
         NEIN → Ignorieren
        ↓
Worker-Thread verarbeitet
```

---

### Follow-Daten Struktur im Code

Wenn du im Follow-Handler debuggen möchtest, kannst du diese Properties nutzen:

```python
@client.on(FollowEvent)
def on_follow(event: FollowEvent):
    # Wer hat gefolgt?
    follower_name = event.user.nickname
    follower_id = event.user.user_id
    
    # Wem wurde gefolgt?
    followed_user = event.follow_user.nickname
    followed_id = event.follow_user.user_id
    
    # Wann?
    timestamp = event.timestamp
    
    # Debuggen:
    print(f"{follower_name} folgt {followed_user} um {timestamp}")
```

**Hinweis:** In den meisten Fällen interessiert uns **nur** `event.user.nickname`, weil wir wissen, wer gefolgt hat.

---

### Einfache Fehlerbehandlung

Da Follow-Events einfach sind, brauchen wir weniger Fehlerbehandlung:

```python
try:
    username = get_safe_username(event.user)
    # ... Rest des Codes
except AttributeError:
    logger.error("Follow-Event ist unvollständig", exc_info=True)
except Exception as e:
    logger.error(f"Fehler im Follow-Handler: {e}", exc_info=True)
```

**Hauptrisiken:**

- `event.user` existiert nicht? → get_safe_username() schützt
- `get_safe_username()` gibt einen leeren String zurück? → OK, wird trotzdem gequeuet
- Queue ist voll? → Sehr selten, try-except reicht

---

### Praktisches Beispiel: Ein vollständiger Follow-Handler

Hier ist der Standard-Follow-Handler mit Best-Practices:

```python
@client.on(FollowEvent)
def on_follow(event: FollowEvent):
    """
    Verarbeitet Follow-Events von TikTok.
    - Einfache Struktur (keine Combos)
    - Arbeitet direkt mit Trigger 'follow'
    """
    try:
        # SCHRITT 1: Benutzernamen auslesen
        username = get_safe_username(event.user)
        
        # SCHRITT 2: Logging
        logger.info(f"Follow empfangen von: {username}")
        
        # SCHRITT 3: Prüfen, ob Follow-Trigger definiert ist
        if "follow" not in TRIGGERS:
            logger.warning("Kein 'follow' Trigger definiert, ignoriere Event")
            return
        
        # SCHRITT 4: Follow-Aktion in Queue legen
        try:
            MAIN_LOOP.call_soon_threadsafe(
                trigger_queue.put_nowait,
                ("follow", username)
            )
            logger.debug(f"✓ Follow-Action gequeuet für: {username}")
        except Exception as e:
            logger.error(
                f"Fehler beim Queuen von Follow-Aktion: {e}",
                exc_info=True
            )
    
    except AttributeError as e:
        logger.error(
            f"Follow-Event ist unvollständig: {e}",
            exc_info=True
        )
    except Exception as e:
        logger.error(
            f"Unerwarteter Fehler im Follow-Handler: {e}",
            exc_info=True
        )
```

**Was macht dieser Code?**

1. **Username auslesen & sanitieren** – Mit get_safe_username()
2. **Logging** – Wir sehen im Log, wer folgt
3. **Trigger prüfen** – Existiert der "follow" Trigger?
4. **Queuen** – Mit call_soon_threadsafe()
5. **Fehlerbehandlung** – Alles geschützt

---

### Noch einfacher: Minimales Beispiel

Der absolute Minimal-Handler (funktioniert auch!):

```python
@client.on(FollowEvent)
def on_follow(event: FollowEvent):
    username = get_safe_username(event.user)
    MAIN_LOOP.call_soon_threadsafe(
        trigger_queue.put_nowait,
        ("follow", username)
    )
```

**Das ist es!** Drei Zeilen, macht genau das Gleiche.

---

### Unterschied zu Gifts (Wiederholung zum Vergleich)

Um zu verstehen, warum Follow-Handler so einfach sind:

**Gift-Handler:**
```
if streaking: return           # ← Streaking prüfen
count = repeat_count or 1      # ← Mehrfach-Verarbeitung
for _ in range(count):         # ← Loop!
    queue.put(...)
```

**Follow-Handler:**
```
queue.put(...)                 # ← Direkt, kein Loop nötig!
```

Das ist der Hauptunterschied!

---

### Edge Cases (wenn was Schiefläuft)

Was kann bei Follows schiefgehen?

| Szenario | Folge | Lösung |
|----------|-------|--------|
| `event.user` ist None | AttributeError | get_safe_username() wirft Exception |
| Username ist leer string `""` | Wird so gequeuet | Normal, kein Problem |
| "follow" Trigger existiert nicht | Event ignoriert | return früh |
| Queue voll (extrem selten) | put_nowait() Exception | Try-except fängt es |
| TikTok sendet Follow 2x schnell | Zwei Events hintereinander | Beide werden verarbeitet (Gewollt!) |

**Fazit:** Follow-Handler sind **sehr robust** – es gibt wenig, was schiefgehen kann.

---

### Zusammenfassung & Nächster Schritt

**Was du jetzt weißt:**

| Konzept | Erklärung |
|---------|-----------|
| **Follow = Einfach** | Keine Combos, kein Streaking, nur 1 Trigger |
| **3-Schritt-Ablauf** | Username → Prüfen → Queuen |
| **Trigger "follow"** | Der einzige Trigger für Follow-Events |
| **Fehlerbehandlung** | Minimal nötig, get_safe_username() schützt viel |
| **Best Practice Pattern** | Gleich wie bei Gifts, nur viel kürzer |

**Was passiert NACH dem Follow-Handler?**

Die gequeuete "follow"-Action wird später vom Worker-Thread verarbeitet (z.B. Minecraft-Befehl ausführen).

→ [Nächstes Kapitel: Like-Events](ch05-07-Like-Events.md)

---

> [!TIP]
> Follow-Events sind perfekt zum Experimentieren. Versuch, den Minimal-Handler zu erweitern (z.B. spezielle Behandlung für bestimmte Usernames).