# Events empfangen

Events sind der zentrale Kommunikationsweg. Dieses Kapitel zeigt, wie dein Plugin TikTok-Events empfängt und wie der Event-Command-Mapper lose Kopplung ermöglicht.

## Zwei Wege zu deinem Plugin

| Weg | Quelle | Einrichtung | Handler-Name |
|-----|--------|-------------|--------------|
| **Event-Bridge** | TikTok-Events (Gift, Follow, Like, Comment, Join, Share) | `event_subscriptions` in `plugin.json` | `"tiktok_event"` |
| **Event-Command-Mapper** | Alle EventBus-Ereignisse (TikTok, Plugins, System) | `event_commands.yaml` | Beliebig, definiert in der YAML |

**Warum zwei Wege?** Die Event-Bridge ist der schnelle Einstieg für TikTok — Plugins erhalten TikTok-Events ohne zusätzliche Konfiguration, indem sie `event_subscriptions` setzen. Der Event-Command-Mapper (ECM) ist das flexible Werkzeug für lose Kopplung: Ein Event kann mehrere Plugins ansprechen, und Plugins müssen sich nicht kennen. In der Praxis nutzt ein TikTok-Plugin meist die Bridge; der ECM verbindet Plugins untereinander (z. B. Timer → WinCounter).

## Weg 1: Event-Bridge (TikTok-Events)

### Abonnement deklarieren

In der `plugin.json`:

```json
{
  "event_subscriptions": ["tiktok.gift", "tiktok.follow"]
}
```

Wildcard `"tiktok.*"` abonniert alle TikTok-Events. Wildcards funktionieren für jeden Namespace, z. B. `"timer.*"` oder `"*.milestone"`. Du kannst auch einzelne Events anderer Plugins abonnieren, z. B. `"timer.zero"` oder `"death-counter.milestone"`. Eigene Events haben den Namespace `plugin-name.ereignis` (siehe unten).

### Handler registrieren

```python
class MeinPlugin(BasePlugin):
    def __init__(self):
        super().__init__()
        self.register_handler("tiktok_event", self._on_event)

    def _on_event(self, args):
        event_type = args.get("event_type", "")
        user = args.get("user", "")
        data = args.get("data", {})
```

### Datenstruktur der Events

Die Event-Bridge liefert standardisierte Dictionaries:

```python
# tiktok.gift
{
    "event_type": "tiktok.gift",
    "user": "fan123",
    "data": {
        "gift_name": "Rose",
        "gift_id": "5655",
        "count": 1
    }
}

# tiktok.follow
{
    "event_type": "tiktok.follow",
    "user": "neuer_fan",
    "data": {}
}

# tiktok.comment
{
    "event_type": "tiktok.comment",
    "user": "kommentator",
    "data": {
        "comment": "Hallo zusammen!"
    }
}

# tiktok.like
{
    "event_type": "tiktok.like",
    "user": "fan",
    "data": {
        "delta": 3,    # Like-Inkrement seit letztem Event
        "total": 150   # Gesamtanzahl Likes (Session)
    }
}

# tiktok.join / tiktok.share
{
    "event_type": "tiktok.join",
    "user": "besucher",
    "data": {}
}
```

> [!NOTE]
> Die Event-Bridge veröffentlicht TikTok-Events auf dem EventBus, filtert sie im Bridge-Prozess (`_event_bridge_worker`) und enqueued den Befehl `"tiktok_event"` in der CommandQueue des API-Servers.

### Vollständiges Beispiel: Auf mehrere Event-Typen reagieren

```python
class ReaktionsPlugin(BasePlugin):
    def __init__(self):
        super().__init__()
        self.register_handler("tiktok_event", self._on_event)

    def _on_event(self, args):
        etype = args["event_type"]
        user = args["user"]

        if etype == "tiktok.gift":
            gname = args.get("data", {}).get("gift_name", "?")
            log.info(f"{user} sendete {gname}")

        elif etype == "tiktok.follow":
            log.info(f"Neuer Follower: {user}")

        elif etype == "tiktok.comment":
            log.info(f"Kommentar von {user}")
```

