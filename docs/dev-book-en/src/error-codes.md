# Error Codes

Every error in the system has a stable, documented code in the format `SUBSYSTEM-NNNN`.

## Subsystems

| Prefix | Subsystem |
|--------|-----------|
| `CORE` | Core runtime / generic infrastructure |
| `PLUGIN` | Plugin system |
| `GUI` | Graphical user interface |
| `API` | REST API / FastAPI |
| `NETWORK` | Network / HTTP / WebSocket |
| `CONFIG` | Configuration loading / validation |
| `OVERLAY` | Overlay subsystem |
| `LIFECYCLE` | Process lifecycle / supervisor |
| `MC` | Minecraft server / RCON |
| `TIKTOK` | TikTok Live connection / events |
| `HOOK` | Hook system |
| `WATCHER` | File / directory watchers |
| `WORKER` | Background worker threads / tasks |
| `VALIDATE` | Validation subsystem |
| `DIAG` | Diagnostics / health |
| `SHUTDOWN` | Shutdown procedures |
| `STARTUP` | Startup procedures |
| `SECURITY` | Authentication / sandbox |
| `BACKUP` | Backup subsystem |
| `UPDATE` | Update subsystem |
| `SANDBOX` | Plugin sandbox |
| `HEARTBEAT` | Heartbeat monitoring |

## Severity Levels

| Level | Meaning |
|-------|-----------|
| `DEBUG` (0) | Diagnostic detail, no action needed |
| `INFO` (1) | Normal operation, informational |
| `NOTICE` (2) | Normal but significant condition |
| `WARNING` (3) | Potential issue, should be reviewed |
| `ERROR` (4) | Functionality impaired, action required |
| `CRITICAL` (5) | Severe failure, immediate attention needed |
| `FATAL` (6) | Process will terminate |

## Important Error Codes

The complete, machine-readable list is available via `GET /api/v1/diagnostics/error-codes`.

### HOOK (Hook System)

| Code | Message | Description |
|------|---------|--------------|
| `HOOK-0001` | Hook manifest missing or invalid | `hook.json` is missing, unreadable, or invalid |
| `HOOK-0002` | Hook main.py not found | The hook directory lacks a `main.py` entry point |
| `HOOK-0003` | Hook imports disallowed module | The hook imports a module not in the allowed list |
| `HOOK-0004` | Hook failed to load | `main.py` raised an exception during loading |
| `HOOK-0005` | Hook registration failed | The `register()` function raised an exception |
| `HOOK-0006` | Hook script action failed | A hook script action raised an exception during execution |
| `HOOK-0007` | Hook has no register() function | `main.py` does not define a `register()` function |
| `HOOK-0008` | Hook lifecycle callback failed | An `on_live_start`/`on_live_end`/`on_unload` callback raised an exception |
| `HOOK-0009` | Hook permission denied | A guarded HookAPI call lacked the required `permissions` entry in `hook.json` |
| `HOOK-0010` | Hook timer callback failed | A `register_timer()` callback raised an exception; the timer keeps running |

### PLUGIN (Plugin System)

| Code | Message | Description |
|------|---------|--------------|
| `PLUGIN-0001` | Failed to initialize plugin | Plugin error during initialization |
| `PLUGIN-0002` | Plugin process crashed | Plugin subprocess exited unexpectedly |
| `PLUGIN-0003` | Plugin tick handler failed | `on_tick()` threw an exception |
| `PLUGIN-0004` | Plugin command handler failed | A command handler threw an exception |
| `PLUGIN-0005` | Plugin directory not found | The plugins directory does not exist or is inaccessible |
| `PLUGIN-0006` | Plugin manifest invalid | `plugin.json` is missing, unreadable, or invalid |
| `PLUGIN-0007` | Plugin disabled by configuration | Plugin is present but disabled in the registry or config |
| `PLUGIN-0008` | Plugin sandbox violation detected | Plugin exceeded its sandbox limits |
| `PLUGIN-0009` | Plugin executable not found | The compiled plugin executable is missing |
| `PLUGIN-0010` | Plugin discovery failed | Plugin discovery encountered an error |
| `PLUGIN-0011` | Plugin health check failed | Plugin process died or became unresponsive |
| `PLUGIN-0012` | Plugin failed to register overlay | Overlay HTML could not be registered with the API |
| `PLUGIN-0013` | Plugin state push failed | State could not be pushed to the API |
| `PLUGIN-0014` | Plugin command fetch failed | Fetching commands from the API failed |
| `PLUGIN-0015` | Plugin heartbeat missing | Plugin stopped sending heartbeat pings |
| `PLUGIN-0016` | Plugin failed to stop gracefully | Plugin did not stop within the expected timeout |
| `PLUGIN-0017` | Plugin command queue full | Plugin's command queue reached maximum capacity |

