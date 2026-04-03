## Eigenem `$`-Befehl erstellen

Das Streaming Tool besitzt ein **Event-Hook-System**, mit dem Entwickler eigene `$`-Commands schreiben können — ganz ohne `main.py` zu verändern.

Du legst eine `.py`-Datei im Ordner `src/event_hooks/` an, definierst dort eine `register(api)`-Funktion und trägst den zugehörigen `$`-Command in der `actions.mca`-Datei ein. Beim nächsten Start des Bots wird dein Hook automatisch geladen und ist sofort einsatzbereit.

> [!WARNING]
> **Eigene Imports sind nur eingeschränkt erlaubt.**
>
> Hook-Skripte laufen innerhalb der gebündelten Anwendung (`app.exe`). Du darfst deshalb **keine beliebigen Module importieren** — es sind nur die folgenden erlaubt:
>
> - `random`
> - `time`
> - (mehr in Zukunft)
>
> Alle anderen Funktionen stehen dir über das `api`-Objekt zur Verfügung (z. B. RCON-Befehle senden, Trigger auslösen, Logging, Config lesen).
> Verwende **keine** eigenen `import`-Anweisungen für externe Pakete wie `requests`, `flask`, `aiohttp` usw. — diese stehen in Hook-Skripten nicht zur Verfügung und führen zu einem Ladefehler.

---

### Wie es funktioniert

Beim Start des Bots werden alle `.py`-Dateien im Ordner `event_hooks/` automatisch geladen und in den laufenden Prozess integriert. Es wird kein eigener Prozess und kein eigenes Executable pro Hook gestartet — alles läuft direkt in der Hauptanwendung.

> [!NOTE]
> **Entwicklung vs. Release:**
> Während der Entwicklung liegt der Ordner unter `src/event_hooks/`. Im Release-Build wird er vom Build-Skript nach `event_hooks/` kopiert. Der Bot lädt die Hooks immer aus dem Release-Pfad (`event_hooks/`), nicht aus `src/event_hooks`.

Die Ladereihenfolge im Detail:

1. **Parsing:** `generate_datapack()` liest `actions.mca` und sammelt alle `$`-Command-Namen (z. B. `$begruessung` → `begruessung`)
2. **Import:** Alle `.py`-Dateien in `event_hooks/` werden via `importlib` dynamisch importiert
3. **Registrierung:** Für jedes geladene Modul wird `register(api)` aufgerufen — dort werden die Handler registriert
4. **Ausführung:** Wenn ein TikTok-Event eintrifft und der zugehörige Trigger auf einen `$`-Command zeigt, wird der passende Handler sofort ausgeführt

---

### Einen Hook erstellen

#### Schritt 1: Hook-Skript anlegen

Erstelle eine neue `.py`-Datei im Ordner `src/event_hooks/`.

**Beispiel:** `src/event_hooks/begruessung.py`

```python
def register(api):
    def begruessung(user, trigger, context):
        api.rcon_enqueue([
            f"say {user} folgt jetzt!",
            "effect give @a minecraft:glowing 5 0 true",
        ])

    api.register_action("begruessung", begruessung)
```

Was passiert hier?

- `register(api)` ist die **Pflichtfunktion**, die vom System aufgerufen wird. Ohne sie wird das Skript ignoriert.
- Innerhalb von `register()` definierst du deinen Handler als Closure — dadurch hat er automatisch Zugriff auf `api`.
- `api.register_action("begruessung", begruessung)` meldet den Handler unter dem Namen `begruessung` an. Dieser Name muss exakt mit dem `$`-Command in der `actions.mca` übereinstimmen.

#### Schritt 2: In `actions.mca` eintragen

Der User (oder du als Entwickler zum Testen) trägt den Command in der `actions.mca` ein. Der Trigger-Key links vom `:` bestimmt, bei welchem TikTok-Event der Hook ausgelöst wird:

```
follow: $begruessung
```

In diesem Beispiel: Jedes Mal, wenn jemand auf TikTok folgt, wird der Hook `begruessung` aufgerufen.

#### Schritt 3: Bot starten oder neu starten

Starte den Bot — oder starte ihn neu, falls er bereits läuft. Der Hook wird automatisch geladen und ist sofort aktiv.

---

### Die `register(api)`-Funktion

