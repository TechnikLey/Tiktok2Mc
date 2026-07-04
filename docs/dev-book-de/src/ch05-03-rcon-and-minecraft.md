# RCON & Minecraft-Kommunikation

RCON (Remote Console) ist das Protokoll, über das das System mit dem Minecraft-Server kommuniziert. Es erlaubt das Senden von Befehlen an den Server, als ob sie in der Server-Konsole eingegeben würden.

## Wie Plugins und Hooks RCON nutzen

### In Plugins

Plugins kommunizieren indirekt mit Minecraft. Sie senden Befehle über das Event-System oder den Event-Command-Mapper:

```python
# Ein Plugin kann über den Event-Command-Mapper
# Minecraft-bezogene Befehle an spezialisierte Komponenten senden.
self.api_post("/events", {
    "type": "minecraft.befehl",
    "data": {"befehl": "say Hallo"}
})
```

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
