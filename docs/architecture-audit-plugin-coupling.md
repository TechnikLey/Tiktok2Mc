# Architecture Audit: Plugin Coupling

> **Scope:** Full codebase analysis of `D:\Tiktok2Mc`
> **Focus:** Plugin independence, cross-plugin dependencies, main-system coupling
> **Date:** 2026-05-31

---

## 1. Executive Summary

The plugin ecosystem is **moderately coupled**. Cross-plugin dependencies are minimal (only 2 explicit), but the **main system is deeply entangled** with plugin internals. The biggest architectural debt is that the **main config owns plugin features** (`comment_commands`, `random_triggers`, `minecraft_server_api`) and the **main system hardcodes plugin names** in the core event pipeline.

**Good news:**
- No plugin imports another plugin directly
- All plugin communication goes through the public HTTP API
- Plugin polling/state-push model is clean

**Bad news:**
- `main.py` hardcodes 4 plugin names in the TikTok event loop
- `overlay_utils.py` is hardcoded to the `overlay-text` plugin
- `comment_commands` (a plugin-level feature) lives in the main config
- `PluginAPIClient`, `EventBus`, `WebSocket` — all built but **completely unused**
- Every plugin reimplements the same `urllib.request` polling boilerplate

---

## 2. Phase 2 — Complete Coupling Inventory

---

### 2.1 Plugin → Plugin Coupling

| # | Source | Target | Type | Location | Severity |
|---|--------|--------|------|----------|----------|
| 1 | `timer` | `win-counter` | **Direct HTTP API call** | `timer/main.py:144` — `_api_post("/plugins/win-counter/command", {"command":"add_win","args":{"amount":1}})` | Medium |
| 2 | `spotify` hook | `overlay-text` | **Indirect via `core.overlay_utils`** | `spotify/hooks/spotify_control/main.py:29` — `api.send_overlay_text(...)` → `core/overlay_utils.py:110` → HTTP POST to `/plugins/overlay-text/command` | Low |

**Notes:**
- #1 is fire-and-forget; `timer` never reads back `win-counter` state.
- #2 goes through a core abstraction (`HookAPI.send_overlay_text`), but the core abstraction is hardcoded to the `overlay-text` plugin.
- Three plugins (`deathcounter`, `wincounter`, `timer`) all consume the same `player_death` / `player_respawn` commands from the central API queue — this is **not** direct coupling; they are independent subscribers to a central event.

---

### 2.2 Main System → Plugin Coupling

#### A. Hardcoded plugin names in `src/python/main.py`

| # | Plugin name | Code location | What it does | Severity |
|---|-------------|---------------|--------------|----------|
| 1 | `like-goal` | `main.py:223` | `load_all_plugin_configs().get("like-goal", {})` — loads plugin config directly from disk to validate like triggers | High |
| 2 | `like-goal` | `main.py:1122` | `_plugin_command("like-goal", "add_likes", delta=...)` — forwards TikTok like counts to the plugin | High |
| 3 | `channel-points` | `main.py:759,1287,1336,1346,1389,1390,1403,1450` | `_ping_channel_points()` called on **every** TikTok event (gift/follow/like/join/comment/share) | **Critical** |
| 4 | `channel-points` | `main.py:781,783` | `_plugin_command("channel-points", "get_points", ...)` — comment command point-cost check | **Critical** |
| 5 | `channel-points` | `main.py:792` | `_plugin_command("channel-points", "spend", ...)` — point deduction on command execution | **Critical** |
| 6 | `overlay-text` | `main.py:582` | `send_overlay_text(...)` — delegates overlay rendering to `core.overlay_utils` which is hardcoded to `overlay-text` | Medium |

#### B. Hardcoded plugin names in core utilities

| # | File | Plugin | Code | Severity |
|---|------|--------|------|----------|
| 7 | `core/overlay_utils.py` | `overlay-text` | `PLUGIN_NAME = "overlay-text"` (line 13) — constant hardcodes plugin name | **Critical** |
| 8 | `core/overlay_utils.py` | `overlay-text` | `manifest.get("name") == "overlay-text"` (line 22) — filesystem scan for specific plugin | **Critical** |
| 9 | `core/overlay_utils.py` | `overlay-text` | `load_plugin_config(plugin_dir)` (line 58) — loads overlay-text config directly from disk | **Critical** |
| 10 | `core/theme.py` | 7 plugins | `_DEFAULT_THEMES` dict contains hardcoded keys: `"like_goal"`, `"death_counter"`, `"win_counter"`, `"timer"`, `"overlay_text"`, `"spotify"`, `"channel_points"` | Medium |
| 11 | `core/api/services/__init__.py` | `minecraft_server_api` | `"minecraft_server_api": dict` in global config validation schema | Medium |