Jede Hook-Datei **muss** eine `register(api)`-Funktion auf oberster Ebene bereitstellen. Fehlt sie, wird das Skript beim Laden **übersprungen** und eine Fehlermeldung ausgegeben.

`register()` wird genau einmal beim Start des Bots aufgerufen. Definiere alle deine Handler innerhalb dieser Funktion als Closures — so haben sie automatisch Zugriff auf das `api`-Objekt, ohne dass du globale Variablen brauchst.

```python
def register(api):
    def mein_handler(user, trigger, context):
        # Deine Logik hier
        api.log(f"{user} hat {trigger} ausgelöst")

    api.register_action("meine_aktion", mein_handler)
```

> [!WARNING]
> Dateien ohne `register()`-Funktion werden **nicht** geladen. In der Konsole erscheint dann:
> ```
> [HOOK] [ERROR] dateiname.py has no register() function — skipped.
> ```

---

### Handler-Signatur

Jeder Handler muss genau **drei Argumente** akzeptieren:

| Argument | Typ | Beschreibung |
|---|---|---|
| `user` | `str` | Der TikTok-Benutzername, der das Event ausgelöst hat (z. B. `"max_mustermann"`) |
| `trigger` | `str` | Der Name des `$`-Commands, der gerade ausgeführt wird (z. B. `"begruessung"`) |
| `context` | `dict` | Reserviert für zukünftige Erweiterungen — aktuell wird immer ein leeres `{}` übergeben |

```python
def mein_handler(user, trigger, context):
    api.rcon_enqueue([f"say Hallo {user}, Trigger war: {trigger}"])
```

