## Die Datei `main.py`

`main.py` ist das **Herzstück** deines Projekts. Sie ist dafür verantwortlich, mit TikTok verbunden zu bleiben und alle Events zu empfangen.

---

## Was macht main.py?

Wenn du das Programm startest, macht `main.py` diese Schritte (vereinfacht):

```
1. Konfiguration laden (config.yaml)
     ↓
2. TikTok-Client einrichten
     ↓
3. Event-Handler registrieren ("Höre auf Gifts, Follows, Likes")
     ↓
4. Mit TikTok verbinden (bleibt verbunden)
     ↓
5. Events empfangen (kontinuierlich)
     ↓
6. Events verarbeiten & in Queue legen
     ↓
7. [Während Schritt 6 läuft: Main-Loop verarbeitet Queue]
```

Das ist **nicht linear**. Schritte 5, 6 und 7 laufen **gleichzeitig** (parallel) ab.

---

## Aufbau von main.py (auf hoher Ebene)

```python
# 1. IMPORTE
from TikTokLive import TikTokLiveClient
from TikTokLive.events import GiftEvent, FollowEvent, LikeEvent
from core.validator import validate_file, print_diagnostics
from core.paths import get_base_dir

# 2. GLOBALE VARIABLEN
MAIN_LOOP = ... # Referenz zur Hauptschleife
trigger_queue = Queue()  # Warteschlange der Trigger
like_queue = Queue()     # Warteschlange für Likes

# 3. FUNKTIONEN ZUM ERSTELLEN DES CLIENTS
def create_client(user):
    client = TikTokLiveClient(unique_id=user)
    
    @client.on(GiftEvent)
    def on_gift(event):
        # Reagiere auf Gift
        pass
    
    # Ähnlich: on_follow, on_like, etc.
    return client

# 4. HAUPTFUNKTION
def main():
    # Lade Config
    cfg = load_config(...)
    
    # Starte Client
    client = create_client(cfg["tiktok_user"])
    
    # Starte andere Services (Server, GUI, Plugins)
    # ...
    
    # Hauptloop (verarbeitet Queue)
    while True:
        event = trigger_queue.get()  # Nächsten Event holen
        process_trigger(event)       # Verarbeiten
```

---

## Die Rolle von Importe

Am Anfang von `main.py` siehst du:

```python
from TikTokLive import TikTokLiveClient
from TikTokLive.events import GiftEvent, FollowEvent, ConnectEvent, LikeEvent
```

Das heißt:

- **TikTokLiveClient**: Ein Objekt, das die Verbindung zu TikTok herstellt
- **GiftEvent**: Wird ausgelöst, wenn ein Gift empfangen wird
- **FollowEvent**: Wird ausgelöst, wenn jemand folgt
- **LikeEvent**: Wird ausgelöst, wenn Likes eintreffen

Diese werden später verwendet, um Event-Handler zu registrieren.

Weitere Importe:

```python
from core.validator import validate_file, print_diagnostics
from core.paths import get_base_dir
```

Das sind **Kern-Module** (vom Projekt selbst), nicht externe Bibliotheken.

---

## Schritt 1: Konfiguration laden

```python
CONFIG_FILE = get_root_dir() / "config" / "config.yaml"

try:
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
except Exception as e:
    print(f"FEHLER: Config konnte nicht geladen werden: {e}")
    sys.exit(1)  # Programm beenden
```

Das liest die `config.yaml`:

```yaml
tiktok_user: "eintiktoker"
Timer:
  Enable: true
  StartTime: 10
```

Wenn das fehlschlägt, bricht das Programm ab (weil es ohne Config nicht funktioniert).

---

## Schritt 2 & 3: Client erstellen & Handler registrieren

```python
def create_client(user):
    """Erstelle einen TikTok-Live-Client für den angegebenen User"""
    client = TikTokLiveClient(unique_id=user)
    
    # Jetzt registrieren wir Event-Handler
    # Handler = "Funktionen, die ausgeführt werden, wenn ein Event kommt"
    
    @client.on(GiftEvent)
    def on_gift(event: GiftEvent):
        # Diese Funktion wird JEDES MAL aufgerufen, wenn ein Gift kommt
        pass  # Logik kommt später
    
    @client.on(FollowEvent)
    def on_follow(event: FollowEvent):
        # Diese Funktion wird aufgerufen, wenn jemand folgt
        pass
    
    @client.on(LikeEvent)
    def on_like(event: LikeEvent):
        # Diese Funktion wird aufgerufen, wenn Likes eintreffen
        pass
    
    return client  # Gib den konfigurierten Client zurück
```

Das `@client.on(...)` ist ein **Dekorator** – eine Python-Funktion, die sagt: "Rufe diese Funktion auf, wenn dieses Event kommt".

---

## Schritt 4: Mit TikTok verbinden

```python
client = create_client(cfg["tiktok_user"])

# Verbindung starten (asynchron)
asyncio.run(client.connect())
```

Das verbindet sich mit dem TikTok-Stream und **bleibt verbunden**. Wenn ein Event kommt, ruft der Client automatisch den entsprechenden Handler auf.

---

## Warum ist main.py komplex?

Wenn du die echte `main.py` öffnest, siehst du viel mehr Code als hier erklärt:

```python
# Echte main.py hat auch:
- Error-Handling (was wenn Fehler?)
- Combo-Gifts (wiederholte Gifts)
- Race Conditions (Multi-Threading)
- Streams (VideoEvents)
- und vieles mehr...
```

Das macht den Code kompliziert. Aber **die Kernidee bleibt gleich**:

1. Client erstellen
2. Handler registrieren  
3. Verbinden
4. Events verarbeiten

---

## Was kommt in den Event-Handlern?

Die eigentliche **Magie** passiert in den Event-Handlern:

```python
@client.on(GiftEvent)
def on_gift(event: GiftEvent):
    # 1. Gift-Details auslesen
    gift_name = event.gift.name
    user = event.user.nickname
    
    # 2. Prüfen, ob diese Gift konfiguriert ist
    if gift_name in valid_functions:
        # 3. Trigger in Warteschlange legen
        MAIN_LOOP.call_soon_threadsafe(
            trigger_queue.put_nowait,
            (gift_name, user)
        )
```

Aber das wird später ausführlich besprochen.

---

## Die Rolle des Hauptprogramms

`main.py` ist **nicht** die einzige Datei, die läuft. Daneben gibt es auch:

- **server.py**: Startet den Minecraft-Server (Java-Subprocess, RCON-Konfiguration, server.properties)
- **registry.py**: Lädt und startet alle Plugins
- **gui.py**: Zeigt ein Admin-Interface

---

## Zusammenfassung

`main.py` macht:

✓ Konfiguration laden  
✓ TikTok-Client erstellen  
✓ Event-Handler registrieren  
✓ Mit TikTok verbinden  
✓ Events empfangen & verarbeiten  
✓ In Warteschlange legen  

Alles läuft **parallel** ab – nicht nacheinander.

---

## Nächster Schritt

Jetzt verstehst du die **Struktur**. Der nächste Schritt ist es, die **Importe** genauer zu verstehen.

**→ [Importe](./ch05-02-Imports.md)**

Dort wirst du sehen, was mit den importieren Modulen angestellt wird.