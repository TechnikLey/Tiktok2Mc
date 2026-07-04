# Hook-API

Die Hook-API ist die Schnittstelle zwischen deinem Hook und dem Hauptsystem. Du erhältst ein API-Objekt in der `register()`-Funktion. Dieses Kapitel beschreibt jede Methode mit ihrer Funktionsweise, typischen Anwendungsfällen und häufigen Fehlern.

## Einstiegspunkt: Die register()-Funktion

Jeder Hook **muss** eine `register(api)`-Funktion auf oberster Ebene definieren. Ohne sie wird der Hook nicht geladen.

```python
from core.hook_api import HookAPI

def register(api: HookAPI):
    """Wird vom Hook-Loader beim Start einmal aufgerufen."""
    pass
```

**Was passiert beim Laden?** Der Hook-Loader in `hook_loader.py`:

1. Prüft, ob `main.py` existiert
2. Analysiert den Python-Code auf verbotene Imports (siehe [Import-Beschränkungen](./ch04-06-import-restrictions.md))
3. Importiert `main.py` dynamisch mit `importlib`
4. Prüft, ob `register` existiert und aufrufbar ist – sonst Fehler `HOOK_0007`
5. Ruft `register(api)` auf
6. Fängt Fehler innerhalb von `register()` – Fehler `HOOK_0005`

Der `api`-Parameter ist eine `HookAPI`-Instanz, die direkten Zugriff auf den Bridge-Prozess gewährt: RCON-Warteschlange, Trigger-Warteschlange, Overlay-System und Hook-Konfiguration.

## Aktionen registrieren

`api.register_action(name, handler)` ist die wichtigste Methode. Sie registriert eine Handler-Funktion für einen `$`-Befehl.

```python
api.register_action("superjump", superjump)
```

**Signatur**: `register_action(name: str, fn: Callable) -> None`

**Parameter**:
- `name`: Der Name des `$`-Befehls (ohne `$`-Präfix). Muss dem Namen in der `actions.mca` entsprechen.
- `fn`: Eine Funktion mit der Signatur `(user, trigger, context) -> None`

**Interne Funktionsweise**: Der Name und die Funktion werden im **globalen** `HOOK_ACTIONS`-Dictionary gespeichert (Modul-Level, für den gesamten Bridge-Prozess sichtbar). Wenn später ein TikTok-Event den Trigger auslöst, sucht `execute_global_command()` in diesem Dictionary nach dem Namen.

**Verhalten bei Duplikaten**: Der erste registrierte Handler gewinnt. Ein zweiter `register_action`-Aufruf mit demselben Namen wird mit einer Warnung ignoriert:
```
[HOOK] Duplicate action 'superjump' — first registration kept.
```

**Ein Hook, mehrere Aktionen**:

```python
def register(api):
    def begruessung(user, trigger, context):
        api.rcon_enqueue([f"say Hallo {user}!"])

    def verabschiedung(user, trigger, context):
        api.rcon_enqueue([f"say Tschüss {user}!"])

    api.register_action("begruessung", begruessung)
    api.register_action("verabschiedung", verabschiedung)
```

In der `actions.mca`:
```
follow: $begruessung
like: $verabschiedung
```

## Minecraft-Befehle senden

`api.rcon_enqueue(commands)` fügt eine Liste von Minecraft-Befehlen in die RCON-Warteschlange ein.

```python
api.rcon_enqueue([
    "effect give @a minecraft:speed 10 2 true",
    f"say {user} hat Geschwindigkeit ausgelöst!",
])
```

**Signatur**: `rcon_enqueue(commands: list[str]) -> None`

**Verhalten**:
- Die Befehle werden **der Reihe nach** an den Minecraft-Server gesendet
- Jeder Befehl ist ein vollständiger Minecraft-Befehl **ohne** führenden `/`
- Die Ausführung ist **asynchron** – `rcon_enqueue` kehrt sofort zurück, die Befehle werden im Hintergrund gesendet
- Fehlgeschlagene Befehle werden automatisch wiederholt (bis zu 3 Versuche)
- Bei Verbindungsabriss wird automatisch neu verbunden

**Plugin-Befehle** funktionieren genauso wie Vanilla-Befehle:

```python
api.rcon_enqueue([
    f"tnt 2 0.1 2 {user}",           # Plugin-Befehl (z. B. von TNT-PLUGIN)
    f"shop open {user}",              # Ein weiterer Plugin-Befehl
    "say Willkommen im Server!",      # Vanilla-Befehl
])
```

**Wichtige Einschränkung**: Die RCON-Warteschlange hat eine maximale Befehllänge von ~1400 Zeichen. Sehr viele Befehle hintereinander können zu Verzögerungen führen.

## Trigger auslösen

`api.enqueue_trigger(action_name, user)` löst einen anderen Trigger aus der `actions.mca` aus.

```python
api.enqueue_trigger("follow", user)
```

**Signatur**: `enqueue_trigger(action_name: str, user: str = "hook") -> None`

**Wozu?** Du kannst innerhalb eines Handlers einen zweiten Trigger auslösen. Das ermöglicht die Verkettung von Aktionen:

```python
def register(api):
    def geschenk(user, trigger, context):
        # Zuerst eine Minecraft-Nachricht senden
        api.rcon_enqueue([f"say Danke {user} für das Geschenk!"])
        # Dann den follow-Trigger auslösen (alle follow-Aktionen werden ausgeführt)
        api.enqueue_trigger("follow", user)

    api.register_action("geschenk", geschenk)
```

