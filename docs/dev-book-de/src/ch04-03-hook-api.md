# Hook-API-Referenz

Alle Methoden, die dein Hook über das `api`-Objekt in der `register()`-Funktion nutzen kann.

## Übersicht

| Methode | Beschreibung |
|---------|--------------|
| `register_action(name, fn)` | Handler für `$`-Befehle registrieren |
| `rcon_enqueue(commands)` | Minecraft-Befehle ausführen |
| `enqueue_trigger(action_name, user="hook", context=None)` | anderen Trigger auslösen (verkettet) |
| `get_hook_config(name)` | Per-Hook-Konfiguration lesen |
| `send_overlay_text(title, subtitle="", duration=3, overlay_name="default")` | Overlay-Text anzeigen |
| `store_get(key, default=None)` | Aus dem persistenten Store dieses Hooks lesen |
| `store_set(key, value)` | In den persistenten Store schreiben |
| `store_delete(key)` | Schlüssel aus dem Store löschen |
| `store_all()` | Kompletten Store lesen |
| `log(msg)` | Hook-spezifische Meldung loggen |
| `config` (Property) | Globale Config lesen (Kopie) |

## register_action(name, fn)

Registriert eine Handler-Funktion im globalen `HOOK_ACTIONS`-Dictionary.

```python
api.register_action("superjump", mein_handler)
```

- **name**: Muss mit dem Namen nach `$` in der `actions.mca` übereinstimmen
- **fn**: `(user: str, trigger: str, context: HookContext) -> bool | None`
  — `user` ist immer der reine Benutzername-String; Ereignisdaten liegen
  in `context` (siehe unten)
- Doppelte Registrierung wird ignoriert (erster Aufruf gewinnt)

```python
def register(api: HookAPI):
    def handler(user, trigger, context):
        api.rcon_enqueue([f"say {user} löste {trigger} aus!"])

    api.register_action("mein-befehl", handler)
```

### Rückgabewert — Veto-Vertrag

Eine Hook-Action kann den auslösenden Trigger durch die Rückgabe von `False` blockieren (Veto):

| Rückgabewert | Wirkung |
|--------------|--------|
| `None` (Standard) / `True` | Kette läuft wie gewohnt weiter |
| `False` | Der Rest der Trigger-Kette wird abgebrochen |

Gibt ein Hook `False` zurück, werden alle folgenden `$`-Aktionen derselben
Trigger-Zeile übersprungen; Overlay-, Vanilla-, RCON- und Shell-Aktionen des
Triggers werden nicht ausgeführt. Bereits von früheren Hooks enqueued Trigger
(via `enqueue_trigger`) bleiben unberührt.

Damit lassen sich Gate-Hooks wie Rate-Limiter oder Schimpfwortfilter umsetzen:

```python
def register(api: HookAPI):
    recent: list[float] = []

    def anti_spam(user, trigger, context):
        now = time.time()
        recent[:] = [t for t in recent if now - t < 5]
        if len(recent) >= 10:
            return False  # zu viele Events — ganzen Trigger blockieren
        recent.append(now)

    api.register_action("gate", anti_spam)
```

In der `data/actions.mca` steht das Gate an erster Stelle, damit es vor allem anderen läuft:

```mca
gift:$gate;$say_thanks
```

## Handler-Kontext — strukturierte Ereignisdaten

Das dritte Handler-Argument ist ein **`HookContext`** — eine `dict`-Unterklasse,
die das Ereignis beschreibt, mit dem die Kette gestartet wurde. Sie wird von der
Ereignisquelle gebaut und enthält mindestens:

| Schlüssel | Typ | Bedeutung |
|-----|------|---------|
| `event` | `str` | Trigger-Familie: `"gift"`, `"follow"`, `"like"`, `"comment"`, `"join"`, `"share"` bzw. der Trigger-Name bei Webhook-/Hook-Quellen |
| `source` | `str` | Herkunft des Triggers: `"tiktok"`, `"webhook"` (custom_trigger/Test/API-Dispatch) oder `"hook"` |

Ereignisspezifische Schlüssel kommen hinzu:

