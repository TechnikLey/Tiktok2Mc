# Hook-API

Die Hook-API ist die Schnittstelle zwischen deinem Hook und dem Hauptsystem. Jeder Hook erhält ein API-Objekt in seiner `register()`-Funktion. Die API bietet die wichtigsten Funktionen für die Interaktion mit Minecraft und dem System.

## Einstiegspunkt

Jeder Hook muss eine `register(api)`-Funktion auf oberster Ebene definieren. Diese Funktion wird beim Start einmal aufgerufen:

```python
from core.hook_api import HookAPI

def register(api: HookAPI):
    # Hier registrierst du deine Aktionen
```

## Aktionen registrieren

Die wichtigste Funktion: Registriere einen Handler für einen `$`-Befehl.

`api.register_action(name, handler)`

- `name`: Der Name des `$`-Befehls (ohne `$`-Präfix)
- `handler`: Eine Funktion mit der Signatur `(user, trigger, context)`

```python
def register(api):
    def mein_handler(user, trigger, context):
        # user: TikTok-Benutzername
        # trigger: Name des $ -Befehls
        # context: Dictionary (für zukünftige Erweiterungen)
        pass

    api.register_action("mein-befehl", mein_handler)
```

## Minecraft-Befehle senden

`api.rcon_enqueue(commands)` sendet eine Liste von Minecraft-Befehlen an den RCON-Server:

```python
api.rcon_enqueue([
    "effect give @a minecraft:speed 10 2 true",
    f"say {user} hat Geschwindigkeit ausgelöst!",
])

# Auch Plugin-Befehle sind möglich:
api.rcon_enqueue([
    f"tnt 2 0.1 2 {user}",
])
```

Die Befehle werden der Reihe nach ausgeführt. Jeder Befehl ist ein vollständiger Minecraft-Befehl ohne führenden `/`.

## Trigger auslösen

`api.enqueue_trigger(action_name, user)` löst einen anderen Trigger aus der `actions.mca` aus:

```python
api.enqueue_trigger("follow", user)
```

Dies ermöglicht die Verkettung von Triggern. Der Trigger wird asynchron verarbeitet – der aktuelle Handler läuft zu Ende, bevor der neue Trigger ausgeführt wird.

> [!WARNING]
> Achte auf Endlosschleifen! Das System blockiert nach 3 Ketten-Schritten einen Trigger dauerhaft für die Sitzung.

## Overlay-Text senden

`api.send_overlay_text(title, subtitle, duration, overlay_name)` zeigt Text im Overlay an:

```python
api.send_overlay_text(
    title="Neuer Follower!",
    subtitle=f"{user} folgt jetzt!",
    duration=5
)
```

## Konfiguration lesen

`api.get_hook_config(name)` gibt die Konfiguration des Hooks zurück:

```python
cfg = api.get_hook_config("mein-hook")
modus = cfg.get("mode", "standard")
```

`api.config` gibt die globale Konfiguration (schreibgeschützt) zurück.

## Hilfsfunktionen

`api.log(msg)` gibt eine Nachricht in der Konsole aus:

```python
api.log("Hook wurde geladen")
```

`api.get_valid_functions()` gibt die Menge aller gültigen Trigger-Namen zurück:

```python
if "follow" in api.get_valid_functions():
    api.enqueue_trigger("follow", user)
```

> [!NOTE]
> Die hier dokumentierte API ist die stabile, öffentliche Schnittstelle. Interne Methoden sind nicht Teil dieser API.
