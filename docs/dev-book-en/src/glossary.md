# Glossary

## A

**actions.mca**
Configuration file that maps TikTok triggers to Minecraft actions. Defines what happens when a specific event arrives.

**API Server**
Central HTTP server (port 29185) that manages communication between plugins, hooks, and the main system.

## B

**Bridge Process**
The main process (`src/python/main.py`) that manages the TikTok connection, receives events, and forwards them to the system. Imports modules from `src/core/` — both directories share the same PYTHONPATH, so `from core.*` works in the Bridge process.

## C

**config.yaml**
Configuration file. Each plugin and each hook has its own. The global `config.yaml` contains system-wide settings.

**config_schema**
JSON schema in `plugin.json` or `hook.json` that defines the expected configuration structure.

## E

**Event**
A message in the system distributed via the EventBus. Events have a type (e.g., `tiktok.gift`) and data.

**EventBus**
Central publish/subscribe system for distributing events to all interested components.

**Event-Command-Mapper**
Service that maps events from the EventBus to plugin commands, based on `event_commands.yaml`.

## H

**Hook**
Lightweight, in-process extension for `$` commands in `actions.mca`. Runs in the bridge process.

**hook.json**
Manifest file of a hook. Contains metadata and configuration schema.

**HookAPI**
The programming interface available to hooks for interacting with the main system.

## P

**Plugin**
Standalone program that runs as a separate subprocess and communicates via HTTP with the API server.

**plugin.json**
Manifest file of a plugin. Contains metadata, entry point, dependencies, and configuration schema.

**Plugin Registry**
Central database (in `data/api_plugin_registry.json`) that manages all registered plugins with their state.

## R

**RCON (Remote Console)**
Network protocol for sending commands to a Minecraft server.

## S

**SSE (Server-Sent Events)**
Technology for real-time updates from server to client. Used for overlay updates.

## T

**Trigger**
An entry in `actions.mca` that maps a TikTok event (or a custom name) to actions.
