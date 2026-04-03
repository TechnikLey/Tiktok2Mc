# Create Your Own Plugin

> [!WARNING]
> Currently all plugins use the `config.yaml`.
> However, this will change in the future, as this file is only intended
> for the main program.
> The exact implementation will be introduced in future updates and this chapter will be adjusted accordingly.
> Keep this in mind and watch for changes.
>
> You can already create your own `config.yaml` in the plugin folder and use it for settings.
> This saves you from having to make adjustments to the code later if the global `config.yaml` can no longer be used for plugins.

### What Is a Plugin?

A **plugin** is an independent Python program that integrates with the streaming tool. Each plugin:
- Runs as a **separate process** (registered in the registry)
- **Communicates via DCS** (HTTP) with other modules
- Optionally has a **GUI (ICS)** with pywebview
- Is centrally configured in `config.yaml`
- Has **access to events** via webhook

**Built-in plugins (examples):**
- **DeathCounter**: Counts deaths, sends to Minecraft
- **LikeGoal**: Manages like goals
- **Timer**: Countdown timer
- **WinCounter**: Win counter

(All built-in plugins support `ICS`)

### Plugin Lifecycle

```
1. Create plugin folder (with create_plugin.ps1) (plugins/myPlugin/)
   ↓
2. Write main.py (HTTP server, event handler)
   ↓
3. Register in registry.py (PLUGIN_REGISTRY)
   ↓
4. Edit config.yaml (user configuration)
   ↓
5. Load into start.py (start process)
   ↓
6. Events arrive via /webhook endpoint
   ↓
7. Plugin processes, sends commands
```

### Roadmap of This Chapter

1. **Understand plugin structure** (folders, files, config)
2. **Creating an HTTP server with Flask** (receive events)
3. **Send Minecraft commands** (RCON communication)
4. **Data storage & configuration** (user data)
5. **GUI with pywebview** (visual interface, optional)
6. **Communicate between plugins** (HTTP + error handling)
7. **Best practices & error handling** (production ready)

→ **Start**: [Plugin structure & setup](./ch02-01-plugin-structure-and-setup.md)
- Logging in `logs/` folder
- Avoid typical mistakes
- Resource management (memory & thread leaks)

## Programming Languages: Python or Something Else?

A plugin does not necessarily have to be written in Python. You can basically develop it in any programming language. You can find out more about this in the chapter [Create plugin without Python](...).

**But be careful:** With Python you need about 20 lines of code for the base. With other languages (Java, C++, Rust, etc.) this can quickly add up to several hundred lines because you have to implement a lot of things yourself.

Additional programming languages may be directly supported in the future. However, Python remains the primary supported language: with the most help, integrations and regular updates.

## Let's Go!

Are you ready? Then let's start with [Plugin structure & setup](./ch02-01-plugin-structure-and-setup.md).

After going through these chapters you will understand:
- How plugins are technically structured
- How events reach you and how you react to them
- How to manage configuration and data
- How to build GUIs with pywebview
- How plugins communicate with each other
- How to keep your plugin stable

The concrete implementation and creative use of these tools – that's your part!

---
