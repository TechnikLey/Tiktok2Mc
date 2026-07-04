# Events & Subscriptions

Plugins können auf Ereignisse aus dem gesamten System reagieren. Es gibt zwei Mechanismen: die deklarative Event-Bridge und den Event-Command-Mapper.

## Event-Bridge

Die Event-Bridge ist eine Komponente im Bridge-Prozess, die TikTok-Events an Plugins verteilt. Sie empfängt Events aus dem TikTokLive-Client, filtert sie anhand der `event_subscriptions` aus der `plugin.json` jedes Plugins und leitet sie per HTTP an die entsprechenden Plugins weiter. Die Event-Bridge ist der primäre Weg für Plugins, TikTok-Events zu empfangen.

### Events abonnieren

Deklariere in der `plugin.json`, welche Events du empfangen möchtest:

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

### Events empfangen

Registriere einen Handler für den Befehl `tiktok_event`:

```python
class MeinPlugin(BasePlugin):
    def __init__(self):
        super().__init__()
        self.register_handler("tiktok_event", self._on_event)

    def _on_event(self, args):
        event_type = args.get("event_type", "")   # z. B. "tiktok.gift"
        user = args.get("user", "")                # TikTok-Benutzername
        data = args.get("data", {})                # Event-Daten
```

### Unterstützte Event-Typen

| Event | Beschreibung |
|---|---|
| `tiktok.gift` | Ein Geschenk wurde gesendet |
| `tiktok.follow` | Ein neuer Follower |
| `tiktok.like` | Ein Like (mit Throttling) |
| `tiktok.join` | Ein Benutzer ist dem Live beigetreten |
| `tiktok.comment` | Ein Kommentar wurde geschrieben |
| `tiktok.share` | Der Live wurde geteilt |

## Event-Command-Mapper

Der Event-Command-Mapper ist ein separates System, das EventBus-Ereignisse auf Plugin-Befehle abbildet. Die Konfiguration erfolgt in `event_commands.yaml`:

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

Wenn das Event `timer.zero` eintrifft, sendet der Mapper den Befehl `add_win` mit den angegebenen Argumenten an das Plugin `win-counter`.

### Vorteile

- **Null Kopplung**: Weder das sendende noch das empfangende Plugin müssen voneinander wissen.
- **Deklarativ**: Die Verknüpfungen sind in einer YAML-Datei definiert, nicht im Code.
- **Flexibel**: Ein Event kann mehrere Befehle an mehrere Plugins auslösen.

## Eigene Events veröffentlichen

Plugins können eigene Events an den EventBus senden:

```python
self.api_post("/events", {
    "type": "mein-plugin.ereignis",
    "data": {"wert": 42, "benutzer": "max"}
})
```

Andere Plugins oder der Event-Command-Mapper können auf diese Events reagieren.

## Event-Daten

Jedes Event enthält:

| Feld | Beschreibung |
|---|---|
| `type` | Der Event-Typ (z. B. `tiktok.gift`) |
| `data` | Ein Dictionary mit Event-spezifischen Daten |
| `timestamp` | Zeitstempel des Events (wird vom System gesetzt) |