| Ereignis | Zusätzliche Schlüssel |
|-------|------------|
| `gift` | `gift_name`, `gift_id`, `streak` (Combo-Länge; `1` bei Nicht-Combo-Gifts), `combo` |
| `comment` | `comment`, `is_moderator`, `is_super_fan`, `in_fanclub` |
| `like` | `total_since_start`, `milestone_every`, `milestone_rule` |
| Hook-verkettet (`enqueue_trigger`) | `hook` (Name deines Hooks) plus alles, was du per `context=` übergibst |

Schlüssel sind nur vorhanden, wenn sie bedeutungsvoll sind (z. B. fehlt
`combo` bei Nicht-Gift-Events). Pflicht-Schlüssel liest du als Attribute,
optionale via `.get()`:

- `context.event`, `context.streak` — Attribut-Zugriff, fail-fast mit
  `AttributeError` bei unbekannten Schlüsseln (Tippfehler-Schutz)
- `context.get("combo", False)` — optionale Schlüssel mit Defaults
- Volle Dict-Kompatibilität bleibt erhalten: `in`, Iteration,
  `json.dumps(context)` funktionieren wie gewohnt

Interne Mechanik wie die Verkettungstiefe ist bewusst **nicht** Teil des
Kontexts — er beschreibt das Ereignis, nicht den Dispatcher.

### Beispiel: Gift-Combo-Bonus

Da der Kontext die fertige Streak-Länge enthält, ist ein Combo-Bonus nur
noch ein einfacher Schwellwert-Check — Combo-Gifts feuern einmal beim
Ende der Streak, mit `streak` als Gesamtzahl der Gifts:

```python
def register(api: HookAPI):
    def combo_bonus(user, trigger, context):
        if context.event != "gift":
            return
        if context.gift_name == "Rose" and context.streak >= 10:
            api.rcon_enqueue([f"say {user} hat eine {context.streak}x Rosen-Combo geschickt!"])
            api.enqueue_trigger(
                "mega_celebration", user,
                context={"event": "gift", "gift_name": "Rose",
                         "streak": context.streak},
            )

    api.register_action("combo_check", combo_bonus)
```

```mca
gift:$combo_check;$say_thanks
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

## enqueue_trigger(action_name, user="hook", context=None)

Löst einen anderen Action-Namen aus (verkettete Trigger).

```python
api.enqueue_trigger("explosion", user)
```

- Ruft `execute_global_command(action_name, user)` auf
- **Maximale Verkettungstiefe**: 3 (danach wird der Trigger gesperrt)
- Bei Überschreitung wird der Action-Name **dauerhaft für die Session** blockiert
- **context**: optionales Dict, das an die Hook-Actions der neuen Kette
  weitergereicht wird (siehe [Handler-Kontext](#handler-kontext--strukturierte-ereignisdaten)).
  Ohne Angabe startet die neue Kette mit `{"source": "hook", "hook": <name>}`.

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
rcon_host = glob_cfg.get("server_host", "127.0.0.1")
```

## Persistenter Speicher

Jeder Hook bekommt automatisch seinen eigenen Namespace im namespaced
persistenten Store der API (`data/plugin_data/<hook-name>.json`). Das `api`-Objekt,
das an `register()` übergeben wird, ist bereits an den Namen deines Hooks gebunden
— kein HTTP-Boilerplate nötig:

```python
def register(api: HookAPI):
    def track(user, trigger, context):
        count = api.store_get("count", 0)
        api.store_set("count", count + 1)

    api.register_action("track", track)
```

| Methode | Verhalten |
|--------|----------|
| `store_get(key, default=None)` | Liefert den Wert, oder `default`, wenn der Schlüssel fehlt / der Store nicht erreichbar ist |
| `store_set(key, value)` | Speichert beliebige JSON-serialisierbare Daten; gibt `True`/`False` zurück |
| `store_delete(key)` | Löscht einen Schlüssel; `True` wenn er existierte |
| `store_all()` | Liefert alle Schlüssel/Werte als Dict |

Schlüssel müssen dem Muster `[A-Za-z0-9_.-]{1,128}` entsprechen. Werte überleben
Neustarts und werden atomar geschrieben. Das Dashboard kann dieselben Daten über
`GET /api/v1/plugins/<hook-name>/data` lesen.

