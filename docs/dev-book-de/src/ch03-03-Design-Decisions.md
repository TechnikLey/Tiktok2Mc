## Warum ist das Format so aufgebaut?

### Design-Entscheidung

Das Format `TRIGGER:<TYPE>COMMAND xREPEAT` ist nicht zufällig gewählt. Es ist ein Kompromiss zwischen:

- **Einfachheit** (User können es verstehen)
- **Maschinenlesbarkeit** (Code kann es parsen)
- **Flexibilität** (verschiedene Command-Typen)

---

### Alternativen (und warum sie nicht gewählt wurden)

**Alternative 1: JSON-Format**

```json
{
  "triggers": [
    {
      "id": "follow",
      "command": "/give @a diamond",
      "repeat": 1
    }
  ]
}
```

**Pro:** Strukturiert, leicht zu parsen
**Con:** Zu streng, User machen viele Fehler mit Klammern/Kommas

---

**Alternative 2: Config-basiert (YAML)**

```yaml
actions:
  follow:
    command: /give @a diamond
    repeat: 1
```

**Pro:** Lesbar
**Con:** Zu viel Setup

---

**Alternative 3: SQL-Datenbank**

```sql
INSERT INTO actions VALUES ('follow', '/give @a diamond', 1);
```

**Pro:** Mächtig, Daten persistent
**Con:** Overkill, braucht externe Tools

---

### Das gewählte Format: Warum es besser ist

```
follow:/give @a diamond x1
```

**Vorteile:**

1. **Eine Zeile pro Aktion** – Einfach zu verstehen
2. **Trennung mit `:` und `x`** – Klare Struktur ohne Klammern
3. **Minimal, prägnant** – Anfänger verstehen es schnell
4. **Nicht zu streng** (Optional: `x` kann fehlen)
5. **Kommentar-Support** (#) – Lines einfach deaktivieren
6. **Kompatibel** – Funktioniert in regulären Text-Editoren

---

### Parsen ist einfach

Für den Code:

```python
# Beispiel: "follow:/give @a diamond x3"
parts = line.split(":")
trigger = parts[0]           # "follow"
cmd_with_repeat = parts[1]   # "/give @a diamond x3"

# Repeat extrahieren
if "x" in cmd_with_repeat:
    cmd, repeat = cmd_with_repeat.rsplit("x", 1)
    repeat_count = int(repeat)
else:
    cmd = cmd_with_repeat
    repeat_count = 1

# Typ bestimmen
if cmd.startswith("/"):
    kind = "vanilla"
elif cmd.startswith("!"):
    kind = "plugin"
elif cmd.startswith("$"):
    kind = "built_in"
```

**Einfach, effizient, robust!**