**Schutz vor Endlosschleifen**: Das System zählt die Ketten-Tiefe. Bei mehr als 3 aufeinanderfolgenden `enqueue_trigger`-Aufrufen wird der auslösende Trigger **dauerhaft für die gesamte Sitzung** gesperrt:

```
[HOOK] enqueue_trigger() blocked — chain depth exceeds maximum (3)
```

Rufe daher niemals `enqueue_trigger` mit dem Namen des aktuellen Triggers auf.

## Overlay-Text senden

`api.send_overlay_text(title, subtitle, duration, overlay_name)` zeigt Text im Overlay an.

```python
api.send_overlay_text(
    title="Neuer Follower!",
    subtitle=f"{user} folgt jetzt!",
    duration=5
)
```

**Signatur**: `send_overlay_text(title: str, subtitle: str = "", duration: int = 3, overlay_name: str = "default") -> bool`

**Parameter**:
| Parameter | Beschreibung | Standard |
|---|---|---|
| `title` | Haupttext (wird groß angezeigt) | – |
| `subtitle` | Kleinerer Text unter dem Titel | `""` |
| `duration` | Anzeigedauer in Sekunden | `3` |
| `overlay_name` | Name des Overlay-Fensters (für mehrere Overlays) | `"default"` |

**Rückgabewert**: `True` bei Erfolg, `False` bei Fehler (z. B. wenn der Overlay-Dienst nicht erreichbar ist).

## Konfiguration lesen

`api.get_hook_config(name)` gibt die Konfiguration eines Hooks zurück.

```python
cfg = api.get_hook_config("mein-hook")
modus = cfg.get("mode", "standard")
triggers = cfg.get("triggers", [])
```

**Signatur**: `get_hook_config(name: str) -> dict`

**Verhalten**:
- Gibt ein Dictionary mit der Konfiguration aus der `config.yaml` des Hooks zurück
- Wenn der Hook keine `config.yaml` hat oder das Schema kein `config_schema` definiert: leeres Dictionary `{}`
- Die Konfiguration wird einmal beim Start geladen und gilt für die gesamte Sitzung
- Bei Änderungen an der `config.yaml` ist ein Neustart erforderlich

**Die globale Konfiguration** lesen:

```python
global_cfg = api.config  # Schreibgeschützt, Deep Copy
rcon_host = global_cfg.get("rcon", {}).get("host", "localhost")
```

## Hilfsfunktionen

### `api.log(msg)`

Protokolliert eine Nachricht mit dem Präfix `[HOOK]` in der System-Konsole:

```python
api.log(f"Hook wurde geladen: {name}")
```

**Signatur**: `log(msg: str) -> None`

**Wann verwenden?** Für Entwicklungs-Logs und Debugging. In Produktion sollten wichtige Ereignisse über `api.rcon_enqueue` oder `api.send_overlay_text` kommuniziert werden.

### `api.get_valid_functions()`

Gibt die Menge aller gültigen Trigger-Namen zurück:

```python
if "follow" in api.get_valid_functions():
    api.enqueue_trigger("follow", user)
```

**Signatur**: `get_valid_functions() -> set[str]`

**Wozu?** Prüfe vor `enqueue_trigger`, ob der Trigger existiert. Das verhindert stille Fehler, wenn ein Trigger umbenannt oder entfernt wurde.

## Vollständiges Beispiel: Ein vielseitiger Hook

```python
from core.hook_api import HookAPI

def register(api: HookAPI):
    """Registriert mehrere Aktionen für verschiedene Events."""

    # ── Aktion: Power-up ──────────────────────────────────
    def power_up(user, trigger, context):
        effekte = {
            "superjump": "minecraft:jump_boost",
            "superrun": "minecraft:speed",
            "superheal": "minecraft:regeneration",
        }
        effekt = effekte.get(trigger)
        if effekt:
            api.rcon_enqueue([
                f"effect give @a {effekt} 10 5 true",
                f"say {user} hat {effekt} ausgelöst!"
            ])
            api.send_overlay_text(
                title="Power-Up!",
                subtitle=f"{user} aktivierte {trigger}",
                duration=3
            )

    api.register_action("superjump", power_up)
    api.register_action("superrun", power_up)
    api.register_action("superheal", power_up)

    # ── Aktion: Dankeschön ────────────────────────────────
    def danke(user, trigger, context):
        api.rcon_enqueue([f"playsound minecraft:entity.player.levelup master @a"])
        api.send_overlay_text(
            title="Danke!",
            subtitle=f"{user} hat sich bedankt",
            duration=2
        )

    api.register_action("danke", danke)
```

In der `actions.mca`:
```
follow: $superjump
like: $superrun
5655: $superheal
join: $danke
```

## Zusammenfassung: Lebenszyklus eines Hooks

```
1. TikTok2Mc startet → main.py wird ausgeführt
2. main.py validiert actions.mca
3. main.py erstellt HookAPI-Instanz
4. Hook-Loader scannt src/hooks/*/main.py
5. Für jeden Hook:
   a. main.py importieren
   b. Import-Beschränkungen prüfen
   c. register(api) aufrufen
   d. Handler werden in HOOK_ACTIONS registriert
6. TikTok-Event trifft ein → execute_global_command()
7. HOOK_ACTIONS[action](user, trigger, context) wird aufgerufen
```

> [!NOTE]
> Die hier dokumentierte API ist die stabile, öffentliche Schnittstelle. Interne Methoden der `HookAPI`-Klasse (alle mit `_`-Präfix) sind nicht Teil dieser API.
