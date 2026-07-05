# Hook Development

Hooks are a lightweight alternative to plugins. They run directly in the bridge process and react to `$` commands defined in `actions.mca`. Hooks are particularly suitable for simple, reactive extensions.

In this chapter you will learn how to create, configure, and integrate hooks into the system.

## Chapter Structure

1. [Your First Hook](./ch04-01-your-first-hook.md) – Create your first hook in a few minutes
2. [Hook Structure & Manifest](./ch04-02-hook-structure-and-manifest.md) – Directory structure and hook.json
3. [Hook API Reference](./ch04-03-hook-api.md) – All available Hook API methods
4. [Configuration](./ch04-04-hook-configuration.md) – Per-hook configuration
5. [Import Restrictions](./ch04-05-import-restrictions.md) – Allowed imports and restrictions
6. [Plugin-Bundled Hooks](./ch04-06-plugin-bundled-hooks.md) – Hooks bundled with a plugin

## When to Use a Hook vs. a Plugin

| Aspect | Hook | Plugin |
|--------|------|--------|
| Execution location | Runs **directly in the bridge process** | Own subprocess |
| Communication | **Direct function call** | HTTP API (`send_command`) |
| Latency | Milliseconds | Higher (polling interval 1s) |
| Complexity | Simple, one function | Full class with threads |
| Use case | Simple `$` commands | Complex logic, GUI, state |
| Lifecycle | Loaded on startup | Started/stopped as subprocess |