### CONFIG (Configuration)

| Code | Message | Description |
|------|---------|--------------|
| `CONFIG-0001` | Configuration file not found | `config/config.yaml` does not exist |
| `CONFIG-0002` | Configuration file has invalid YAML syntax | YAML syntax error |
| `CONFIG-0003` | Configuration key missing, using default | A key was missing and a default value was used |
| `CONFIG-0004` | Configuration validation warning | A configuration value did not pass validation |
| `CONFIG-0005` | Runtime configuration reload failed | Reloading configuration at runtime failed |
| `CONFIG-0006` | Duplicate command keys detected in config | Duplicate keys in commands_config sections |
| `CONFIG-0007` | Comment command prefix collision | Two command groups use the same prefix |
| `CONFIG-0008` | Plugin configuration missing or invalid | A plugin's `config.yaml` could not be loaded |

### MC (Minecraft / RCON)

| Code | Message | Description |
|------|---------|--------------|
| `MC-0001` | Minecraft server JAR not found | `server.jar` is missing from the instance directory |
| `MC-0002` | Java runtime not available | No Java 17+ runtime available |
| `MC-0003` | Minecraft server exited with non-zero code | Server process exited with an error code |
| `MC-0004` | RCON connection failed | RCON connection to the server failed |
| `MC-0005` | RCON command failed | An RCON command execution returned an error |
| `MC-0006` | RCON command dropped after retries | Command failed multiple times and was dropped |
| `MC-0007` | RCON queue full | Queue full, command discarded |
| `MC-0008` | RCON password not set | RCON enabled but no password configured |
| `MC-0009` | MinecraftServerAPI plugin disabled | MinecraftServerAPI plugin could not be activated |
| `MC-0010` | MinecraftServerAPI config failed to write | Writing the API config file failed |
| `MC-0011` | Minecraft server properties update failed | Writing `server.properties` failed |

### TIKTOK (TikTok Live)

| Code | Message | Description |
|------|---------|--------------|
| `TIKTOK-0001` | TikTok Live connection failed | Connection to TikTok Live failed |
| `TIKTOK-0002` | TikTok Live disconnected | Connection dropped (auto-reconnect active) |
| `TIKTOK-0003` | TikTok event handler failed | An event handler raised an exception |
| `TIKTOK-0004` | TikTok event publishing failed | Publishing an event to the EventBus failed |
| `TIKTOK-0005` | TikTok bridge worker crashed | A bridge worker (trigger/RCON/event bridge) crashed |

### CORE (General)

| Code | Message | Description |
|------|---------|--------------|
| `CORE-0001` | Unhandled exception in main thread | Fatal exception in main thread |
| `CORE-0002` | Unhandled exception in worker thread | Exception in background thread |
| `CORE-0003` | Resource not found | File or resource not found |
| `CORE-0004` | Operation timed out | Timeout exceeded |
| `CORE-0005` | Failed to clean up resource | Cleanup failed |
| `CORE-0006` | Event bus queue full, dropping event | EventBus queue full, event discarded |
| `CORE-0007` | State machine invalid transition | Illegal state transition |
| `CORE-0008` | Heartbeat timeout detected | Component is not responding |
| `CORE-0009` | Component health state changed | A subsystem changed health state |

## Finding Errors in Logs

Error codes appear in the log with their code:

```
[ERROR] [HOOK-0003] Hook imports disallowed module: hook 'jump' imports 'os'
```

You can search the entire log for `SUBSYSTEM-NNNN`.
