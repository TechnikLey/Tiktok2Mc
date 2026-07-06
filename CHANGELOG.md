# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-07-05

### BREAKING CHANGES

- **Complete system rewrite** — v1.0.0 is a ground-up redesign and is **not compatible** with any v0.x version. Direct migration from previous versions is not supported.
- **Port consolidation** — all 7 per-plugin Flask servers removed; plugins now communicate through the central API on port 29185.
- **Plugin architecture overhaul** — plugins now use a `BasePlugin` class with `plugin.json` manifests and `config.yaml` alongside them. Legacy self-registration and `register_plugin()` calls removed.
- **ChannelPoints and LikeGoal plugins removed** — economy/points system and like-goal overlay deleted entirely.
- **`overlay-text` promoted to core subsystem** — no longer a plugin; configuration moved from plugin config to global `config.yaml`.
- **Shell commands unified into `actions.mca`** — standalone `shell_actions.txt` removed; shell commands use the `&` prefix inside `actions.mca`.
- **Spotify configuration migrated** — tokens, `client_id`, and `client_secret` moved from global `config.yaml` to `src/plugins/spotify/config.yaml`.
- **Hook system restructured** — hooks moved from `event_hooks/` to `hooks/`, now use `hook.json` manifests with subdirectory structure.

### Added

- **Server Manager** — create, start, stop, and restart Minecraft server instances from the GUI with console instance selector, lifecycle UX, and live uptime display.
- **API Authentication** — optional `api_key` config field; `X-API-Key` header enforced on non-localhost requests.
- **GUI Installer** — Windows NSIS installer with setup wizard, desktop/start menu shortcuts, startup registration, and uninstall support.
- **Event Reactions (GUI)** — guided 3-step wizard replacing the technical "Mappings/Actions" UI with visual reaction cards, category filters, templates, and live preview.
- **Live Dashboard** — real-time plugin health status cards, recent activity feed, and EventBus visualization via SSE.
- **Overlay Preview & Live Theme Editor** — live preview rendering with debounced auto-refresh on color changes; in-editor test message form.
- **Hook System** — persistent hook registry with enable/disable, per-hook configuration, auto-discovery, and management API. New `create_hook.py` scaffolding script.
- **Trigger Simulator (Event Tester)** — API and GUI card for simulating follow/like/gift/share/join/comment events through the full EventBus pipeline.
- **RCON Console** — connection timeout handling, pre-configuration from `config.yaml` so console works on first request.
- **Spotify OAuth Flow Helper** — CLI wizard (`spotify_setup.py`) that guides users through browser-based Spotify authentication, token exchange, and saves to plugin-local config.
- **Error Handling & Diagnostics Framework** — structured error codes, crash manager, health monitor with 8-state machine, diagnostics report, and API endpoints (`GET /api/v1/diagnostics`, `GET /api/v1/health`).
- **Event-Command Mapper** — background task that listens to EventBus events and dispatches plugin commands via `CommandQueue` based on mapping config in `data/event_commands.yaml`.
- **Port Scanner** — automatically scans bind ports on startup and resolves conflicts.
- **MCA Language Server** — VS Code extension with IntelliSense, diagnostics, syntax highlighting, symbol navigation, and code snippets for `.mca` files.
- **Backup System** — SHA-256 deduplicated, versioned backups with retention policies for registry, plugin config, and actions.
- **Plugin sandboxing** — cross-platform resource limits (memory, CPU, file handles) with configurable `plugin_sandbox` section.
- **Download integrity verification** — SHA-256 checksum verification for plugin and tool updates.

### Changed

- **GUI redesigned** — unified design system with CSS custom properties, BEM-style classes, amber accent color, and improved modal z-indexing.
- **Plugin communication modernized** — zero-latency long-polling via `asyncio.Event` replaces 0.5s polling loops. EventBus pub/sub with SSE and WebSocket endpoints replaces hardcoded plugin-to-plugin calls.
- **Declarative Event Routing** — `plugin.json` `event_subscriptions` field routes events automatically; no more hardcoded plugin names in `main.py`.
- **Timer, WinCounter, DeathCounter rewritten** — fully decoupled from each other, publish events via EventBus instead of direct calls.
- **Spotify plugin modernized** — publishes `spotify.*` events to EventBus, registers comment handler via declarative `plugin.json` prefix.
- **Config editing improved** — dynamic Save button (enabled only when dirty), input debounce, unsaved-changes dialog on close.
- **Single-instance guard** — GUI prevents multiple instances via named mutex; auto-switches to dashboard on second launch.
- **Test suite expanded** — 1197 total tests (969 Python + 228 GUI) with CI workflow on push/PR to `main`.

### Removed

- **ChannelPoints plugin** (economy/points system)
- **LikeGoal plugin** (like-goal overlay)
- **`shell_actions.txt`** — merged into `actions.mca` with `&` prefix
- **Per-plugin Flask servers** — all 7 plugin ports eliminated
- **Legacy self-registration** — `register_plugin()`, `python/registry.py`, `client.py`, `--register-only` flag
- **Legacy `gui.py`, `plugin_updater.py`**
- **Sidebar dropdowns** for Plugins and Hooks (simplified navigation)
- **`random_triggers`** from main config (moved to `hooks/random/config.yaml`)

### Fixed

Due to a full system rewrite, many legacy issues from previous stable versions were inherently resolved by the architectural changes. No specific legacy bug list is carried forward due to the architectural redesign.
