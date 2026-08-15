# RCON & Minecraft Communication

RCON (Remote Console) is the protocol through which the system communicates with the Minecraft server. It allows sending commands to the server as if they were entered in the server console.

## How Plugins and Hooks Use RCON

### In Plugins

Plugins do not have direct RCON access. They send Minecraft commands indirectly via the Event-Command-Mapper. A specialized service receives the event and executes the RCON command:

```python
# A plugin publishes an event that the Event-Command-Mapper
# forwards to a Minecraft command service.
self.api_post("/events", {
    "type": "minecraft.command",
    "data": {"command": "say Hello"}
})
```

> [!NOTE]
> There is **no built-in** `minecraft.command` → RCON mapping in `defaults/event_commands.yaml`. You must configure this mapping yourself if you want plugins to execute RCON commands via the Event-Command-Mapper.

Configure an entry in `event_commands.yaml` that maps this event to an RCON command (see [Event-Command-Mapper](./ch05-02-event-command-mapper.md) for details).

### In Hooks

Hooks have direct access to RCON via the Hook API:

```python
def my_handler(user, trigger, context):
    api.rcon_enqueue([
        f"say {user} triggered a command!",
        "effect give @a minecraft:speed 10 2 true",
    ])
```

## RCON Configuration

The RCON connection is configured in the global `config.yaml`:

```yaml
# The RCON host is the server_host address (default: 127.0.0.1)
server_host: "127.0.0.1"
rcon:
  enabled: true
  port: 25575
  password: "your-password"
```

## Important Notes

- RCON commands are sent asynchronously — execution order is guaranteed.
- The system automatically retries failed RCON commands (up to 3 attempts).
- If the connection drops, it will automatically reconnect.
- Minecraft server plugins (Bukkit, Paper, Spigot) can also be controlled via RCON.

## Limitations

- RCON has a limited command length (protocol limit).
- Many commands in a row can cause delays.
- The Minecraft server must have RCON enabled (see `server.properties`).
