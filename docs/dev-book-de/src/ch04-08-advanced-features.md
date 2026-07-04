# Fortgeschrittene Features (Hook)

Dieses Kapitel beschreibt fortgeschrittene Muster für die Hook-Entwicklung.

## Trigger-Verkettung

Ein Hook kann andere Trigger auslösen. Das ermöglicht komplexe Abläufe aus einfachen Bausteinen.

### Bestehenden Trigger weiterleiten

```python
def register(api):
    def geschenk_gross(user, trigger, context):
        api.rcon_enqueue([f"say Riesiges Geschenk von {user}!"])
        api.enqueue_trigger("follow", user)

    api.register_action("grosses-geschenk", geschenk_gross)
```

In der `actions.mca`:

```
5655: $grosses-geschenk
```

Bei Gift `5655` wird zuerst die RCON-Nachricht gesendet, dann der `follow`-Trigger ausgelöst (mit allen zugehörigen Aktionen).

### Eigenen Trigger anlegen

Du kannst eigene Trigger definieren, die nie automatisch von TikTok ausgelöst werden:

In der `actions.mca`:

```
dankeschoen: $dankeschoen; /playsound minecraft:entity.player.levelup master @a
```

Im Hook:

```python
def register(api):
    def geschenk(user, trigger, context):
        api.enqueue_trigger("dankeschoen", user)

    def dankeschoen(user, trigger, context):
        api.rcon_enqueue([f"say Danke {user}!"])

    api.register_action("geschenk", geschenk)
    api.register_action("dankeschoen", dankeschoen)
```

## Mehrere Aktionen in einem Hook

Ein Hook kann beliebig viele Aktionen registrieren:

```python
def register(api):
    def bei_follow(user, trigger, context):
        api.rcon_enqueue([f"say {user} folgt jetzt!"])

    def bei_grossem_geschenk(user, trigger, context):
        api.rcon_enqueue([
            "summon minecraft:firework_rocket ~ ~ ~",
            f"say Danke {user}!",
        ])

    api.register_action("follow_effekt", bei_follow)
    api.register_action("geschenk_effekt", bei_grossem_geschenk)
```

## Ein Handler für mehrere Befehle

Ein Handler kann unter mehreren Namen registriert werden:

```python
def register(api):
    def power_up(user, trigger, context):
        effekte = {
            "superjump": "minecraft:jump_boost",
            "superrun": "minecraft:speed",
            "superheal": "minecraft:regeneration",
        }
        effekt = effekte.get(trigger)
        if effekt:
            api.rcon_enqueue([f"effect give @a {effekt} 10 5 true"])

    api.register_action("superjump", power_up)
    api.register_action("superrun", power_up)
    api.register_action("superheal", power_up)
```

## Schutz vor Endlosschleifen

Das System erkennt Trigger-Verkettungen, die zu Endlosschleifen führen:

- Maximal 3 Ketten-Schritte
- Nach Überschreitung wird der Trigger dauerhaft für die Sitzung gesperrt
- Der Fehler wird protokolliert

> [!WARNING]
> Rufe niemals `enqueue_trigger` mit dem eigenen Trigger-Namen auf. Das führt zur dauerhaften Sperrung des Triggers für die gesamte Sitzung.
