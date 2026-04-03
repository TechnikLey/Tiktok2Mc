# Syntax & Befehle

### Aufbau einer Zeile

```
TRIGGER:<TYPE>COMMAND xANZAHL
```

```
trigger_name:<type>command xAnzahl
│            │     │       │
│            │     │       └─→ Wiederholung (optional)
│            │     └───────→ Der eigentliche Befehl
│            └───────────→ Präfix: / ! oder $
└─────────────→ Der Name, den Event-Handler nutzen
```

Jeder Teil ist wichtig:

| Teil | Bedeutung | Beispiel |
|------|-----------|----------|
| **TRIGGER** | Eindeutiger Name oder ID | `8913`, `follow`, `likes` |
| **:** | Trennzeichen | `:` (immer erforderlich) |
| **\<TYPE\>** | Art des Commands | `/`, `!`, `$`, `>>` |
| **COMMAND** | Was soll passieren? | `give @a diamond`, `tnt 2 0.1 2` |
| **xANZAHL** | Wie oft? (Optional) | `x3`, `x10` (ohne x = 1×) |

---

### Praktische Beispiele mit Erklärung

**Beispiel 1: Einfaches Gift mit Wiederholung**

```
8913:/execute at @a run summon minecraft:evoker ~ ~ ~ x3
```

- **8913** = Gift-ID (evoker Gift)
- **:** = Trennzeichen
- **/** = Vanilla Minecraft Command
- **execute at @a run summon minecraft:evoker ~ ~ ~** = Was soll passieren
- **x3** = Diese Aktion 3x hintereinander

**Resultat:** Der Command wird **3x ausgeführt** = 3 Evoker spawnen!

---

**Beispiel 2: Follow ohne Wiederholung**

```
follow:/give @a minecraft:golden_apple 7
```

- **follow** = Spezial-Trigger für Follow-Events
- **:** = Trennzeichen
- **/** = Vanilla Command
- **give @a minecraft:golden_apple 7** = Was soll passieren
- *(kein x)* = Nur 1x ausführen

**Resultat:** Alle Spieler bekommen 1x 7 goldene Äpfel.

---

**Beispiel 3: Custom Command (Plugin)**

```
6267:!tnt 600 0.1 2 Notch
```

- **6267** = Gift-ID (TNT Gift)
- **:** = Trennzeichen
- **!** = Custom/Plugin Command (nicht Vanilla)
- **tnt 600 0.1 2 Notch** = Was soll passieren (custom Syntax!)
- **(kein x)** = 1x ausführen

**Resultat:** Plugin-Command `!tnt` wird ausgeführt.

---

**Beispiel 4: Spezial-Funktion**

```
16071:$random
```

- **16071** = Gift-ID
- **:** = Trennzeichen
- **$** = Spezial-Funktion (kein normaler Command!)
- **random** = Wähle zufällig einen anderen Trigger
- **(kein x)** = 1x ausführen

**Resultat:** Ein **zufällig gewählter anderer Trigger** wird ausgeführt!


**Beispiel 5: Overlay-Ausgabe (Bildschirmtext)**

```
follow: >>Neuer Follower!|{user} folgt dir jetzt!|5
```

- **follow** = Spezial-Trigger für Follow-Events
- **:** = Trennzeichen
- **>>** = Overlay-Ausgabe (Text wird im Stream eingeblendet, kein Minecraft-Command!)
- **Neuer Follower!|{user} folgt dir jetzt!|5** = Text, Untertitel und Dauer (Sekunden), durch `|` getrennt
- **x** wird hier nicht unterstützt

**Resultat:**
Im Stream erscheint ein Overlay mit dem Text `Neuer Follower!` und dem Untertitel `{user} folgt dir jetzt!` für 5 Sekunden.

> [!NOTE]
> Die Dauer ist optional, Standard sind 3 Sekunden.
> `{user}` wird automatisch durch den Namen des Auslösers ersetzt (bei Likes z.B. `Community`).

---

### Trigger-Typen erklärt

**1. Gift-IDs (Zahlen)**

```
5655:!tnt 2 0.1 2 Notch
8913:/execute at @a run summon minecraft:evoker ~ ~ ~ x3
```

Gift-IDs sind numerisch und eindeutig für jeden Geschenktyp auf TikTok.
Die komplette Liste aller Gift-IDs findest du in `core/gifts.json`.

---

**2. Special Trigger: follow**

```
follow:/give @a minecraft:golden_apple 7
```

Reserviertes Wort für Follow-Events. Wird **immer** als `follow` geschrieben (Kleinbuchstaben).

---

**3. Like-Trigger**

