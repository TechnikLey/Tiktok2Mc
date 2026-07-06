# Hook-API-Referenz

Alle Methoden, die dein Hook über das `api`-Objekt in der `register()`-Funktion nutzen kann.

## Übersicht

| Methode | Beschreibung |
|---------|--------------|
| `register_action(name, fn)` | Handler für `$`-Befehle registrieren |
| `rcon_enqueue(commands)` | Minecraft-Befehle ausführen |
| `enqueue_trigger(action_name, user="hook")` | Einen anderen Trigger auslösen (verkettet) |
| `get_hook_config(name)` | Per-Hook-Konfiguration lesen |
| `send_overlay_text(title, subtitle="", duration=3, overlay_name="default")` | Overlay-Text anzeigen |
| `log(msg)` | Hook-spezifisch loggen |
| `config` (Property) | Globale Config lesen (Kopie) |

## register_action(name, fn)

Registriert eine Handler-Funktion im globalen `HOOK_ACTIONS`-Dictionary.

```python
api.register_action("superjump", mein_handler)
```

- **name**: Muss mit dem Namen nach `$` in der `actions.mca` übereinstimmen
- **fn**: `(user: str, trigger: str, context: dict) -> None`
- Doppelte Registrierung wird ignoriert (erster Aufruf gewinnt)

```python
def register(api: HookAPI):
    def handler(user, trigger, context):
        api.rcon_enqueue([f"say {user} löste {trigger} aus!"])

    api.register_action("mein-befehl", handler)
```

## rcon_enqueue(commands)

Fügt eine Liste von Minecraft-Befehlen in die RCON-Warteschlange ein.

```python
api.rcon_enqueue([
    "effect give @a minecraft:speed 30 2 true",
    f"say {user} hat Geschwindigkeit ausgelöst!",
])
```

- **commands**: `list[str]` — werden nacheinander an den Minecraft-Server gesendet
- Die Queue ist asynchron: Die Funktion blockiert nicht
- Bei voller Queue werden Befehle stillschweigend verworfen

## enqueue_trigger(action_name, user="hook")

Löst einen anderen Action-Namen aus (verkettete Trigger).

```python
api.enqueue_trigger("explosion", user)
```

- Ruft `execute_global_command(action_name, user)` auf
- **Maximale Verkettungstiefe**: 3 (danach wird der Trigger gesperrt)
- Bei Überschreitung wird der Action-Name **dauerhaft für die Session** blockiert

### Beispiel: Verkettung

```
actions.mca:
  follow: $begruessung
  $begruessung → enqueue_trigger("feuerwerk")
  feuerwerk → in actions.mca: feuerwerk: $effekt
```

Der Hook reagiert auf `$begruessung` und löst dann `feuerwerk` aus:

```python
def on_begruessung(user, trigger, context):
    api.rcon_enqueue([f"say Hallo {user}!"])
    api.enqueue_trigger("feuerwerk", user)
```

## get_hook_config(name)

Gibt die Konfiguration eines bestimmten Hooks als Dict zurück. Der Parameter `name` ist der Hook-Name (identisch mit dem Verzeichnisnamen und dem `name`-Feld in der `hook.json`).

```python
config = api.get_hook_config("sprung")
dauer = config.get("dauer", 10)
```

- Liefert ein leeres Dict `{}`, wenn der Hook keine Konfiguration hat
- Die Konfiguration stammt aus der `config.yaml` des Hooks kombiniert mit dem `config_schema`

## send_overlay_text(title, subtitle="", duration=3, overlay_name="default")

Zeigt eine Overlay-Textnachricht an.

```python
api.send_overlay_text("Neuer Follower!", user, 5)
api.send_overlay_text("Gift", "Diamant", 3, "gift-overlay")
```

- **title**: Haupttext
- **subtitle**: Untertitel (optional)
- **duration**: Anzeigedauer in Sekunden (Default: 3)
- **overlay_name**: Overlay-Kanal (Default: `"default"`)
- Gibt `True` bei Erfolg, `False` bei Fehler zurück (z. B. wenn der API-Server nicht erreicht werden kann oder das Overlay deaktiviert ist)

## log(msg)

Schreibt eine Hook-spezifische Log-Nachricht.

```python
api.log(f"Benutzer {user} hat Aktion ausgelöst")
```

- Erscheint im Log mit `[HOOK]` Präfix

## config (Property)

Schreibgeschützter Zugriff auf die globale `config.yaml` (Kopie).

```python
glob_cfg = api.config
rcon_host = glob_cfg.get("rcon", {}).get("host", "localhost")
```

## Fehlercodes für Hooks

| Code | Bedeutung |
|------|-----------|
| `HOOK-0001` | Hook-Verzeichnis nicht gefunden |
| `HOOK-0002` | `hook.json` fehlt oder ungültig |
| `HOOK-0003` | `main.py` fehlt |
| `HOOK-0004` | `name` oder `version` fehlt im Manifest |
| `HOOK-0005` | Disallowed import gefunden |
| `HOOK-0006` | Unerwarteter Fehler beim Laden |
| `HOOK-0007` | `register()`-Funktion fehlt |

## Nächstes Kapitel

Lerne, wie du [Hook-Konfigurationen](./ch04-04-hook-configuration.md) definierst und ausliest.