#### C. Plugin-specific config sections in `defaults/config.yaml`

| Section | Belongs to | Why it's a problem |
|---------|-----------|-------------------|
| `comment_commands` | **Should be plugin-local** or a standalone plugin | Full chat-command engine (prefixes, roles, cooldowns, points costs, handlers, conditionals) lives in main config. `main.py` parses and executes it. |
| `random_triggers` | **Should be hook-local** (`hooks/random/config.yaml`) | Configures `$random` hook mode + trigger list, but schema demands it in main config. |
| `minecraft_server_api` | **Should be plugin-local** (`plugins/minecraft_server_api/config.yaml`) | Plugin-specific `enabled`, `api_port`, `web_server_port` in main config. |

#### D. Comment command handlers that reach into plugins

The `comment_commands` system in `main.py` (lines ~795-962) has a Spotify-specific group (prefix `"$"`) that:
- Lists Spotify command names: `play`, `pause`, `skip`, `playtrack`, `queue`, `volume`
- References `{spotify_port}` placeholder
- Documents Spotify `/playtrack` endpoint behavior (`{"found": true/false}`)
- Makes HTTP calls to `http://127.0.0.1:{spotify_port}/comment?user={user}&text={text}`

This means the **main system owns knowledge** of Spotify's internal command vocabulary and port.

#### E. `start.py` coupling

| # | Location | Coupling | Severity |
|---|----------|----------|----------|
| 12 | `start.py:181` | `cfg.get("minecraft_server_api", {}).get("enabled", True)` — reads plugin-specific config from main config | Medium |
| 13 | `start.py:814-847` | `_plugin_health_check_loop()` — iterates global `processes` dict and updates API registry with `health_status="dead"` | Medium |

---

### 2.3 Plugin → Main System Coupling

| # | Plugin | Coupling | Severity |
|---|--------|----------|----------|
| 1 | `spotify` | `redirect_uri: "http://127.0.0.1:29185/api/v1/plugins/oauth/callback?name=spotify-control"` in own `config.yaml` — hardcodes central API port and route | Medium |
| 2 | All plugins | Every plugin reimplements the same `_api_post()` / `_api_get()` boilerplate with `urllib.request` instead of using the provided `PluginAPIClient` | Low |

---

### 2.4 Communication Architecture Assessment

| Mechanism | Built? | Used by plugins? | Used by main system? |
|-----------|--------|------------------|---------------------|
| HTTP command polling (`GET /plugins/{name}/commands`) | ✅ | ✅ All 7 plugins | ✅ (main pushes commands) |
| HTTP state push (`POST /plugins/{name}/state`) | ✅ | ✅ All 7 plugins | ❌ |
| Overlay HTML registration | ✅ | ✅ All 7 plugins | ❌ |
| Per-plugin SSE stream | ✅ | ✅ Browser overlays | ❌ |
| `EventBus` (in-memory pub/sub) | ✅ | ❌ **None** | ❌ **None** |
| Global SSE (`/api/v1/events/stream`) | ✅ | ❌ Only log viewer | ❌ |
| WebSocket (`/api/v1/ws`) | ✅ | ❌ **None** | ❌ **None** |
| `PluginAPIClient` class | ✅ | ❌ **None** | ❌ **None** |
| `register_plugin()` helper | ✅ | ❌ **None** | ❌ **None** |
| `POST /api/v1/events` (event injection) | ✅ | ❌ **None** | ❌ **None** |

**Verdict:** The project built a rich event infrastructure (EventBus, WebSocket, global SSE, event injection) that is **100% unused** by business logic. Everything is synchronous HTTP polling.

---

## 3. Phase 3 — Refactor Plan

---

### 3.1 Design Principles

1. **Plugin owns its config** — No plugin-specific keys in `defaults/config.yaml`
2. **Main system publishes events, plugins subscribe** — Replace hardcoded `_plugin_command("channel-points", ...)` with EventBus
3. **Core utilities are plugin-agnostic** — `overlay_utils.py` must not hardcode `"overlay-text"`
4. **Standardize plugin communication** — Provide a `PluginClient` that every plugin uses (stop the copy-paste `urllib.request`)
5. **Declare dependencies** — Use `depends_on` in manifests; launcher enforces startup order

---

### 3.2 High-Priority Decoupling Targets

