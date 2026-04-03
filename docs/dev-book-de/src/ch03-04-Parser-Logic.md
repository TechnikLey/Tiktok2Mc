## Wie wird das Format verarbeitet?

### Der Ablauf beim Programmstart

Die Verarbeitung der `actions.mca` Datei findet **beim Start** statt:

```
1. Program Start
   ↓
2. Datei "actions.mca" laden
   ↓
3. Validator prüft auf Fehler
   ↓
4. Parser zerlegt jede Zeile:
   - Trigger auslesen
   - Command-Typ bestimmen (/, !, $)
   - Wiederholungen (x) extrahieren
   ↓
5. In-Memory-Dictionary aufbauen:
   ACTIONS = {
     "follow": [...],
     "8913": [...],
     "likes": [...]
   }
   ↓
6. Fertig! Datei ist in den RAM geladen
   ↓
7. Worker-Thread: Nachschlage ist sehr schnell!
```

---

### Code-Beispiel: Parser Logik

```python
def parse_actions(filename):
    actions = {}
    
    with open(filename) as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            
            # Kommentare & leere Zeilen überspringen
            if not line or line.startswith("#"):
                continue
            
            # Format parsen: "trigger:command x repeat"
            if ":" not in line:
                print(f"[ERROR] Zeile {line_num} hat kein ':' Trennzeichen")
                continue
            
            trigger, cmd_part = line.split(":", 1)
            trigger = trigger.strip()
            
            # Wiederholungen extrahieren
            repeat = 1
            if " x" in cmd_part:
                cmd_part, repeat_str = cmd_part.rsplit(" x", 1)
                try:
                    repeat = int(repeat_str)
                except ValueError:
                    print(f"[ERROR] Zeile {line_num}: x nach keine Zahl")
                    continue
            
            # Command-Typ bestimmen
            cmd = cmd_part.strip()
            if cmd.startswith("/"):
                cmd_type = "vanilla"
                body = cmd[1:].strip()
            elif cmd.startswith("!"):
                cmd_type = "plugin"
                body = cmd[1:].strip()
            elif cmd.startswith("$"):
                cmd_type = "built_in"
                body = cmd[1:].strip()
            else:
                print(f"[ERROR] Zeile {line_num}: Ungültiger Prefix")
                continue
            
            # Speichern
            if trigger not in actions:
                actions[trigger] = []
            
            actions[trigger].append({
                "type": cmd_type,
                "command": body,
                "repeat": repeat
            })
    
    return actions
```

---

### Command-Typ Differenzierung

Beim Parsen wird unterschieden zwischen 3 Typen:

**Typ 1: Vanilla (`/`)**

```python
if cmd.startswith("/"):
    kind = "vanilla"
    body = cmd[1:]  # "/" entfernen
```

→ Wird in `.mcfunction`-Datei gespeichert
→ Kann vom Minecraft-Server direkt ausgeführt werden

---

**Typ 2: Plugin (`!`)**

```python
elif cmd.startswith("!"):
    kind = "plugin"
    body = cmd[1:]  # "!" entfernen
```

→ Wird via RCON an Minecraft gesendet
→ Ist ein Custom/Plugin-Command (nicht Vanilla)

---

**Typ 3: Built-in (`$`)**

```python
elif cmd.startswith("$"):
    kind = "built_in"
    body = cmd[1:]  # "$" entfernen
```

→ Wird vom Programm selbst verarbeitet
→ Beispiel: `$random` wählt anderen Trigger

---

### Runtime: Nachschlagen sehr schnell

Wenn zur Laufzeit ein Event kommt:

```python
# Event-Handler sendet Trigger
trigger = "follow"

# Worker-Thread macht Nachschlag:
if trigger in ACTIONS:
    for action in ACTIONS[trigger]:
        execute(action["command"], repeat=action["repeat"])
```

**Super schnell!** Dictionary-Lookup ist sehr schnell.

Egal ob 10 oder 10.000 Actions definiert sind – das Nachschlagen ist **gleich schnell!**

---

### Warum `kind` wichtig ist

```python
# Kind bestimmt die Verarbeitung:

if kind == "vanilla":
    # Speichern in .mcfunction-Datei
    # Wird vom Server nativ ausgeführt
    save_to_mcfunction(body)

elif kind == "plugin":
    # Direkt via RCON an Server senden
    rcon_execute(body)

elif kind == "script":
    # Vom Programm interpretiert (z.B. $random)
    execute_built_in(body, source_user)
```

Die `kind`-Unterscheidung bestimmt, **wie** der Command ausgeführt wird!

---

### Performance-Hinweis

**Alle Command-Typen haben die gleiche Performance!**

Die Kosten einer Aktion hängen ab von:
- **Was** der Command macht (nicht **welcher** Type)
- Z.B. `/summon` dauert länger als `/say`
- Z.B. `!tnt 1000` dauert länger als `!tnt 1`

Type (/, !, $) ist aus Performence sicht egal!
<br> Es kommt auf denn Command an.

---

### Zusammenfassung

1. **Parser** zerlegt actions.mca einmal beim Start
2. **In-Memory-Dictionary** wird aufgebaut
3. **Command-Typen** werden klassifiziert (/, !, $)
4. **Runtime** = schnelle Dictionary-Lookups
5. **Keine Parsing zur Laufzeit** = mehr Performance