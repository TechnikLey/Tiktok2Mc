# Events & Subscriptions

Events sind das zentrale Kommunikationsmittel in TikTok2Mc. Sie transportieren Nachrichten vom TikTok-Live-Stream, von Plugins und vom System selbst. Dieses Kapitel erklärt, wie Events fließen, wie du sie empfängst und wie du eigene veröffentlichst.

## Überblick: Zwei Event-Mechanismen

Es gibt zwei Wege, wie Events dein Plugin erreichen:

| Mechanismus | Quelle | Konfiguration | Empfang |
|---|---|---|---|
| **Event-Bridge** | TikTok-Events (Gift, Follow, Like, etc.) | `event_subscriptions` in `plugin.json` | `register_handler("tiktok_event", ...)` |
| **Event-Command-Mapper** | Alle EventBus-Ereignisse (TikTok, Plugins, System) | `event_commands.yaml` | `register_handler("<befehl>", ...)` |

Die Event-Bridge ist speziell für TikTok-Events optimiert. Der Event-Command-Mapper kann beliebige Events auf Plugin-Befehle abbilden – auch solche, die von anderen Plugins ausgelöst wurden.

## Event-Bridge: TikTok-Events empfangen

### 1. Abonnement deklarieren

In der `plugin.json` gibst du an, welche TikTok-Events dich interessieren:

```json
{
  "event_subscriptions": ["tiktok.gift", "tiktok.follow"]
}
```

Wildcards sind möglich:

```json
{
  "event_subscriptions": ["tiktok.*"]
}
```

Das abonniert **alle** TikTok-Events (`gift`, `follow`, `like`, `join`, `comment`, `share`).

### 2. Handler registrieren

Im Plugin-Code registrierst du einen Handler für den Befehl `"tiktok_event"`:

```python
class MeinPlugin(BasePlugin):
    def __init__(self):
        super().__init__()
        self.register_handler("tiktok_event", self._on_tiktok_event)

    def _on_tiktok_event(self, args):
        event_type = args.get("event_type", "")   # z. B. "tiktok.gift"
        user = args.get("user", "")                # TikTok-Benutzername
        data = args.get("data", {})                # Event-Daten (variiert pro Typ)
```

### 3. Die Event-Daten im Detail

Jeder TikTok-Event liefert ein Dictionary mit diesen Feldern:

```python
{
    "event_type": "tiktok.gift",      # oder tiktok.follow, tiktok.like, ...
    "user": "tiktok_nutzer",          # TikTok-Benutzername
    "data": {                         # Event-spezifisch (siehe unten)
        # ...
    }
}
```

### TikTok-Event-Typen und ihre Daten

#### `tiktok.gift`

```python
{
    "event_type": "tiktok.gift",
    "user": "fan123",
    "data": {
        "gift_id": 5655,               # Gift-ID aus der TikTok-Gift-Liste
        "gift_name": "Rose",           # Anzeigename des Geschenks
        "diamonds": 1,                 # Diamanten-Wert
        "repeat_count": 5,             # Wie oft wiederholt
        "repeat_end": true             # Letzter Repeat dieses Bursts
    }
}
```

#### `tiktok.follow`

```python
{
    "event_type": "tiktok.follow",
    "user": "neuer_fan",
    "data": {
        "follow_count": 1234           # Aktuelle Follower-Anzahl
    }
}
```

#### `tiktok.comment`

```python
{
    "event_type": "tiktok.comment",
    "user": "kommentator",
    "data": {
        "comment": "$superjump",       # Der Kommentartext
        "comment_id": "abc123"
    }
}
```

#### `tiktok.like`, `tiktok.join`, `tiktok.share`

```python
{
    "event_type": "tiktok.like",       # oder tiktok.join, tiktok.share
    "user": "benutzer",
    "data": {
        "like_count": 42               # Bei like: Gesamtanzahl (nicht inkrementell)
        # Bei join/share: keine zusätzlichen Felder
    }
}
```