## Lifecycle-Callbacks

Hooks können Callbacks registrieren, die feuern, wenn die TikTok-Live-Verbindung
hergestellt wird oder wenn der Live-Stream endet. Nützlich für Start-/Shutdown-
Ankündigungen, Reset internen States oder Synchronisation mit externen Diensten.

```python
def register(api: HookAPI):
    def on_start():
        api.send_overlay_text("Stream Online!", "Hooks sind aktiv", 5)
        api.log("TikTok-Verbindung hergestellt — Hook bereit")

    def on_end():
        api.send_overlay_text("Stream Offline", "Bis zum nächsten Mal!", 5)
        api.log("TikTok-Stream beendet — Hook fährt herunter")

    api.on_live_start(on_start)
    api.on_live_end(on_end)
```

- **`on_live_start(fn)`** — Wird einmal aufgerufen, wenn die Bridge erfolgreich
  mit dem TikTok-Live-Stream verbunden ist (`ConnectEvent`). Läuft in einem
  Hintergrund-Executor; Exceptions in einem Hook blockieren andere Hooks nie.
- **`on_live_end(fn)`** — Wird einmal aufgerufen, wenn der Live-Stream endet
  (`LiveEndEvent`). Ebenfalls im Hintergrund-Executor.
- Die generische Form ist `api.register_lifecycle(event, fn)` mit `event`
  als `"live_start"` oder `"live_end"`. Die Convenience-Methoden sind empfohlen.

> [!NOTE]
> Callbacks sind synchron (kein `async def`). Sie laufen in einem Thread-Pool,
> um den TikTok-Client-Thread nicht zu blockieren. Halte sie kurz; schwere
> Arbeit sollte via `api.rcon_enqueue`, `api.enqueue_trigger` oder HTTP-Calls
> ausgelagert werden.

## Hook-Runtime-Reload

**Hooks aktivieren/deaktivieren oder deren Config ändern — ohne Bridge-Restart.**

Wenn du:
- einen Hook im Dashboard aktivierst/deaktivierst (`POST /hooks/{name}/enable|disable`)
- die Hook-Config speicherst (`PUT /hooks/{name}/config`)
- `POST /reload` mit `"hooks": true` aufrufst

nimmt die Bridge das `reload_hooks`-Signal innerhalb von ~1 Sekunde auf und
registriert alle aktiven Hooks neu. Dein `register()` läuft erneut, liest also
die frische Config und registriert Actions neu.

> [!IMPORTANT]
> - `register()` wird **bei jedem Reload** aufgerufen, nicht nur einmal. Schreibe
>   es idempotent (z. B. `register_action` ignoriert Duplikate, daher ist
>   erneutes Registrieren desselben Action-Namens sicher).
> - Per-Hook-Config wird beim Reload neu via `get_hook_config()` eingelesen.
> - Wenn dein Hook externe Ressourcen hält (Dateien, Verbindungen), kannst du
>   Reloads detektieren. Ein Muster:
>   ```python
>   def register(api: HookAPI):
>       if not hasattr(register, "_first_run"):
>           register._first_run = True
>           # Einmaliges Setup (Verbindung öffnen, etc.)
>       # Actions neu registrieren (wiederholbar sicher)
>       api.register_action("meine_action", handler)
>   ```

## Fehlercodes für Hooks

| Code | Bedeutung |
|------|-----------|
| `HOOK-0001` | Hook-Manifest fehlt oder ungültig |
| `HOOK-0002` | `main.py` des Hooks nicht gefunden |
| `HOOK-0003` | Nicht erlaubtes Modul importiert |
| `HOOK-0004` | Hook konnte nicht geladen werden (`main.py` warf Exception) |
| `HOOK-0005` | Registrierung fehlgeschlagen (`register()` warf Exception) |
| `HOOK-0006` | Hook-Action fehlgeschlagen (Exception bei Ausführung) |
| `HOOK-0007` | `register()`-Funktion fehlt |

## Nächstes Kapitel

Lerne, wie du [Hook-Konfigurationen](./ch04-04-hook-configuration.md) definierst und ausliest.