Fehlende oder zu viele Argumente führen dazu, dass der Handler beim Aufruf einen Fehler wirft (der Bot bleibt aber stabil — siehe [Fehlerbehandlung](#fehlerbehandlung)).

---

### Die `HookAPI`

Das `api`-Objekt, das an `register()` übergeben wird, ist die einzige Schnittstelle zwischen deinem Hook und dem Hauptsystem. Es stellt folgende Methoden bereit:

#### `api.register_action(name, fn)`

Registriert einen Handler unter dem angegebenen Namen. Der Name muss exakt mit dem `$`-Command in der `actions.mca` übereinstimmen.

```python
api.register_action("begruessung", begruessung)
```

> [!WARNING]
> Wird derselbe Name zweimal registriert (z. B. in zwei verschiedenen Hook-Dateien), gewinnt die **erste** Registrierung. Die zweite wird ignoriert und eine Warnung ausgegeben:
> ```
> [HOOK] [WARN] Duplicate action 'begruessung' — first registration kept.
> ```

#### `api.rcon_enqueue(commands)`

Sendet eine Liste von Minecraft-Commands an die RCON-Queue. Die Commands werden der Reihe nach an in
die RCON-Queue geschoben und von dort abgearbeitet.

```python
api.rcon_enqueue([
    "effect give @a minecraft:speed 10 2 true",
    f"say {user} hat einen Speed-Boost ausgelöst!",
])
```

Jeder Eintrag ist ein vollständiger Command als String — **ohne** führenden `/`.

> [!NOTE]
> **Vanilla- und Plugin-Commands sind beide erlaubt.**
>
> Da alles über RCON läuft, kannst du nicht nur Vanilla-Minecraft-Commands senden, sondern auch Commands von installierten Server-Plugins (z. B. Bukkit/Paper/Spigot-Plugins). Der Server empfängt sie genau so, als hättest du sie in der Server-Konsole eingegeben worden.
>
> ```python
> api.rcon_enqueue([
>     "tnt 2 0.1 2 Notch",  # Beispiel: Plugin-Command
>     "say Boost aktiv!",   # Vanilla-Command
> ])
> ```

#### `api.enqueue_trigger(trigger, user)`

Schiebt einen **Trigger** in die Trigger-Queue. Der Bot verarbeitet ihn exakt so, als wäre ein TikTok-Event mit diesem Trigger eingetroffen — inklusive **aller** Aktionen, die dem Trigger in der `actions.mca` zugeordnet sind (Vanilla, RCON, Overlay, weitere `$`-Commands).

> [!WARNING]
> **Das erste Argument ist ein Trigger — kein `$`-Command-Name.**
>
> Ein Trigger ist das, was **links** vom `:` in der `actions.mca` steht.
> Das sind z. B. Gift-IDs (`5655`), reservierte Event-Namen (`follow`, `likes`) oder eigene Trigger, die du selbst angelegt hast.
>
> Was **rechts** vom `:` hinter dem `$` steht — also der Command-Name wie `begruessung` oder `superjump` — ist **kein** gültiger Trigger.
>
> ```
> follow: $begruessung
> │         │
> │         └── $-Command-Name (KEIN gültiger Trigger)
> └──────────── Trigger (das musst du an enqueue_trigger übergeben)
> ```
>
> `api.enqueue_trigger("begruessung", user)` tut **nichts** — still ignoriert, kein Fehler, keine Warnung.
> `api.enqueue_trigger("follow", user)` funktioniert — `follow` steht links in der `actions.mca`.

> [!NOTE]
> Der Trigger wird **asynchron** in die Queue gestellt — er wird nicht sofort im selben Handler-Aufruf abgearbeitet. Die RCON-Commands deines aktuellen Handlers laufen zuerst, dann kommt der weitergeleitete Trigger dran.

---

##### Variante A — Einen bestehenden Trigger weiterleiten

Du kannst aus einem Hook heraus einen Trigger auslösen, der in der `actions.mca` bereits für ein anderes TikTok-Event eingetragen ist.

`actions.mca`:
```
follow: $begruessung; /give @a minecraft:golden_apple 7
5655:   $grosses_geschenk
```

```python
def register(api):
    def grosses_geschenk(user, trigger, context):
        api.rcon_enqueue(f"say Riesiges Geschenk von {user}!")
        # Löst zusätzlich den "follow"-Trigger aus.
        # → Der User bekommt die Begrüßung + Golden Apples on top.
        api.enqueue_trigger("follow", user)

    def begruessung(user, trigger, context):
        api.rcon_enqueue(f"say Hallo {user}")

    api.register_action("grosses_geschenk", grosses_geschenk)
    api.register_action("begruessung", begruessung)
```

Was passiert bei Gift `5655`?

1. TikTok meldet Gift `5655` → Trigger `5655` wird abgearbeitet
2. `execute_global_command("5655", …)` findet `$grosses_geschenk` → ruft deinen Handler auf
3. Handler sendet die RCON-Nachricht und schiebt `"follow"` in die Queue
4. Kurz darauf: `execute_global_command("follow", …)` läuft — führt `$begruessung` **und** `/give …` aus

So bekommt ein Geschenke-Sender automatisch dieselbe Behandlung wie ein neuer Follower, ohne dass du den Follow-Code duplizieren musst.

> [!WARNING]
> **Achtung: Endlosschleifen!**
>
> Leite niemals auf den Trigger zurück, der deinen eigenen Handler ausgelöst hat:
>
> ```
> follow: $begruessung
> ```
> ```python
> def begruessung(user, trigger, context):
>     api.enqueue_trigger("follow", user)  # ← Loop!
> ```
>
> Sobald jemand auf TikTok folgt, löst das den `follow`-Trigger aus. Dessen Handler schiebt `follow` wieder in die Queue, der Handler feuert erneut, schiebt wieder `follow` hinein — und so weiter.
>
> Das System erkennt das zur Laufzeit automatisch. Nach 3 Ketten-Schritten wird der Trigger geblockt und dauerhaft für die laufende Session gesperrt:
>
> ```
> [HOOK] [ERROR] enqueue_trigger('follow') blocked — chain depth 4 exceeds maximum (3).
>                Trigger 'follow' is now permanently banned for this session. Possible infinite loop.
> ```
>
> Jeder weitere `enqueue_trigger("follow", ...)`-Aufruf — egal von welchem Hook — wird dann sofort abgewiesen:
>
> ```
> [HOOK] [ERROR] enqueue_trigger('follow') permanently blocked — trigger was banned after loop detection.
> ```
>
> **Was wird noch ausgeführt?**
>
> `enqueue_trigger` wirft keine Exception — es gibt nur ein stilles `return` zurück zur aufrufenden Stelle. Das bedeutet:
>
> - **Der Rest des Handlers läuft normal weiter.** Hat `begruessung` nach dem `enqueue_trigger`-Aufruf noch weiteren Code (z. B. weitere `rcon_enqueue`-Aufrufe, Logging, etc.), wird der vollständig ausgeführt. Nur der Eine `enqueue_trigger`-Aufruf ist blockiert.
>
> - **Die restlichen Aktionen aus der `actions.mca`-Zeile laufen ebenfalls normal.** Angenommen, `follow` ist so eingetragen:
>   ```
>   follow: $begruessung; /give @a minecraft:golden_apple 7
>   ```
>   Der Handler `begruessung` wird aufgerufen (inklusive allem Code dahinter), und der `/give`-Command wird danach **normal ausgeführt** — der Ban betrifft nur den `enqueue_trigger`-Aufruf, nichts sonst.

---

##### Variante B — Einen eigenen Trigger anlegen

Trigger in der `actions.mca` müssen keine echten TikTok-Events sein. Du kannst dir **eigene Trigger** anlegen — sie sind genauso gültig wie `follow` oder eine Gift-ID, werden aber nie automatisch von TikTok ausgelöst. Sie feuern nur, wenn du sie per `enqueue_trigger` anstößt.

`actions.mca`:
```
5655:        $geschenk_klein
8913:        $geschenk_gross
dankeschoen: $dankeschoen
```

Hier ist `dankeschoen` ein eigener Schlüssel. Kein TikTok-Event heißt so — er dient rein als interner Ketten-Schritt, den deine Hooks über `enqueue_trigger` aufrufen.

```python
def register(api):
    def geschenk_klein(user, trigger, context):
        api.rcon_enqueue(["effect give @a minecraft:speed 5 1 true"])
        api.enqueue_trigger("dankeschoen", user)

    def geschenk_gross(user, trigger, context):
        api.rcon_enqueue(["effect give @a minecraft:speed 20 3 true"])
        api.enqueue_trigger("dankeschoen", user)

    def dankeschoen(user, trigger, context):
        api.rcon_enqueue([f"say Danke an {user} für das Geschenk!"])

    api.register_action("geschenk_klein", geschenk_klein)
    api.register_action("geschenk_gross", geschenk_gross)
    api.register_action("dankeschoen", dankeschoen)
```

Was passiert bei Gift `5655`?

1. `execute_global_command("5655", …)` → findet `$geschenk_klein` → ruft deinen Handler auf
2. Handler gibt Speed-Effekt und schiebt `"dankeschoen"` in die Queue
3. `execute_global_command("dankeschoen", …)` → findet `$dankeschoen` → ruft `dankeschoen`-Handler auf
4. Handler sendet die Danke-Nachricht

Bei Gift `8913` passiert dasselbe über `geschenk_gross`, aber am Ende läuft dieselbe `dankeschoen`-Aktion. Die Logik steht nur einmal im Code.

---

##### Warum lohnt sich ein eigener Trigger?

Ein eigener Trigger ist ein vollwertiger `actions.mca`-Eintrag. Das heißt: du kannst ihm nicht nur einen `$`-Hook zuweisen, sondern die **gesamte Palette** der `actions.mca`-Syntax nutzen — Vanilla-Commands, RCON, Overlay-Text, alles auf einmal:

```
dankeschoen: $dankeschoen; /playsound minecraft:entity.player.levelup master @a; >>Danke!|{user} hat gesponsert!|4
```

Wenn jetzt ein Hook `api.enqueue_trigger("dankeschoen", user)` aufruft, passiert alles zusammen: dein Python-Handler läuft, der Sound wird über das Datapack abgespielt, und der Overlay-Text erscheint im Stream.

Die konkreten Vorteile:

- **Wiederverwendbarkeit:** Beliebig viele Hooks können denselben Trigger aufrufen. Die gemeinsame Logik steht einmal — im Hook und/oder in der `actions.mca`.
- **Trennung von Code und Konfiguration:** Der Streamer kann in der `actions.mca` Commands, Sounds oder Overlay-Text an den Trigger anhängen, ohne die Python-Datei anfassen zu müssen. Du als Entwickler schreibst die Logik, der Streamer konfiguriert den Rest.
- **Verkettung:** Trigger können andere Trigger auslösen — so baust du komplexe Abläufe aus einfachen, testbaren Bausteinen zusammen.
- **Später erweiterbar:** Wenn der Streamer irgendwann noch einen Firework-Effekt dranhängen will, ändert er nur die eine Zeile in `actions.mca` — fertig. Kein Code-Deployment nötig.

> [!TIP]
> Du möchtest testen, ob deine Trigger funktionieren?
> Dann wirf einen Blick in die GUIDE.md, Kapitel "Test Your Triggers Without TikTok". Dort findest du ein Test-Tool, mit dem du deine Trigger ganz ohne TikTok-Verbindung ausprobieren kannst.
>
> Wenn du Python installiert hast, kannst du in der Entwicklungsstruktur auch direkt die Datei `tests/send_trigger.py` starten und so Trigger bequem aus der Konsole testen – ganz ohne die .exe zu verwenden.
> Beachte aber: Auch beim Testen mit `send_trigger.py` muss das Projekt gebaut sein und alle anderen Komponenten in der Release-Umgebung laufen.

#### `api.log(msg)`

Gibt eine Nachricht in der Konsole aus, mit automatischem `[HOOK]`-Prefix. Nützlich zum Debuggen.

```python
api.log("Hook erfolgreich geladen")
# Ausgabe: [HOOK] Hook erfolgreich geladen
```

#### `api.config`

Lesezugriff auf die geladenen Werte aus `config.yaml`. Gibt ein verschachteltes Dictionary zurück.

```python
port = api.config.get("RCON", {}).get("Port", 25575)
```

---

### Einen Handler für mehrere `$`-Commands verwenden

Manchmal sollen mehrere `$`-Commands ähnlich reagieren, aber mit leichten Unterschieden. In diesem Fall registrierst du dieselbe Funktion unter mehreren Namen und unterscheidest im Handler über das `trigger`-Argument, welcher Command gerade aktiv ist.

```python
def register(api):
    def power_up(user, trigger, context):
        effects = {
            "superjump": "minecraft:jump_boost",
            "superrun":  "minecraft:speed",
            "superheal": "minecraft:regeneration",
        }
        effect = effects.get(trigger)
        if effect:
            api.rcon_enqueue([f"effect give @a {effect} 10 5 true"])

    api.register_action("superjump", power_up)
    api.register_action("superrun", power_up)
    api.register_action("superheal", power_up)
```

Der User trägt dann in `actions.mca` ein:
```
5655: $superjump
16111: $superrun
7934: $superheal
```

So brauchst du nur **einen** Handler für beliebig viele verwandte Commands.

---

### Mehrere Aktionen in einer Datei

Eine einzelne `.py`-Datei kann beliebig viele Aktionen registrieren. Du bist nicht auf einen Handler pro Datei beschränkt:

```python
def register(api):
    def bei_follow(user, trigger, context):
        api.rcon_enqueue([f"say {user} folgt jetzt!"])

    def bei_grossem_geschenk(user, trigger, context):
        api.rcon_enqueue([
            "summon minecraft:firework_rocket ~ ~ ~",
            f"say Danke, {user}!",
        ])

    api.register_action("follow_effekt", bei_follow)
    api.register_action("geschenk_effekt", bei_grossem_geschenk)
```

---

### Fehlerbehandlung

Fehler innerhalb eines Hook-Handlers **crashen den Bot nicht**. Sie werden abgefangen und mit einem `[HOOK]`-Prefix in der Konsole ausgegeben:

```
[HOOK] [WARN] Error in action 'begruessung': name 'undefined_var' is not defined
```

Auch beim Laden gibt es ein Sicherheitsnetz:

- **Syntaxfehler** in einer Hook-Datei → nur diese Datei wird übersprungen, alle anderen laden normal weiter
- **Fehlende `register()`-Funktion** → Datei wird übersprungen mit Fehlermeldung
- **Exception in `register()`** → Datei wird übersprungen, Fehler wird geloggt
- **Exception im Handler zur Laufzeit** → wird geloggt, Bot läuft weiter

---

### Build-in Commands können nicht überschrieben werden

> [!WARNING]
> Bestimmte $-Commands sind fest im System eingebaut und können nicht durch eigene Hooks überschrieben werden.
> 
> Aktuell reservierte Namen:
> - `random`
> 
> Wenn du versuchst, einen dieser Namen mit `api.register_action("random", ...)` zu registrieren, erscheint beim Laden folgende Fehlermeldung:
> ```
> [HOOK] [ERROR] 'random' is a reserved built-in command — cannot be overridden by a hook.
> ```
> 
> Diese Commands werden intern von main.py behandelt und sind für eigene Hooks gesperrt.

→ [Nächstes Kapitel: RCON und seine Grenzen](./ch03-07-Rcon-and-Its-Limitations.md)