```
likes:/execute at @a run summon minecraft:creeper ~ ~ ~ x2
like_2:/clear @a *; /kill @a
```

Vordefinierte Trigger für Like-Events:
- `likes` = Standard-Like-Event (Häufigkeit konfigurierbar in `config.yaml`)
- `like_2` = Zusätzlicher Like-Trigger (z.B. für Meilensteine)

Können in `config.yaml` konfiguriert werden.

---

### Command-Typen erklärt

**Typ 1: Vanilla Commands (`/`)**

```
/give @a minecraft:diamond
/execute at @a run summon minecraft:wither ~ ~ ~
/clear @a *
/say Willkommen!
```

Beginnt mit `/` → Standard Minecraft-Befehl. Wird in eine `.mcfunction`-Datei geschrieben und über das Datapack ausgeführt.

---

**Typ 2: Plugin Commands (`!`)**

```
5655:!tnt 2 0.1 2 Notch
6267:!tnt 600 0.1 2 Notch
```

Beginnt mit `!` → Custom-Befehl. Wird **direkt per RCON** an den Server gesendet, **nicht** in eine `.mcfunction`-Datei geschrieben.

→ [Warum der Unterschied? → Der Nutzen der .mcfunction-Dateien](./ch03-08-The-Use-of-mcfunction-Files.md)

---

**Typ 3: Spezial-Funktionen (`$`)**

```
16071:$random
```

Beginnt mit `$` → Interne Spezialfunktion des Streaming-Tools. Aktuell ist nur `$random` implementiert.

`$random` wählt einen **zufälligen anderen Trigger** aus und führt ihn aus. Dabei werden Endlos-Schleifen verhindert: Trigger mit `$random` sowie Basis-Trigger wie `likes`, `like_2` und `follow` werden automatisch ausgeschlossen.

→ [Details zu $random → Funktion des $random Commands](./ch03-05-Function-of-the-$random-Command.md)

---

### Wiederholungen: Das xANZAHL-System

```
x3    = 3× hintereinander
x10   = 10× hintereinander
x100  = 100× hintereinander
```

Ohne `x` wird der Command genau **1×** ausgeführt.

```
8913:/execute at @a run summon minecraft:evoker ~ ~ ~ x3
```

Ist **äquivalent** zu:

```
/execute at @a run summon minecraft:evoker ~ ~ ~
/execute at @a run summon minecraft:evoker ~ ~ ~
/execute at @a run summon minecraft:evoker ~ ~ ~
```

→ 3 Evoker spawnen statt 1.

---

**Mehrere Commands mit `;` kombinieren:**

```
11046:/clear @a *; /execute at @a run summon minecraft:wither ~ ~ ~ x20; !tnt 20 0.1 2 Notch
```

Commands mit `;` trennen → alle werden der Reihe nach ausgeführt!
<br> Von Links nach Rechts

---

### Kommentare und Deaktivieren

Was nach `#` kommt, wird **ignoriert**:

```
#8913:/give @a minecraft:diamond
5655:/give @a minecraft:emerald
```

- Zeile 1 ist **auskommentiert** (wird nicht gelesen)
- Zeile 2 ist **aktiv** (wird gelesen)

**Nutzen:** Zum Deaktivieren ohne zu löschen oder um etwas dazu zu schreiben

---

### Gültige und ungültige Syntax

**Gültige Trigger-Namen:**

```
✓ Buchstaben (a-z, A-Z)
✓ Zahlen (0-9)
✓ Unterstriche (_)

✗ Leerzeichen
✗ Sonderzeichen außer _
✗ Umlaute (ä, ö, ü)
```

**✓ RICHTIG:**
```
follow:/give @a minecraft:golden_apple 7
8913:/execute at @a run summon minecraft:evoker ~ ~ ~ x3
16071:$random
5655:!tnt 2 0.1 2 Notch
```

**✗ FALSCH:**
```
follow /give @a diamond           # ← Fehlt :
8913:               /give @a diamond  # ← Leerzeichen nach :
likes $random                        # ← Fehlt :
follow:/give @a diamond x          # ← x ohne Zahl
```

---

### Zusammenfassung

| Concept | Erklärung |
|---------|-----------|
| **Trigger** | Gift-ID, `follow`, `likes`, `like_2` |
| **Command-Typen** | `/` (Vanilla → mcfunction), `!` (Plugin → RCON), `$` (Spezial) |
| **xANZAHL** | Command N-mal wiederholen |
| **Semikolon** | Mehrere Commands in einer Zeile |
| **Kommentare** | `#` zum Deaktivieren/Dokumentieren |

→ [Nächstes Kapitel: Design-Entscheidungen](./ch03-03-Design-Decisions.md)