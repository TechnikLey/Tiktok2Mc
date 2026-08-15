# Dein erster Hook

In diesem Tutorial erstellst du deinen ersten Hook. Der Hook wird auf den `$superjump`-Befehl reagieren und allen Minecraft-Spielern einen Sprung-Boost geben.

Du lernst dabei nicht nur den Code, sondern auch, wie ein Hook im Bridge-Prozess lebt: wie er geladen wird, wie die `$`-Befehle aus der `actions.mca` zu deinem Handler gelangen und wie das System Hooks von Plugins unterscheidet.

## Hook erstellen

Das Projekt enthält ein Skript, das die Grundstruktur für einen Hook erzeugt:

```bash
python create_hook.py
```

Das Skript fragt nach:

- **Hook-Name**: Nur Kleinbuchstaben und Ziffern, z. B. `sprung`
- **Ort**: Haupt-Hooks-Verzeichnis oder Plugin-gebündelt
- **Action-Name**: Der Name für den `$`-Befehl in der `actions.mca`
- **Update-URL**: Optional

Nach der Erstellung findest du den Hook unter `src/hooks/sprung/`:

```
src/hooks/sprung/
├── hook.json
├── main.py
└── config.yaml
```

## Hook-Code schreiben

Öffne `src/hooks/sprung/main.py` und ersetze den Inhalt:

```python
from core.hook_api import HookAPI

def register(api: HookAPI):
    def superjump(user, trigger, context):
        api.rcon_enqueue([
            f"effect give @a minecraft:jump_boost 10 5 true",
            f"say {user} hat einen Supersprung ausgelöst!",
        ])

    api.register_action("superjump", superjump)
```

### Was passiert hier Zeile für Zeile?

**`def register(api: HookAPI)`**: Jeder Hook **muss** eine Funktion namens `register` auf oberster Ebene definieren. Der Hook-Loader ruft diese Funktion genau einmal beim Start auf und übergibt ihr ein `HookAPI`-Objekt. Ohne diese Funktion wird der Hook nicht geladen (Fehler `HOOK-0007`).

**`api.register_action("superjump", superjump)`**: Registriert die Handler-Funktion unter dem Namen `"superjump"` im globalen `HOOK_ACTIONS`-Dictionary. Wenn später ein `$superjump`-Befehl in der `actions.mca` ausgelöst wird, sucht das System in diesem Dictionary nach dem Namen und ruft die zugehörige Funktion auf.

**`def superjump(user, trigger, context)`**: Die Handler-Funktion muss drei Parameter akzeptieren:
- `user`: Der TikTok-Benutzername, der das Event ausgelöst hat (String)
- `trigger`: Der Action-Name (hier `"superjump"`)
- `context`: Ein Dictionary für zukünftige Erweiterungen (aktuell leer)

**`api.rcon_enqueue([...])`**: Fügt eine Liste von Minecraft-Befehlen in die RCON-Warteschlange ein. Die Befehle werden nacheinander an den Minecraft-Server gesendet.

## In actions.mca eintragen

Öffne die `actions.mca` (standardmäßig `data/actions.mca`) und füge eine Zeile hinzu:

```
follow: $superjump
```

Jedes Mal, wenn jemand auf TikTok folgt, wird der `$superjump`-Hook ausgelöst.

### Wie der `$`-Befehl fließt – vom TikTok-Event zum Handler

```
TikTok CommentEvent "follow"
       │
       ▼
on_follow() in main.py
       │
       ▼ Event in die Trigger-Queue einreihen
       │
trigger_worker() in main.py
       │
       ▼
execute_global_command("follow", user)
  │
  ├─ Prüft: Ist "follow" in ctx.script_actions?
  │   (Wird beim Start aus actions.mca geparst)
  │
  └─ Ja → Für jede Aktion unter "follow":
           ├─ Ist "$superjump" in HOOK_ACTIONS registriert?
           │   (Wurde von register_action() befüllt)
           │
           └─ Ja → superjump(user, "superjump", {}) aufrufen
                     │
                     ▼
                   api.rcon_enqueue(["effect give @a ...", "say ..."])
```

