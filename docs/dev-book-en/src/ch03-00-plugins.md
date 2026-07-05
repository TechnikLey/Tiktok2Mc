# Plugin Development

Plugins are the primary extension mechanism. A plugin runs as a separate subprocess and communicates via HTTP with the API server.

In this chapter you will develop a complete plugin step by step. Each chapter builds on the previous one.

## Chapter Overview

1. [Your First Plugin](./ch03-01-your-first-plugin.md) — Lifecycle, handlers, events
2. [Plugin Structure & Manifest](./ch03-02-plugin-structure.md) — All files and fields
3. [Configuration](./ch03-03-configuration.md) — Schema, defaults, access
4. [Plugin API Reference](./ch03-04-plugin-api.md) — All public methods
5. [Receiving Events](./ch03-05-events-and-subscriptions.md) — TikTok events and Event-Command-Mapper
6. [Cross-Plugin Communication](./ch03-06-cross-plugin-communication.md) — Messages between plugins
7. [Overlays & State](./ch03-07-overlays-and-state.md) — HTML overlay and real-time updates