#### 🟡 Target 1: Extract plugin-specific parts from `comment_commands`
**Severity:** Medium
**Why:** `comment_commands` is a **core feature** (command parsing + execution framework belongs in main.py). BUT plugin-specific command definitions (Spotify `$` commands, ChannelPoints `points_cost`, plugin-specific URLs) leak plugin internals into the main config.
**Migration:**
1. Keep `comment_commands` framework in `main.py` (parsing, roles, cooldowns, prefix matching)
2. Remove Spotify-specific `$` command group from `defaults/config.yaml` — move to `plugins/spotify/config.yaml` under a `commands` or `chat_commands` key
3. Remove `points_cost` from command definitions — ChannelPoints plugin should handle its own economy, main system just fires `comment` events
4. Core provides a command registration hook: plugins register their command handlers via API (`POST /api/v1/plugins/{name}/commands/register` or via EventBus)
5. `main.py` fires `comment` events to EventBus; plugins can subscribe and handle their own prefixes

#### 🔴 Target 2: Decouple `channel-points` from main event loop
**Severity:** Critical
**Why:** `_ping_channel_points()` is called on every TikTok event with a hardcoded plugin name.
**Migration:**
1. `main.py` publishes all TikTok events to the EventBus: `event_bus.publish("tiktok.gift", {...})`, `event_bus.publish("tiktok.like", {...})`, etc.
2. `channel-points` plugin subscribes to relevant events: `event_bus.subscribe("tiktok.*", handler)`
3. Remove `_ping_channel_points()` from `main.py` entirely
4. Point-cost checks (`get_points`, `spend`) become internal to the command-processor plugin

#### 🔴 Target 3: Decouple `overlay_utils.py` from `overlay-text`
**Severity:** Critical
**Why:** The overlay utility is hardcoded to a single plugin name.
**Migration:**
1. `overlay_utils.py` should accept a `plugin_name` parameter instead of using a constant
2. Or: rename `overlay_utils.py` to `plugin_utils.py` and make it a generic plugin-caller
3. `HookAPI.send_overlay_text()` should accept a target plugin name (default `"overlay-text"` for backward compat)

#### 🟡 Target 4: Move `random_triggers` to hook-local config
**Severity:** Medium
**Why:** Hook config should live in the hook's own `config.yaml`.
**Migration:**
1. Move `random_triggers` from `defaults/config.yaml` to `src/hooks/random/config.yaml`
2. `hooks/random/main.py` already reads via `api.get_hook_config("random")` — just needs the data to be in the right place
3. Remove `random_triggers` from main config schema

#### 🟡 Target 5: Move `minecraft_server_api` to plugin-local config
**Severity:** Medium
**Why:** Plugin-specific settings should not be in the main config.
**Migration:**
1. Move the section to a new `plugins/minecraft_server_api/config.yaml` or absorb into an existing plugin
2. `main.py`, `start.py`, `server.py` query the plugin via API instead of reading main config

#### 🟡 Target 6: Adopt `PluginAPIClient` in all plugins
**Severity:** Medium
**Why:** 8 plugins copy-paste the same `urllib.request` boilerplate.
**Migration:**
1. Fix `PluginAPIClient` if needed (or replace with a simpler `PluginClient`)
2. Update all plugin `main.py` files to use it
3. Delete the duplicate `_api_post()` / `_api_get()` functions

#### 🟢 Target 7: Remove hardcoded theme keys
**Severity:** Low
**Why:** `theme.py` pre-defines colors for specific plugins.
**Migration:**
1. Make `_DEFAULT_THEMES` empty by default
2. Each plugin defines its own theme fallback in its `config.yaml`
3. `theme.py` falls back to generic colors if plugin has no theme config

---

### 3.3 Recommended Migration Path

**Phase A (Immediate — before any code changes):**
1. Audit `depends_on` arrays in all `plugin.json` files
2. Add missing runtime dependencies:
   - `timer` → `depends_on: ["win-counter"]` (for `auto_win`)
   - `win-counter` → `depends_on: []` (already empty, but implicit: MinecraftServerAPI for `player_death`)
   - `death-counter` → `depends_on: []` (implicit: MinecraftServerAPI)

**Phase B (High-priority decoupling):**
1. Implement EventBus publishing in `main.py` for all TikTok events
2. Refactor `channel-points` to consume EventBus events instead of being polled
3. Extract `comment_commands` logic from `main.py` into `channel-points` or a new plugin
4. Make `overlay_utils.py` plugin-agnostic