### Vollständiges Beispiel: Auf verschiedene Events reagieren

```python
class ReaktionsPlugin(BasePlugin):
    def __init__(self):
        super().__init__()
        self.register_handler("tiktok_event", self._on_event)
        self._gift_count = 0

    def _on_event(self, args):
        event_type = args["event_type"]
        user = args["user"]
        data = args.get("data", {})

        if event_type == "tiktok.gift":
            self._gift_count += 1
            name = data.get("gift_name", "unbekannt")
            log.info(f"{user} sendete {name} (Geschenk #{self._gift_count})")

        elif event_type == "tiktok.follow":
            log.info(f"Neuer Follower: {user}")

        elif event_type == "tiktok.comment":
            text = data.get("comment", "")
            log.info(f"{user} schrieb: {text}")
```

## Wie die Event-Bridge intern arbeitet

```
TikTokLive-Client (main.py)
       │
       ▼ Event empfangen (z. B. FollowEvent)
       │
_publish_tiktok_event(event_type, user, data)
       │
       ▼ event_bus.publish(f"tiktok.{type}", {user, data})
       │
EventBus (In-Memory Pub/Sub, im Bridge-Prozess)
       │
       ▼
_event_bridge_worker (Hintergrund-Task)
  │
  ├─ Prüft: Abonniert Plugin A "tiktok.follow"?  → Ja → enqueue("tiktok_event", args) für Plugin A
  ├─ Prüft: Abonniert Plugin B "tiktok.*"?       → Ja → enqueue("tiktok_event", args) für Plugin B
  └─ Prüft: Abonniert Plugin C "tiktok.gift"?    → Nein → überspringen
       │
       ▼
CommandQueue (API-Server)
       │
       ▼ Polling-Thread von Plugin A holt Befehl ab
       │
Handler self._on_tiktok_event(args) wird aufgerufen
```

**Wichtig**: Die Event-Bridge läuft im **Bridge-Prozess** (`main.py`), nicht im API-Server. Sie enqueued Befehle in die CommandQueue des API-Servers über eine HTTP-Schnittstelle oder direkte Funktionsaufrufe (beide laufen im selben Prozess).

## Event-Command-Mapper

Der Event-Command-Mapper ist ein separates System, das Events aus dem EventBus auf Plugin-Befehle abbildet. Er ist **nicht** auf TikTok-Events beschränkt – er reagiert auf **alle** Event-Typen, auch solche, die von Plugins veröffentlicht wurden.

### Konfiguration

Definiere in `event_commands.yaml`:

```yaml
event_commands:
  timer.zero:
    - target: win-counter
      command: add_win
      args: {amount: 1}
  minecraft.player_death:
    - target: timer
      command: pause
```

Wenn das Event `timer.zero` eintrifft, sendet der Mapper den Befehl `add_win` mit `{amount: 1}` an das Plugin `win-counter`.

### Vorteile gegenüber direkter Kommunikation

1. **Null Kopplung**: Das Timer-Plugin muss `win-counter` nicht kennen. Es veröffentlicht einfach `timer.zero`.
2. **Zentrale Konfiguration**: Alle Verknüpfungen stehen in einer YAML-Datei, nicht verstreut im Code.
3. **Flexibel**: Ein Event kann mehrere Befehle an mehrere Plugins auslösen.
4. **Konfigurierbar ohne Neustart**: Die Datei kann zur Laufzeit neu geladen werden.

### Beispiel: Event-Kaskade

Ein TikTok-Gift startet einen Timer, und wenn der Timer abläuft, gewinnt ein Spieler:

```
tiktok.gift → Timer (start, 60s) → timer.zero → Win-Counter (add_win)
```

Konfiguration:
```yaml
event_commands:
  tiktok.gift:
    - target: timer
      command: start
      args: {duration: 60}
  timer.zero:
    - target: win-counter
      command: add_win
      args: {amount: 1}
```

