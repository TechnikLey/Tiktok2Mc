## Funktion des `$random`-Befehls

### Was ist `$random`?

`$random` ist ein **Event-Hook-Command, der mit dem Streaming Tool ausgeliefert wird**, und **zufällig einen anderen Trigger ausführt**.

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

`$random` ist als Event-Hook in `src/event_hooks/random.py` implementiert. Beim Start registriert der Hook einen Handler via `api.register_action("random", random_handler)`. Wenn ein TikTok-Event `$random` auslöst:

```python
# 1. Parser sieht: "likes:$random"
# → Registriert "random" als $-Command, der mit seinem Hook verknüpft ist

# 2. Beim Start registriert event_hooks/random.py den Handler:
api.register_action("random", random_handler)

# 3. Zur Laufzeit kommt Like-Event → Handler wird aufgerufen:
def random_handler(user, trigger, context):
    # Sammle alle gültigen Trigger des aktuellen Kontexts
    all_valid = api.get_valid_functions()
    
    # Lese den random_triggers-Konfigurationsabschnitt
    cfg = api.config.get("random_triggers", {})
    mode = cfg.get("mode", "deny-all")
    configured = cfg.get("triggers", [])
    
    # Baue den Kandidatenpool basierend auf dem Filtermodus
    candidates = []
    for func in all_valid:
        if mode == "deny-all":
            if func not in configured:  # Nur die gelisteten Trigger ausschließen
                candidates.append(func)
        else:
            if func in configured:  # Nur die gelisteten Trigger erlauben
                candidates.append(func)
    
    # Wähle EINEN zufällig aus und stelle ihn in die Queue
    if candidates:
        chosen = random.choice(candidates)
        api.enqueue_trigger(chosen, user)
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
> `random_triggers` konfigurierbar. Mit `mode: deny-all` werden nur die
> gelisteten Trigger ausgeschlossen, mit `mode: allow-all` werden alle
> außer den gelisteten ausgeschlossen.

---

### Besonderheiten

**1. Loop-Schutz**

Wenn `$random` einen Trigger wählt, der selbst `$random` enthält (oder einen anderen Hook, der zurückruft), verhindert die Ketten-Tiefenbegrenzung (3 Ebenen) Endlosschleifen. Nach Überschreiten des Limits wird der Trigger für die aktuelle Sitzung dauerhaft gesperrt.

**2. Trigger-Filter konfigurierbar**

In `config.yaml` unter `random_triggers` kann festgelegt werden, welche Trigger erlaubt oder blockiert werden:

```yaml
random_triggers:
  mode: deny-all
  triggers:
    - likes
    - like_2
    - follow
```

Bei `deny-all` werden nur die gelisteten Trigger von `$random` ausgeschlossen.  
Bei `allow-all` sind nur die gelisteten Trigger für `$random` verfügbar (alle anderen werden ausgeschlossen).

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
> Da `$random` seit v0.5.0 als Standard-Event-Hook implementiert ist, kannst du seinen
> Quellcode unter `src/event_hooks/random.py` als praxisnahes Beispiel für die Hook-API studieren.

**Nächstes Kapitel:** Wie schreibst du deinen eigenen `$`-Command?

→ [Eigenen $ Command](./ch03-06-Creating-Your-Own-$-Command.md)