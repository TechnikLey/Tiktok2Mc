## Funktion des `$random`-Befehls

### Was ist `$random`?

`$random` ist ein **eingebauter spezieller Command**, der **zufällig einen anderen Trigger ausführt**.

Beispiel:

```
likes:$random
```

Wenn ein Like-Event kommt → statt immer das Gleiche zu tun → **wähle zufällig einen anderen Trigger!**

---

### Praktischer Use-Case

Du magst chaotische Live-Streams? Dann:

```
likes:$random         # Jedes Like-Event einen ZUFÄLLIGEN Effekt!
```

**Resultat:** Der Stream ist unvorhersehbar und lustig!

---

### Wie funktioniert `$random` intern?

```python
# 1. Parser sieht: "likes:$random"
# → Speichert: kind = "built_in", body = "random"

# 2. Zur Laufzeit kommt Like-Event:
actions = ACTIONS["likes"]
for action in actions:
    if action["kind"] == "script":
        if action["body"] == "random":
            # Sammle alle möglichen Trigger
            possible_triggers = get_all_triggers_except("likes")
            
            # Wähle EINEN zufällig aus
            chosen = random.choice(possible_triggers)
            
            # Führe DIESEN aus
            execute_trigger(chosen)
```

---

### Beispiel: Zufälliger Trigger Pool

```
# Definition
follow:/say Willkommen!
5655:/give @a diamond
8913:/summon minecraft:evoker
likes:$random  ← Startet die Random auswahl

# Wenn likes:$random kommt:
# 0% Chance: /say Willkommen!
# 50% Chance: /give @a diamond
# 50% Chance: /summon minecraft:evoker
# 0% Chance: $random
```

> [!NOTE]
> Der Befehl `/say Willkommen!` wird niemals ausgeführt,
> da `follow` standardmäßig in der Ausschlussliste steht.
> Welche Trigger ausgeschlossen werden, ist in `config.yaml` unter
> `Gifts > random_exclude` konfigurierbar.
> Trigger, die selbst `$random` enthalten, werden **immer** automatisch ausgeschlossen.

---

### Besonderheiten

**1. Selbst-Rekursion vermieden**

Trigger, die selbst `$random` enthalten, werden **immer** automatisch aus dem Pool entfernt — unabhängig von der Konfiguration.

**2. Ausschlussliste konfigurierbar**

In `config.yaml` unter `Gifts > random_exclude` kann festgelegt werden, welche Trigger zusätzlich ausgeschlossen werden:

```yaml
Gifts:
  random_exclude:
    - likes
    - like_2
    - follow
```

Standardmäßig sind `likes`, `like_2` und `follow` ausgeschlossen. Du kannst diese Liste beliebig anpassen.

**3. Alle Trigger sind gleich wahrscheinlich**

```python
chosen = random.choice(possible_triggers)  # Gleichverteilung
```

Jeder Trigger hat die **gleiche Chance** gewählt zu werden.

---

### Wann brauchst du das?

- **Chaos-Events** auf dem Stream
- **Überraschungs-Effekte** bei Milestones
- **Gameplay-Variabilität** (nicht immer das Gleiche)
- **Mini-Games** (zufällige Belohnungen)

---

### Zusammenfassung

`$random` ist ein **Meta-Command**, der:
- Zufällig einen anderen Trigger wählt
- Zur Laufzeit evaluiert wird (nicht beim Start!)

> [!NOTE]
> In Zukunft werden voraussichtlich weitere `$`-Commands hinzugefügt.
> Diese werden jedoch nicht mehr in der Entwicklerdokumentation beschrieben,
> sondern nur noch kurz in der Nutzerdokumentation erwähnt.
> Wenn du dich für ihre Funktionsweise interessierst, musst du den Code selbst einsehen und nachvollziehen.

**Nächstes Kapitel:** Wie schreibst du deinen eigenen `$`-Command?

→ [Eigenen $ Command](./ch03-06-Creating-Your-Own-$-Command.md)