**Nichts** davon muss im Code eines Plugins hartcodiert werden – nur die Handler `start`, `add_win` müssen existieren.

## Eigene Events veröffentlichen

Jedes Plugin kann eigene Events an den EventBus senden:

```python
self.api_post("/events", {
    "type": "mein-plugin.erreicht",
    "data": {"wert": 42, "benutzer": "max"}
})
```

Der API-Endpunkt: `POST /api/v1/events`. Das Event wird im EventBus veröffentlicht und an alle Abonnenten verteilt: Event-Command-Mapper, Event-Bridge, SSE-Clients.

### Namenskonventionen für Event-Typen

- Verwende einen **Namensraum** mit deinem Plugin-Namen: `mein-plugin.ereignis`
- Verwende Punkte für Hierarchien: `timer.zero`, `death.milestone`, `spotify.track_changed`
- Vermeide generische Namen wie `update` oder `event` ohne Prefix

### Wann eigene Events veröffentlichen?

| Situation | Event-Typ | Empfänger |
|---|---|---|
| Ein Meilenstein wurde erreicht | `death.milestone` | Event-Command-Mapper → anderes Plugin |
| Ein Timer ist abgelaufen | `timer.zero` | Event-Command-Mapper → Win-Counter |
| Ein externer Zustand hat sich geändert | `spotify.track_changed` | Andere Plugins, Overlay |
| Ein interner Zähler wurde aktualisiert | `mein-plugin.aktualisiert` | SSE-Clients (Browser) |

## Event-Daten-Garantien

| Aspekt | Garantie |
|---|---|
| Reihenfolge | Events eines Typs werden in der Reihenfolge ihres Eintreffens verarbeitet |
| Zustellung | Mindestens einmal (At-Least-Once). Ein Plugin kann dasselbe Event zweimal erhalten, wenn der Polling-Request fehlschlägt und wiederholt wird. |
| Timeout | Der Polling-Request hat ein 35-Sekunden-Timeout. Danach wird automatisch neu gefragt. |

## Häufige Fehler

| Fehler | Ursache | Lösung |
|---|---|---|
| Handler wird nie aufgerufen | `event_subscriptions` fehlt in `plugin.json` | Füge `["tiktok.follow"]` oder `["tiktok.*"]` hinzu |
| Nur manche Events kommen an | Wildcard `tiktok.*` vergessen, einzelne Typen nicht gelistet | Nutze `tiktok.*` oder liste alle benötigten Typen |
| `api_post("/events")` gibt `False` | API-Server nicht erreichbar | Prüfe, ob `python run.py` läuft |
| Event wird doppelt verarbeitet | Kein Idempotenz-Check im Handler | Prüfe, ob die Aktion bereits ausgeführt wurde |
| Event-Command-Mapper reagiert nicht | `event_commands.yaml`-Eintrag fehlt oder vertippt | Prüfe die YAML-Syntax und den Event-Typ |

## Wann welcher Mechanismus?

| Situation | Mechanismus |
|---|---|
| Ein Plugin möchte auf TikTok-Events reagieren | Event-Bridge + `tiktok_event`-Handler |
| Ein Event soll einen Befehl an ein anderes Plugin senden | Event-Command-Mapper + `event_commands.yaml` |
| Ein Plugin möchte seinen Zustand bekannt geben | Eigenes Event via `api_post("/events", ...)` |
| Ein Event soll mehrere Aktionen auslösen | Event-Command-Mapper mit mehreren Targets |
| Events sollen ohne Code-Änderung umleitbar sein | Event-Command-Mapper |

Die Event-Bridge und der Event-Command-Mapper schließen sich nicht aus – du kannst beide parallel nutzen. Die Event-Bridge liefert TikTok-Rohdaten, der Event-Command-Mapper ermöglicht lose gekoppelte Workflows.
