# Error Codes

Every error in the system has a stable, documented code in the format `SUBSYSTEM-NNNN`.

## Subsystems

| Prefix | Subsystem |
|--------|-----------|
| `CORE` | General runtime |
| `PLUGIN` | Plugin system |
| `GUI` | Graphical interface |
| `API` | REST API |
| `CONFIG` | Configuration |
| `OVERLAY` | Overlay system |
| `HOOK` | Hook system |
| `LIFECYCLE` | Process lifecycle |
| `MC` | Minecraft / RCON |
| `TIKTOK` | TikTok Live connection |

## Severity Levels

| Level | Meaning |
|-------|-----------|
| `DEBUG` | Diagnostic information |
| `INFO` | Normal operation |
| `WARNING` | Potential problem |
| `ERROR` | Function limited |
| `CRITICAL` | Severe error |
| `FATAL` | Process will be terminated |

## Important Error Codes

### HOOK (Hook System)

| Code | Message | Description |
|------|---------|--------------|
| `HOOK-0001` | Hook directory not found | Hook directory does not exist |
| `HOOK-0002` | Invalid hook.json | `hook.json` missing or invalid JSON |
| `HOOK-0003` | main.py not found | `main.py` missing in hook directory |
| `HOOK-0004` | Missing required field | `name` or `version` missing in manifest |
| `HOOK-0005` | Disallowed import | Disallowed module imported |
| `HOOK-0006` | Unexpected load error | General load error |
| `HOOK-0007` | Missing register() function | `register()` function missing in main.py |

### PLUGIN (Plugin System)

| Code | Message | Description |
|------|---------|--------------|
| `PLUGIN-0001` | Failed to initialize plugin | Plugin error during initialization |
| `PLUGIN-0002` | Plugin process crashed | Plugin subprocess crashed |
| `PLUGIN-0003` | Plugin tick handler failed | `on_tick()` threw exception |
| `PLUGIN-0004` | Plugin command handler failed | Handler threw exception |
| `PLUGIN-0005` | Plugin dependency not met | `depends_on` plugin not active |
| `PLUGIN-0006` | Plugin not found in registry | Plugin not registered |
| `PLUGIN-0007` | API version mismatch | `min_api_version` not met |

### CONFIG (Configuration)

| Code | Message | Description |
|------|---------|--------------|
| `CONFIG-0001` | Config file not found | `config/config.yaml` does not exist |
| `CONFIG-0002` | Config file invalid | YAML syntax error |
| `CONFIG-0003` | Config healing applied | Missing fields were repaired |
| `CONFIG-0004` | Plugin config not found | Plugin `config.yaml` missing |
| `CONFIG-0005` | Plugin config invalid | Plugin configuration invalid |

### MC (Minecraft / RCON)

| Code | Message | Description |
|------|---------|--------------|
| `MC-0001` | RCON connection failed | Connection to Minecraft server failed |
| `MC-0002` | RCON authentication failed | Wrong RCON password |
| `MC-0003` | RCON command failed | Command could not be sent |
| `MC-0004` | RCON queue full | Queue full, command discarded |
| `MC-0005` | Server not running | Minecraft server is not running |

### TIKTOK (TikTok Live)

| Code | Message | Description |
|------|---------|--------------|
| `TIKTOK-0001` | Connection failed | Connection to TikTok Live failed |
| `TIKTOK-0002` | Reconnecting | Automatic reconnection |
| `TIKTOK-0003` | Event parse error | TikTok event could not be parsed |

### CORE (General)

| Code | Message | Description |
|------|---------|--------------|
| `CORE-0001` | Unhandled exception in main thread | Fatal exception in main thread |
| `CORE-0002` | Unhandled exception in worker thread | Exception in background thread |
| `CORE-0003` | Resource not found | File or resource not found |
| `CORE-0004` | Operation timed out | Timeout exceeded |
| `CORE-0006` | Event bus queue full | EventBus queue full, event discarded |
| `CORE-0008` | Heartbeat timeout | Component not responding |

## Finding Errors in Logs

Error codes appear in the log with their code:

```
[ERROR] [HOOK-0005] Disallowed import: hook 'jump' imports 'os'
```

You can search the entire log for `SUBSYSTEM-NNNN`.
