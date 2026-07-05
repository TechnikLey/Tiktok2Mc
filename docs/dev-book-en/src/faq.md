# FAQ

## General

### Can I write a plugin in a language other than Python?

Yes, plugins can be written in any language as long as they run as an independent process and can communicate with the system's HTTP API. However, the effort is significantly higher since you must implement all communication yourself. This documentation only describes the Python API via `BasePlugin` — for other languages you need to determine the HTTP endpoints from the source code.

### What is the difference between a plugin and a hook?

A plugin is a separate process with its own GUI, state management, and sandboxing. A hook is a lightweight, in-process extension intended only for `$` commands in `actions.mca`. Details can be found in [Core Concepts](./ch02-00-core-concepts.md).

### Can I have multiple hooks in one file?

Each hook has its own `main.py` file and its own directory. However, a single `main.py` can register any number of actions.

## Development

### My plugin is not showing up in the list. What should I do?

Check if the `plugin.json` exists and is valid. The `entry_point` must be correct. Restart the system so the plugin watcher rescans.

### My hook is not loading. What should I do?

Check if the `register()` function exists and if all imports are allowed. Check the logs for error messages.

### Can I use external libraries in hooks?

No. Hooks may only import the allowed modules (see [Import Restrictions](./ch04-05-import-restrictions.md)). If you need external libraries, create a plugin.

## Events

### How do I receive TikTok events in my plugin?

Declare `event_subscriptions` in `plugin.json` and register a handler for `"tiktok_event"`. See [Events & Subscriptions](./ch03-05-events-and-subscriptions.md).

### How do I send an event from my plugin?

Use `self.api_post("/events", {"type": "my.event", "data": {...}})`. The event is then distributed via the EventBus.

### What is the Event-Command-Mapper?

The Event-Command-Mapper forwards events from the EventBus to plugins based on the configuration in `event_commands.yaml`. See [Event-Command-Mapper](./ch05-02-event-command-mapper.md).

## Minecraft

### How do I send Minecraft commands from a hook?

Use `api.rcon_enqueue([...])`. See [Hook API](./ch04-03-hook-api.md).

### How do I send Minecraft commands from a plugin?

Plugins communicate indirectly via the [Event-Command-Mapper](./ch05-02-event-command-mapper.md) or via `send_command()` to specialized components. See [Cross-Plugin Communication](./ch03-06-cross-plugin-communication.md).

### Can I send commands from Minecraft server plugins (Bukkit/Paper)?

Yes, RCON can send both Vanilla commands and plugin commands. The Minecraft server treats them like console input.

## Overlay

### How do I display text in the overlay?

In hooks with `api.send_overlay_text()`. In plugins with `get_overlay_html()` and `push_state()`.

### How do I embed a plugin overlay in OBS?

Use the URL `http://127.0.0.1:29185/api/v1/plugins/<plugin-name>/overlay` as a Browser Source.