## Weg 2: Event-Command-Mapper

Der Event-Command-Mapper (ECM) läuft als Hintergrund-Task im API-Server. Er abonniert **alle** EventBus-Ereignisse und leitet sie basierend auf der `data/event_commands.yaml` an Plugin-Befehle weiter.

### Konfiguration

```yaml
# data/event_commands.yaml
event_commands:
  timer.zero:
    - target: win-counter
      command: add_win
      args: {amount: 1}
  minecraft.player_death:
    - target: timer
      command: pause
```

Wenn das Event `timer.zero` eintrifft, sendet der ECM den Befehl `add_win` mit den Argumenten an das Plugin `win-counter`.

### Im Plugin-Code

```python
# Event veröffentlichen (löst ECM aus)
self.api_post("/events", {
    "type": "timer.zero",
    "data": {}
})

# Auf ECM-Befehle reagieren
self.register_handler("add_win", self._on_add_win)

def _on_add_win(self, args):
    amount = args.get("amount", 1)
    self._wins += amount
```

### Vorteile

- **Keine Kopplung**: Das Timer-Plugin muss `win-counter` nicht kennen
- **Zentrale Konfiguration**: Alle Verknüpfungen in einer YAML-Datei
- **Flexibel**: Ein Event kann mehrere Befehle an mehrere Plugins auslösen
- **Zur Laufzeit änderbar**: Die Datei wird bei jeder Anfrage neu gelesen

## Eigene Events veröffentlichen

```python
self.api_post("/events", {
    "type": "mein-plugin.erreicht",
    "data": {"wert": 42}
})
```

Namenskonvention: `plugin-name.ereignis` (Namespace mit Punkt).

## Delivery-Garantien

| Aspekt | Garantie |
|--------|----------|
| Reihenfolge | Events eines Typs werden in Reihenfolge des Eintreffens verarbeitet |
| Zustellung | At-Most-Once nach Verarbeitung durch den Handler. Bei Netzwerkfehlern kann ein Event erneut angefragt werden. |
| Timeout | Polling-Timeout: 30s Server-Seite, 35s Client-Seite |

## Kommentar-Handler (`comment_handler`)

Plugins können auf TikTok-Kommentare mit einem bestimmten Prefix reagieren. Die Deklaration erfolgt in der `plugin.json`:

```json
{
  "comment_handler": {
    "prefix": "$",
    "enabled": true
  }
}
```

| Feld | Beschreibung |
|------|--------------|
| `prefix` | Zeichen, das einen Command markiert (z. B. `$` für `$song`). Standard: `"$"`. |
| `enabled` | Ob der Handler aktiv ist. Standard: `true`. |

Wenn ein TikTok-Kommentar mit dem Prefix beginnt (z. B. `$song`), leitet das System den Command an das Plugin weiter. Das Plugin empfängt den Event über `event_subscriptions: ["tiktok.comment"]` und kann den Prefix parsen.

> [!NOTE]
> Ohne `comment_handler`-Deklaration wird der Prefix nicht registriert. Das Plugin kann Kommentare zwar über `tiktok.comment` empfangen, aber das System erkennt den Command nicht als zu diesem Plugin gehörig.

## Häufige Fehler

| Problem | Ursache | Lösung |
|---------|---------|--------|
| Events kommen nicht an | `event_subscriptions` fehlt | In `plugin.json` ergänzen |
| Handler wird nicht aufgerufen | Handler-Name falsch | `register_handler("tiktok_event", ...)` prüfen |
| ECM reagiert nicht | `event_commands.yaml` fehlt/fehlerhaft | YAML-Syntax prüfen |
| Doppelte Verarbeitung | Keine Idempotenz im Handler | Nach Zustand prüfen vor Aktion |

## Nächstes Kapitel

Im nächsten Kapitel lernst du die [Plugin-übergreifende Kommunikation](./ch03-06-cross-plugin-communication.md).
