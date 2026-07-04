# RCON & Minecraft-Kommunikation

RCON (Remote Console) ist das Protokoll, über das das System mit dem Minecraft-Server kommuniziert. Es erlaubt das Senden von Befehlen an den Server, als ob sie in der Server-Konsole eingegeben würden.

## Wie Plugins und Hooks RCON nutzen

### In Plugins

Plugins haben keinen direkten RCON-Zugriff. Sie senden Minecraft-Befehle indirekt über den Event-Command-Mapper. Ein spezialisierter Dienst empfängt das Event und führt den RCON-Befehl aus:

```python
# Ein Plugin veröffentlicht ein Event, das der Event-Command-Mapper
# an einen Minecraft-Befehl-Dienst weiterleitet.
self.api_post("/events", {
    "type": "minecraft.befehl",
    "data": {"befehl": "say Hallo"}
})
```

Konfiguriere dazu in der `event_commands.yaml` einen Eintrag, der dieses Event auf einen RCON-Befehl abbildet (siehe [Event-Command-Mapper](./ch05-02-event-command-mapper.md) für Details).

### In Hooks

Hooks haben direkten Zugriff auf RCON über die Hook-API:

```python
def mein_handler(user, trigger, context):
    api.rcon_enqueue([
        f"say {user} hat einen Befehl ausgelöst!",
        "effect give @a minecraft:speed 10 2 true",
    ])
```

## RCON-Konfiguration

Die RCON-Verbindung wird in der globalen `config.yaml` konfiguriert:

```yaml
rcon:
  host: "localhost"
  port: 25575
  password: "dein-passwort"
```

## Wichtige Hinweise

- RCON-Befehle werden asynchron gesendet – die Ausführungsreihenfolge ist garantiert.
- Das System wiederholt fehlgeschlagene RCON-Befehle automatisch (bis zu 3 Versuche).
- Bei Verbindungsabbrüchen wird automatisch neu verbunden.
- Minecraft-Server-Plugins (Bukkit, Paper, Spigot) können ebenfalls über RCON angesteuert werden.

## Einschränkungen

- RCON hat eine begrenzte Befehllänge (ca. 1400 Zeichen).
- Sehr viele Befehle hintereinander können zu Verzögerungen führen.
- Der Minecraft-Server muss RCON aktiviert haben (siehe `server.properties`).