**Drei Phasen der Initialisierung:**

1. **Beim Start parsen**: Der Bridge-Prozess (`main.py`) liest die `actions.mca` und erstellt ein Dictionary `ctx.script_actions`. Für jede Zeile wie `follow: $superjump` speichert er: `script_actions["follow"] = ["superjump"]`.
2. **Hooks laden**: Der Hook-Loader durchläuft `src/hooks/*/main.py`, importiert jede Datei und ruft `register(api)` auf. Dabei werden Handler im globalen `HOOK_ACTIONS`-Dictionary registriert.
3. **Zur Laufzeit**: Wenn ein TikTok-Event eintrifft, schlägt `execute_global_command()` den Trigger in `script_actions` nach, dann jeden Action-Namen in `HOOK_ACTIONS` und ruft den Handler auf.

## Hook testen

1. **Starte TikTok2Mc**: `python start.py`
   Der Bridge-Prozess lädt automatisch alle Hooks aus `src/hooks/`. In der Konsolenausgabe siehst du:
   ```
   [HOOK] Registered action: superjump
   ```

2. **Sende einen Test-Trigger**:
   ```bash
   python tests/send_trigger.py --event tiktok.follow --user TestUser
   ```

3. **Prüfe die Ausgabe**: In der Konsole sollte erscheinen:
   ```
   TestUser hat einen Supersprung ausgelöst!
   ```

   Wenn Minecraft verbunden ist (RCON konfiguriert), erhalten alle Spieler den Sprung-Boost-Effekt.

## Hook deaktivieren

Setze in der `config.yaml` des Hooks `enabled: false` oder deaktiviere den Hook über die GUI. Das System lädt deaktivierte Hooks nicht. Die `config.yaml`-Methode ist der empfohlene Weg — das Entfernen aus `src/hooks/` ist nur nötig, wenn der Hook dauerhaft gelöscht werden soll.

## Unterschied zum Plugin

| Aspekt | Hook | Plugin |
|---|---|---|
| Ausführungsort | Läuft **direkt im Bridge-Prozess** | Eigener Subprozess |
| Kommunikation | **Direkter Funktionsaufruf** (kein HTTP) | HTTP-API (`send_command`, `api_post`) |
| Lebenszyklus | Wird beim Start geladen, lebt bis zum Ende | Wird als Subprozess gestartet/gestoppt |
| Latenz | Millisekunden (kein Netzwerk) | Höher (Polling-Intervall 1s) |
| Komplexität | Einfach, nur eine Funktion | Vollständige Klasse mit Threads |
| Anwendungsfall | Einfache `$`-Befehle | Komplexe Logik, GUI, Zustand |

## Häufige Fehler

| Fehler | Ursache | Lösung |
|---|---|---|
| Hook wird nicht geladen | `register()`-Funktion fehlt | Füge `def register(api):` hinzu |
| `$superjump` tut nichts | Action-Name in `actions.mca` stimmt nicht mit `register_action()` überein | Prüfe beide Namen auf Tippfehler |
| Import-Fehler | Nicht erlaubtes Modul importiert (`os`, `sys`, etc.) | Verwende nur die Hook-API |
| `api.rcon_enqueue()` ohne Wirkung | RCON nicht konfiguriert oder Minecraft nicht verbunden | Prüfe `config.yaml`: `rcon.host`, `rcon.port`, `rcon.password` |
| Trigger wird nicht ausgelöst | Trigger-Name nicht in `actions.mca` definiert | Füge `follow: $superjump` in die `actions.mca` ein |

## Nächste Schritte

Im nächsten Kapitel lernst du die [Hook-Struktur & Manifest](./ch04-02-hook-structure-and-manifest.md) im Detail kennen.