**Phase C (Config cleanup):**
1. Move `random_triggers` to `hooks/random/config.yaml`
2. Move `minecraft_server_api` to plugin-local config
3. Remove plugin-specific keys from `defaults/config.yaml` schema

**Phase D (Standardization):**
1. Build a proper `PluginClient` wrapper
2. Update all plugins to use it
3. Delete `PluginAPIClient` dead code if the new client supersedes it

---

### 3.4 Risks Introduced by Decoupling

| Risk | Mitigation |
|------|------------|
| **EventBus performance** — Publishing every TikTok event to the bus adds overhead | Benchmark first; add selective filtering (only publish events plugins care about) |
| **Startup ordering** — `timer` depends on `win-counter` being ready | `PluginLauncher` already has health polling; enforce `depends_on` startup order |
| **Config migration** — Users have `comment_commands` in their main `config.yaml` | Write a migration that moves the section to plugin config on first startup |
| **API breakage** — Changing `overlay_utils.py` signature affects hooks | Keep backward-compatible default parameter (`plugin_name="overlay-text"`) |
| **Testing gap** — Decoupling creates new integration surfaces | Add integration tests for EventBus → plugin command flow before refactoring |

---

### 3.5 Proposed v1.0.0 Architecture Direction

```
┌─────────────────────────────────────────────────────────────┐
│                         START.EXE                           │
│                      (process orchestrator)                  │
└─────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              │               │               │
        ┌─────▼─────┐   ┌─────▼─────┐   ┌────▼────┐
        │  CORE/    │   │  CORE/    │   │  CORE/  │
        │  app.exe  │   │  server.  │   │  gui.   │
        │           │   │  exe      │   │  exe    │
        └─────┬─────┘   └───────────┘   └─────────┘
              │
        ┌─────▼──────────────────────────────────────┐
        │          Main API (127.0.0.1:29185)       │
        │  ┌─────────────┐  ┌─────────────────────┐  │
        │  │ EventBus    │  │ PluginStateStore    │  │
        │  │ (pub/sub)   │  │ CommandQueue         │  │
        │  └──────┬──────┘  └─────────────────────┘  │
        └─────────┼────────────────────────────────────┘
                  │ publishes events
    ┌─────────────┼─────────────┬─────────────┐
    │             │             │             │
┌───▼───┐    ┌───▼───┐    ┌───▼───┐    ┌───▼───┐
│channel│    │  win  │    │ death │    │ timer │
│points │    │counter│    │counter│    │       │
└───────┘    └───────┘    └───────┘    └───────┘
    │             │             │             │
    │    ┌────────┼─────────────┼─────────────┤
    │    │        │             │             │
    │    │   ┌────▼────┐   ┌───▼───┐    ┌───▼───┐
    │    │   │ like-   │   │overlay│    │spotify│
    │    │   │ goal    │   │ text  │    │       │
    │    │   └─────────┘   └───────┘    └───────┘
    │    │
    │    └──── subscribes to tiktok.* events via EventBus
    │
    └────── comment command processor (extracted from main.py)
```

**Key changes from current architecture:**
1. **Main system publishes, plugins subscribe** — No hardcoded `_plugin_command("channel-points", ...)`
2. **Comment commands become a plugin** — Not baked into `main.py`
3. **EventBus is actually used** — TikTok events flow through it; plugins react
4. **PluginClient standardizes communication** — No more copy-paste `urllib.request`
5. **Config is plugin-local** — `defaults/config.yaml` only has framework settings

---

## 4. Quick-Reference Severity Matrix

| # | Coupling | Severity | Target Phase |
|---|----------|----------|--------------|
| 1 | `main.py` hardcodes `channel-points` on every event | 🔴 Critical | Phase B |
| 2 | `main.py` hardcodes `like-goal` for like triggers | 🔴 Critical | Phase B |
| 3 | `overlay_utils.py` hardcoded to `overlay-text` | 🔴 Critical | Phase B |
| 4 | Plugin-specific command definitions in `comment_commands` config | 🟡 Medium | Phase C |
| 5 | `random_triggers` in main config | 🟡 Medium | Phase C |
| 6 | `minecraft_server_api` in main config | 🟡 Medium | Phase C |
| 7 | `theme.py` hardcoded plugin keys | 🟢 Low | Phase D |
| 8 | Plugin copy-paste `urllib.request` | 🟢 Low | Phase D |
| 9 | Timer → WinCounter direct call | 🟡 Medium | Document in `depends_on` |
| 10 | Spotify hook → Overlay indirect | 🟢 Low | Already via public API |

---

*End of audit.*
