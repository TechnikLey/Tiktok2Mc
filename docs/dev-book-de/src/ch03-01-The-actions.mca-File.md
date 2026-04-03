# Die Datei `actions.mca`

> [!NOTE]
> In dieser und auch in anderen Dateien verwenden wir den Begriff „Plugin".
> Dabei gibt es zwei Bedeutungen: Plugins für Minecraft und Plugins für das Streaming-Tool.
> Welches Plugin gemeint ist, ergibt sich jeweils aus dem Kontext.

### Was ist die actions.mca?

Die `actions.mca` ist eine einfache Text-Datei, die festlegt, **was in Minecraft passiert**, wenn ein bestimmtes TikTok-Event eintrifft. Jede Zeile ist ein Mapping von einem Trigger zu einem oder mehreren Commands:

```
TRIGGER:<TYPE>COMMAND xANZAHL
```

- **TRIGGER** = Name oder ID (z.B. `follow`, `8913`)
- **TYPE** = Präfix: `/` (Vanilla), `!` (Plugin/Custom), `$` (Spezialfunktion)
- **COMMAND** = Der auszuführende Befehl
- **xANZAHL** = Optional: Command N-mal wiederholen

Die vollständige Syntax-Referenz findest du im nächsten Kapitel → [Syntax & Befehle](./ch03-02-Structure.md)

---

### Wo liegt die Datei?

| Pfad | Zweck |
|------|-------|
| `defaults/actions.mca` | Vorlage mit Beispiel-Mappings |
| `data/actions.mca` | Wird tatsächlich geladen und genutzt |

Beim ersten Start wird `defaults/actions.mca` nach `data/actions.mca` kopiert. Ab dann wird nur noch `data/actions.mca` verwendet.

---

### Validierung: Fehler werden früh erkannt

Beim Start parst `generate_datapack()` in `main.py` jede Zeile der `actions.mca`:

```python
# main.py - generate_datapack():
for line_num, original_line in enumerate(f, 1):
    line = original_line.split("#", 1)[0].strip()  # Kommentare entfernen
    if not line or ":" not in line:
        continue
    trigger, full_cmd_line = map(str.strip, line.split(":", 1))
    # ...
    if not cmd.startswith(("/", "!", "$")):
        print(f"[ERROR] Ungültiger Befehl ohne Präfix in Zeile {line_num}: {cmd}")
```

**Jeder Command braucht ein Präfix** (`/`, `!` oder `$`). Zeilen ohne gültiges Präfix werden beim Start mit einer Fehlermeldung übersprungen.

---

### Ein echtes Beispiel

Aus `defaults/actions.mca` (verkürzt):

```
# Basic Events
follow:/give @a minecraft:golden_apple 7
like_2:/clear @a *; /kill @a
likes:/execute at @a run summon minecraft:creeper ~ ~ ~ x2

# Gifts (numerische TikTok Gift-IDs)
5655:!tnt 2 0.1 2 Notch
16111:/give @a minecraft:diamond
5487:/give @a minecraft:totem_of_undying

# Special ($random wählt zufällig einen anderen Trigger)
16071:$random

# Complex (mehrere Command-Typen gemischt)
11046:/clear @a *; /execute at @a run summon minecraft:wither ~ ~ ~ x20; !tnt 20 0.1 2 Notch
```

**Was hier passiert:**
- `follow` → Goldene Äpfel für alle Spieler
- `like_2` → Inventar leeren + alle Spieler töten
- `likes` → 2 Creeper spawnen (Vanilla mit `x2`)
- `16071` → Zufälliger Trigger (`$random`)
- `11046` → Drei Commands nacheinander: Clear, 20 Wither, TNT

---

### Der Ablauf: Vom Event zum Minecraft-Befehl

```
Event-Handler:
  trigger_queue.put_nowait(
    ("follow", "anna_123")
  )                                ← TRIGGER in Queue!
        ↓
Worker-Thread:
  trigger, user = trigger_queue.get()
  → "follow" ist in valid_functions  ← Trigger bekannt!
        ↓
Datapack / RCON:
  follow.mcfunction enthält:
  give @a minecraft:golden_apple 7   ← Ausführung!
        ↓
ERGEBNIS: Alle bekommen goldene Äpfel
```

---

### Zusammenfassung

| Konzept | Erklärung |
|---------|-----------|
| **Format** | `TRIGGER:<TYPE>COMMAND xANZAHL` |
| **Dateien** | `defaults/actions.mca` (Vorlage) → `data/actions.mca` (aktiv) |
| **Validierung** | `generate_datapack()` prüft Syntax beim Start |
| **Ablauf** | Event → Queue → Worker → RCON/Datapack → Minecraft |

→ [Nächstes Kapitel: Syntax & Befehle)](./ch03-02-Structure.md)