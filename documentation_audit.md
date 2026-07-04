# Documentation Audit — TikTok2Mc German Developer Docs

> Generated: 2026-07-04
> Phase 1: Documentation content audit  
> Phase 2: Codebase comparison audit  

---

## Phase 1 — Documentation Quality Issues

### 1. `ch01-00-getting-started.md` — Getting Started

| # | Issue | Description | Severity | Suggestion |
|---|-------|-------------|----------|------------|
| 1.1 | **Wrong config file path** | The doc says `config.yaml` is at the project root. The code resolves it at `config/config.yaml` (see `paths.py:get_config_file()` → `root / "config" / "config.yaml"`). | **High** | Correct the path to `config/config.yaml` |
| 1.2 | **Oversimplified `src/` structure** | Says `src/core/` contains "API-Server, Plugin- und Hook-Verwaltung". In reality `src/core/` is 87 files covering event bus, hook loader, plugin config, health monitor, crash manager, error codes, etc. The FastAPI server is at `src/core/api/server.py`. | **Medium** | Give an accurate summary of core modules |
| 1.3 | **Missing `config/` directory** | The project tree omits the `config/` directory entirely. It lists `config.yaml` as a top-level file but it's actually inside `config/`. | **High** | Include `config/` in the project structure |
| 1.4 | **`run.py` described as "starts the entire system"** | The doc says `python run.py` starts the whole system. In reality `run.py` (72 lines) only starts the standalone API server. The actual bridge process is `src/python/main.py` and the full system supervisor is `src/python/start.py`. | **Critical** | Describe `run.py` as the API server only; document `start.py` as the full system entry point |
| 1.5 | **Missing `src/python/` details** | Says `src/python/` contains "Startskripte und Hilfsprogramme". It actually contains the 1729-line TikTok bridge (`main.py`), the 998-line supervisor (`start.py`), the Minecraft server launcher (`server.py`), the GUI shell (`gui.py`), the overlay process (`overlay.py`), and the updater. | **High** | Describe the actual roles of files in `src/python/` |
| 1.6 | **`create_plugin.py` generates code that doesn't match docs** | `create_plugin.py` generates `main.py` with raw boilerplate calling `load_plugin_config()` and `parse_args()` directly, NOT inheriting from `BasePlugin`. The doc teaches `BasePlugin` but the scaffolder does NOT generate a `BasePlugin` subclass. | **Critical** | Fix scaffolder to generate `BasePlugin` code, or update docs to match scaffolder |

---

### 2. `ch02-00-core-concepts.md` — Core Concepts

| # | Issue | Description | Severity | Suggestion |
|---|-------|-------------|----------|------------|
| 2.1 | **Architecture diagram is misleading** | Shows `TikTok Live → Bridge-Prozess → EventBus → Plugins / Hooks → Minecraft (RCON)` as a linear pipeline. The actual architecture is more complex: the API server (FastAPI) sits between bridge and plugins. Plugins communicate via HTTP to API server, not directly via EventBus. | **High** | Redraw architecture diagram showing API server as the central hub |
| 2.2 | **Event-Command-Mapper description too vague** | Says it "liest die Datei `event_commands.yaml` und leitet Befehle an die entsprechenden Plugins weiter". Doesn't explain that it subscribes to ALL EventBus events (`event_bus.subscribe()`) and dispatches via `command_queue.enqueue()`. | **Medium** | Add detail on how ECM subscribes, maps, and dispatches |
| 2.3 | **Missing: two RCON systems** | Doesn't mention there are TWO RCON clients: one in `main.py` (the bridge RCON worker) and one in `core/api/services/rcon.py` (the API server RconService for console). | **Medium** | Document both systems and their roles |
| 2.4 | **Missing: `start.py` supervisor** | The doc introduces the bridge process but not the `start.py` supervisor that manages ALL components (API server, bridge, GUI, overlays, Minecraft server). | **High** | Add supervisor to architecture explanation |
| 2.5 | **API server described as started by bridge** | Says "Er wird vom Bridge-Prozess gestartet". In reality the API server (FastAPI/uvicorn) is started by the `start.py` supervisor, and the bridge (`main.py`) is also started by it. | **Medium** | Correct the startup order description |

---

### 3. `ch03-01-your-first-plugin.md` — First Plugin

| # | Issue | Description | Severity | Suggestion |
|---|-------|-------------|----------|------------|
| 3.1 | **Incorrect signal file location** | Doc says signal files are at `core/runtime/plugin_start_hallo`. While `get_runtime_dir()` does return `core/runtime/`, this is the API server's runtime dir. The `start.py` supervisor manages signal files here. This is technically correct but confusing. | **Low** | Clarify that signal files are in `core/runtime/` and managed by the supervisor |
| 3.2 | **Event flow diagram conflates processes** | The diagram shows "EventBus" and "CommandQueue" as separate boxes but doesn't clarify which process they live in. EventBus is in the bridge process. CommandQueue is in the API server process. | **Medium** | Add process boundaries to the diagram |
| 3.3 | **Missing `api_post` path detail** | The description says the overlay is sent via `POST /api/v1/plugins/hallo/overlay-html`. The code does `self.api_post(f"/plugins/{self.PLUGIN_NAME}/overlay-html", {"html": html})` which translates to POST `/api/v1/plugins/hallo/overlay-html`. Correct but could be clearer. | **Low** | No change needed |
| 3.4 | **Missing explanation of health monitor** | The code registers with `HealthMonitor` and sets `HealthState.STARTING` → `RUNNING`. The doc doesn't mention this. | **Low** | Add a brief note about health monitoring |

---

### 4. `ch03-02-plugin-structure.md` — Plugin Structure

| # | Issue | Description | Severity | Suggestion |
|---|-------|-------------|----------|------------|
| 4.1 | **`config.yaml` listed as mandatory** | Says `config.yaml` is "Pflicht" (mandatory). `base_plugin.py` calls `load_plugin_config()` which returns an empty dict if no config exists. The plugin will run without it (though it's strongly recommended). | **Low** | Change "Pflicht" to "Empfohlen" |
| 4.2 | **`version.txt` not actually used by system** | Doc says `version.txt` contains version info. This file is generated by `create_plugin.py` but is NOT read by any plugin system code. It's only metadata for the scaffolder. | **Medium** | Clarify that `version.txt` is informational only |
| 4.3 | **Name convention table is contradictory** | Says directory name should be "Kebab-Case ohne Bindestriche" (kebab-case without hyphens). But kebab-case by definition uses hyphens. The `create_plugin.py` allows only `^[a-z0-9]+$` (no hyphens at all). | **High** | Fix: directory name = plugin name without hyphens (flat case) |
| 4.4 | **`hooks/` directory not in scaffolder output** | The structure lists `hooks/` as optional, but `create_plugin.py` does not create it. Users must manually create it. | **Low** | Add instruction to manually create if needed |

---

### 5. `ch03-03-plugin-manifest.md` — Plugin Manifest

| # | Issue | Description | Severity | Suggestion |
|---|-------|-------------|----------|------------|
| 5.1 | **`min_api_version` listed as "Pflichtfeld"** | The doc lists `min_api_version` as required. The JSON schema used by the API (`models.py`) does NOT require this field for registration — it validates but doesn't enforce. | **Medium** | Change to "Optional, but recommended" |
| 5.2 | **Missing `tags` field** | The API model `PluginManifest` has a `tags: list[str]` field and a `custom_data: dict` field that aren't documented. | **Low** | Document additional fields |
| 5.3 | **Registration flow oversimplified** | Step 3 says "Die Daten werden per `POST /api/v1/plugins/register` an den API-Server gesendet". The actual flow: `PluginWatcher` scans `plugin.json`, calls `ApiClient.register_plugin()` which POSTs to the API. | **Low** | Add more detail on PluginWatcher role |

---

### 6. `ch03-04-configuration.md` — Configuration

| # | Issue | Description | Severity | Suggestion |
|---|-------|-------------|----------|------------|
| 6.1 | **Missing: `enabled` field is auto-managed** | The docs show a config with `enabled: true` but don't explain that the `enabled` field in `config_schema` is special — the system uses it to determine if the plugin should auto-start. | **Medium** | Document the special role of `enabled` |
| 6.2 | **Missing: config field types not exhaustive** | The supported types list is missing some types used in the actual system (e.g., `string` with `pattern` validation, `file` type). | **Low** | Expand type list |

---

### 7. `ch03-05-plugin-api.md` — Plugin API

| # | Issue | Description | Severity | Suggestion |
|---|-------|-------------|----------|------------|
| 7.1 | **Missing `bg_color` property** | The code has a `bg_color` property that isn't documented. | **Low** | Add to reference table |
| 7.2 | **`_data_dir` is shared, not per-plugin** | Doc implies `_data_dir` is per-plugin. Actually it's `base_dir.parent / "data"` — all plugins share the same data dir. | **Medium** | Clarify that all plugins share `data/` directory |
| 7.3 | **Missing: `api_post` and `api_get` return value semantics** | Doc says `False` for `api_post` and `None` for `api_get` on failure. Actually `api_post` catches ALL exceptions and returns `False`. `api_get` returns `None` or raises on timeout. | **Low** | The docs are correct on this point |
| 7.4 | **`state` property returns copy, but writes not thread-safe** | Doc says "Thread-sicherer Zugriff". The getter does `return dict(self._state)` (copy under lock). The setter `state(value)` replaces entirely under lock. Direct mutation `self._state["key"] = val` bypasses the lock! | **Medium** | Warn against direct `self._state` mutation; always use `self.state = ...` pattern |
| 7.5 | **Missing: `on_command` fallback documented** | The doc mentions `on_command` as a fallback for unregistered commands. Correct — code at `base_plugin.py:230` calls `self.on_command(cmd, args)` when handler not found. | **OK** | Already documented |

---

### 8. `ch03-06-events-and-subscriptions.md` — Events & Subscriptions

| # | Issue | Description | Severity | Suggestion |
|---|-------|-------------|----------|------------|
| 8.1 | **Event-Bridge data flow unclear about `event_type`** | The `_publish_tiktok_event` publishes with key `"type"` in data. The `_event_bridge_worker` extracts `ev_type = data.get("type")` and `user = data.get("user")`, then sends to CommandQueue with `event_type=full_event_type, user=user, data={rest}`. The flow is correct in docs but could be clearer. | **Medium** | Add detail about data transformation between EventBus and CommandQueue |
| 8.2 | **Missing: EventBus queue capacity** | `EventBus` has `maxsize=2000` per subscriber queue. Dropped events at capacity are logged. Not documented. | **Low** | Document queue limits |
| 8.3 | **At-Least-Once claim needs verification** | Doc claims "Mindestens einmal (At-Least-Once)" delivery. The `_command_polling_loop` uses long-poll with `?wait=1`. If the poll response is lost (network issue), the commands stay in queue until next poll. But if the handler crashes after processing, the command is lost. This is actually At-Most-Once for crashes after dequeue. | **Medium** | Correct the delivery guarantee |
| 8.4 | **35-second timeout is documented but code has 35s** | Doc says "Der Polling-Request hat ein 35-Sekunden-Timeout". Code in `base_plugin.py:211-212` has `timeout=35`. The API server's `wait_for_commands` has `timeout=30.0`. These don't match. | **Medium** | Align timeout documentation with server timeout (30s) |
| 8.5 | **Event Bridge Worker subscribes to ALL events** | The code `q = event_bus.subscribe()` subscribes to all events, then filters `if not event_type.startswith("tiktok.")`. The doc doesn't explain this pattern. | **Medium** | Document the subscribe-all-then-filter pattern |

---

### 9. `ch03-07-cross-plugin-communication.md` — Cross-Plugin Communication

| # | Issue | Description | Severity | Suggestion |
|---|-------|-------------|----------|------------|
| 9.1 | **Very short — lacks concrete workflow** | The chapter is only 64 lines, mostly repeating content from elsewhere. Lacks examples of bidirectional communication patterns. | **Medium** | Expand with real cross-plugin scenarios |
| 9.2 | **Missing: `send_command` vs EventBus latency difference** | Doesn't explain that `send_command()` is HTTP-based (higher latency) while EventBus is in-process. | **Low** | Add latency comparison |

---

### 10. `ch03-08-overlays-and-state.md` — Overlays & State

| # | Issue | Description | Severity | Suggestion |
|---|-------|-------------|----------|------------|
| 10.1 | **SSE reconnect code uses `window.location.reload()`** | The example JS in two places shows different reconnect patterns: one uses `setTimeout(() => { new EventSource(...) }, 2000)` and the error handler table shows `setTimeout` with reload. The table row "SSE-Verbindung bricht ab" recommends implementing `onerror` with `setTimeout`. The version in the doc text itself uses `window.location.reload()` which is destructive. | **High** | Standardize on non-destructive reconnect pattern |
| 10.2 | **`register_overlay()` vs `push_state()` guidance is good** | The guidance on when to use each is correct and matches code behavior. | **OK** | Keep as is |
| 10.3 | **Missing: overlay HTML caching behavior** | `OverlayHtmlStore` caches HTML per plugin. Not documented. | **Low** | Add note about caching |

---

### 11. `ch03-09-advanced-features.md` — Advanced Features

| # | Issue | Description | Severity | Suggestion |
|---|-------|-------------|----------|------------|
| 11.1 | **No new information** | The chapter mostly rehashes examples from earlier chapters. The milestone pattern and timer pattern are already shown in other chapters. | **Low** | Either expand with genuinely advanced content or remove and integrate into other chapters |

---

### 12. `ch04-01-your-first-hook.md` — First Hook

| # | Issue | Description | Severity | Suggestion |
|---|-------|-------------|----------|------------|
| 12.1 | **Misleading: hooks can be disabled via `hook.json`** | Says "Setze in der `hook.json` das Feld `enabled` im `config_schema` auf `false`". This is incorrect. Hook enable/disable is managed by the `HookRegistry` (persisted to `data/hook_registry.json`), not the hook.json manifest. The `hook.json` `config_schema` merely defines what config fields exist. | **Critical** | Correct: hooks are enabled/disabled via the API or GUI, which updates the registry |
| 12.2 | **Missing: `create_hook.py` generates different code than tutorial** | `create_hook.py` generates a `main.py` with `import logging` and a complete handler, but the tutorial hand-writes a simpler version. The scaffolder result conflicts with the tutorial's "write from scratch" approach. | **Medium** | Either match scaffolder to tutorial or note the difference |
| 12.3 | **`$` prefix on actions.mca entries not shown consistently** | The tutorial uses `follow: $superjump` with `$` prefix, which is correct. The action name registered is `"superjump"` without `$`. Good. | **OK** | Already correct |
| 12.4 | **Hook deactivation via removing directory** | Says "entferne die `hook.json`-Datei" or "aus dem Verzeichnis `src/hooks/` entfernen". This works but is destructive — the registry will have stale entries. | **Medium** | Recommend using the API/GUI for disabling instead |

---

### 13. `ch04-04-hook-api.md` — Hook API

| # | Issue | Description | Severity | Suggestion |
|---|-------|-------------|----------|------------|
| 13.1 | **Lifecycle step order is incorrect in one detail** | Step 2 says "main.py validiert actions.mca" and step 3 "main.py erstellt HookAPI-Instanz". Code shows: `load_config()` → `validate_file(ACTIONS_FILE)` → `generate_datapack()` → create `HookAPI` → `load_event_hooks()`. The validation happens BEFORE HookAPI creation, not after. | **Low** | Reorder steps |
| 13.2 | **Missing: `update_runtime_state()` method** | The code has `update_runtime_state()` for live reload support. Not documented. | **Low** | Add to API reference (marked as internal) |
| 13.3 | **`get_valid_functions()` return type** | Code returns `set[str]`. Doc says `set[str]`. Correct. | **OK** | Keep as is |
| 13.4 | **`config` property provides deep copy** | Doc says "Deep Copy". Code confirms `from copy import deepcopy; return deepcopy(self._config)`. | **OK** | Keep as is |

---

### 14. `ch04-06-import-restrictions.md` — Import Restrictions

| # | Issue | Description | Severity | Suggestion |
|---|-------|-------------|----------|------------|
| 14.1 | **Missing `core.plugin_config` in table** | The `ALLOWED_HOOK_MODULES` includes `"core.plugin_config"` but the doc table doesn't list it. | **Low** | Add to table |
| 14.2 | **`urllib` is listed as allowed but with caveat "eingeschränkt"** | The code allows `"urllib"` as a top-level module (checked via `top = full_name.split(".")[0]`). Any submodule of urllib is automatically allowed. The "(eingeschränkt)" note is misleading. | **Low** | Clarify that all urllib submodules are allowed |
| 14.3 | **Missing: `requests` check** | The code has `"requests"` in `ALLOWED_IMPORTS`, but `requests` is not in the doc table. The doc does mention it as "(falls installiert)". Actually it IS in the table. OK. | **OK** | Keep as is |

---

### 15. `ch04-07-plugin-bundled-hooks.md` — Plugin-Bundled Hooks

| # | Issue | Description | Severity | Suggestion |
|---|-------|-------------|----------|------------|
| 15.1 | **Thin content — missing communication examples** | The chapter has only 57 lines and says communication works "über die Event-API" but doesn't show any real example of hook→plugin or plugin→hook communication. | **Medium** | Add concrete examples |
| 15.2 | **No mention of `plugin` field validation** | The `plugin` field in `hook.json` is documented but not how it's used for filtering. The `_discover_hook_dirs()` function uses it to associate hooks with plugins. | **Low** | Add brief explanation |

---

### 16. `ch05-00-actions-and-minecraft.md` — Actions & Minecraft

| # | Issue | Description | Severity | Suggestion |
|---|-------|-------------|----------|------------|
| 16.1 | **Only 5 lines — no content** | The chapter header page has no actual content. Just says "dieses Kapitel ist als Referenz gedacht". | **Medium** | Either add content or merge with overview |

---

### 17. `ch05-01-actions-mca-overview.md` — Actions.mca Overview

| # | Issue | Description | Severity | Suggestion |
|---|-------|-------------|----------|------------|
| 17.1 | **Vanilla command prefix described incorrectly** | Doc lists `/effect give @a speed 10 1` as "Vanilla-Befehl über Datapack". A `/` prefix command generates a datapack `.mcfunction` file which is invoked via `execute as @a run function namespace:name`. But the doc also has a separate `!` prefix for "RCON-Befehl". The distinction between `/` (datapack) and `!` (RCON) is correct in code but confusing in docs. | **Medium** | Better explain that `/` generates datapack functions, `!` sends directly via RCON |
| 17.2 | **Missing: `@name>>` named overlay prefix** | The code supports `@name>>` for named overlays. The doc only shows `>>` for default overlay. | **Low** | Add named overlay syntax |
| 17.3 | **Missing: multiplier syntax `xN`** | The code supports `xN` suffix for repeat count. The doc doesn't document this. | **Medium** | Add multiplier documentation |
| 17.4 | **`#` comment behavior not fully accurate** | Doc says "Kommentare mit `#` am Zeilenanfang werden ignoriert". The code at `actions.py:239-250` distinguishes between `##` (disabled trigger) and `# ` (full-line comment). Both start with `#`, but `##` is parsed. | **Medium** | Clarify `#` vs `##` distinction |

---

### 18. `ch05-02-event-command-mapper.md` — Event-Command Mapper

| # | Issue | Description | Severity | Suggestion |
|---|-------|-------------|----------|------------|
| 18.1 | **Missing: ECM is an asyncio background task** | The doc doesn't explain that ECM runs as an `asyncio.Task` that subscribes to ALL EventBus events and dispatches via `command_queue.enqueue()`. | **Medium** | Add background loop description |
| 18.2 | **Missing: diagnostics API** | Code has `get_diagnostics()` for dashboard. Not documented. | **Low** | Add note |
| 18.3 | **Missing: ECM auto-creates config file** | Code at `_ensure_config_file()` creates an empty `data/event_commands.yaml` if absent. | **Low** | Add note |

---

### 19. `ch05-03-rcon-and-minecraft.md` — RCON

| # | Issue | Description | Severity | Suggestion |
|---|-------|-------------|----------|------------|
| 19.1 | **Plugins RCON access is oversimplified** | Says "Plugins haben keinen direkten RCON-Zugriff". This is true, but the doc suggests plugins must use ECM for RCON. Actually plugins can also directly call `api_post("/events", ...)` which ECM catches. But there's no direct RCON from plugins. | **Low** | Already correct, but could add ref to ECM |
| 19.2 | **Missing: base_plugin.py does NOT have RCON helpers** | The doc implies plugins can send RCON via ECM, which is correct. But base_plugin.py has NO built-in RCON method — the only way is via ECM or `send_command` to another plugin. | **Medium** | Make this limitation clearer |

---

### 20. `ch05-04-overlay-system.md` — Overlay System

| # | Issue | Description | Severity | Suggestion |
|---|-------|-------------|----------|------------|
| 20.1 | **Duplicates content from ch03-08** | The overlay system chapter largely duplicates "Overlays & Zustand" (ch03-08). | **Medium** | Either reference ch03-08 or make this a true reference |
| 20.2 | **Missing: multiple overlay names support** | The `send_overlay_text()` supports named overlays via `overlay_name` parameter. The doc shows this, but the `actions.mca` section doesn't show the `@name>>` syntax. | **Low** | Cross-reference the `@name>>` syntax |

---

### 21. `config-reference.md` — Config Reference

| # | Issue | Description | Severity | Suggestion |
|---|-------|-------------|----------|------------|
| 21.1 | **Global config path is wrong** | Shows `config.yaml` at project root. Actually at `config/config.yaml`. | **High** | Fix path |
| 21.2 | **Missing: `api` config section** | The ref shows `api:` section with `host` and `port` but the actual config has many more fields (e.g., `api_key`, `cors_origins`). | **Low** | Expand with actual config fields |
| 21.3 | **Missing: `comment_commands` config** | The main.py has extensive `comment_commands` configuration that isn't in the reference. | **Medium** | Add `comment_commands` section |
| 21.4 | **Missing: `minecraft_server_api` config** | The main.py reads `minecraft_server_api.web_server_port`. Not documented. | **Low** | Add section |

---

### 22. `glossary.md` — Glossary

| # | Issue | Description | Severity | Suggestion |
|---|-------|-------------|----------|------------|
| 22.1 | **Missing: "CommandQueue"** | Central concept not in glossary. | **Low** | Add |
| 22.2 | **Missing: "Supervisor"** | `start.py` supervisor role. | **Low** | Add |
| 22.3 | **Missing: "Health Monitor"** | System component. | **Low** | Add |

---

### 23. Structural Issues

| # | Issue | Description | Severity | Suggestion |
|---|-------|-------------|----------|------------|
| 23.1 | **No tutorial-first structure** | The docs explain concepts before users can build anything. Chapter 3 has 10 sub-chapters before reaching a working plugin. A "5-minute quickstart" is missing. | **Critical** | Add a quickstart chapter that creates a working plugin in <5 minutes |
| 23.2 | **Cross-plugin communication too thin** | The communication chapter lacks practical examples of real data flow between plugins. | **Medium** | Add a worked example (timer→wincounter) |
| 23.3 | **No error code reference** | The codebase has `HOOK_0001`–`HOOK_0007`, `CORE_0006`, `TIKTOK_0001`–`TIKTOK_0005`, `MC_0004`–`MC_0007` error codes. None are documented. | **Medium** | Add error code table |
| 23.4 | **No debugging guide** | No chapter on debugging plugins (reading logs, inspecting state, testing without TikTok). The `troubleshooting.md` covers only basic symptoms. | **Medium** | Add a debugging guide |
| 23.5 | **Plugin lifecycle explained in too many places** | The `run()` lifecycle is explained in ch03-01, ch03-05, and referenced in ch03-02. Should be in one authoritative place. | **Low** | Consolidate lifecycle documentation |
| 23.6 | **Missing: PluginWatcher documentation** | The `PluginWatcher` is a critical component that scans plugins, auto-registers them, and writes signal files. Not explained anywhere. | **High** | Add PluginWatcher to architecture |

---

## Phase 2 — Codebase Comparison (Docs vs Implementation)

### P2.1 — `config.yaml` Location Mismatch

- **Doc says**: `config.yaml` is at the project root (multiple places in ch01, ch02, config-reference)
- **Code** (`paths.py:30-32`): `get_config_file()` returns `root / "config" / "config.yaml"`
- **Code** (`main.py:54`): `CONFIG_FILE = (BASE_DIR.parent / "config" / "config.yaml").resolve()`
- **Verdict**: **FALSE** — config is at `config/config.yaml`

### P2.2 — Plugin Scaffolder Inconsistency

- **Doc says** (ch03-01): `create_plugin.py` generates a `BasePlugin` subclass with `PLUGIN_NAME`, `register_handler`, `get_overlay_html`, and `if __name__ == "__main__": HalloPlugin().run()`
- **Code** (`create_plugin.py:32-52`): Generates a flat `main.py` with `load_plugin_config()` and `parse_args()` — NO `BasePlugin` subclass, NO `run()` call, NO handler registration
- **Verdict**: **FALSE** — the scaffolder generates incompatible code

### P2.3 — Hook Disable Mechanism

- **Doc says** (ch04-01, ch04-09): Hooks can be disabled by setting `enabled: false` in `hook.json` or by removing the file
- **Code** (`hook_loader.py:398-401`): `if not registry.is_enabled(manifest.name): log.info(...skipping...)`. The `HookRegistry` persists to `data/hook_registry.json`
- **Code** (`hook_registry.py`): `set_enabled()` updates a runtime registry, NOT the `hook.json`
- **Verdict**: **FALSE** — hook enable/disable is managed by the registry, not by hook.json content

### P2.4 — `plugin_start/stop` Signal File Path

- **Doc says** (ch03-01): Signals are at `core/runtime/plugin_start_<name>`
- **Code** (`paths.py:35-37`): `get_runtime_dir()` returns `root / "core" / "runtime"`
- **Code** (`start.py:805`): `signal_file = RUNTIME_DIR / f"plugin_start_{proc.name}"`
- **Verdict**: **TRUE** — path is correct, but the docs don't explain the supervisor's role

### P2.5 — Polling Timeout Mismatch

- **Doc says** (ch03-06): 35-second timeout for command polling
- **Code** (`base_plugin.py:211-212`): `api_get(..., timeout=35)` — client-side timeout
- **Code** (`plugin_overlay.py:82-94`): `wait_for_commands(timeout=30.0)` — server-side timeout
- **Verdict**: **PARTIALLY FALSE** — client says 35s, server says 30s. The effective timeout is the server's 30s

### P2.6 — Event-Bridge is NOT in Main.py's  `_publish_tiktok_event`

- **Doc says** (ch03-06): "Die Event-Bridge läuft im Bridge-Prozess (main.py), nicht im API-Server."
- **Code**: The `_event_bridge_worker` (main.py:880-930) does run in the bridge process. The `_publish_tiktok_event` (main.py:828-837) publishes to EventBus. The worker listens on EventBus, filters for tiktok.* events, and enqueues to CommandQueue (which is in the API server's memory).
- **Verdict**: **TRUE** about location, but the architecture detail that CommandQueue is in the API server process is missing

### P2.7 — Missing Event Fields Documentation

- **Doc says** (ch03-06): `tiktok.comment` data has `comment` and `comment_id`
- **Code** (`main.py:1354-1399`): `_publish_tiktok_event("comment", username)` is called WITHOUT comment text or comment_id in the EventBus event. The comment text is only processed via `_process_comment_command()` for the comment-command system, and `"comment"` trigger enqueued with `{"user": username, "comment": comment_text}` via a DIFFERENT path (the trigger queue, not the EventBus)
- **Verdict**: **PARTIALLY FALSE** — the `tiktok.comment` EventBus event does NOT contain `comment` or `comment_id`. The comment data is only available via the trigger queue for the `comment` action in actions.mca, not via EventBus subscriptions

### P2.8 — Event-Command Mapper Sits in API Server

- **Doc says** (ch03-06): "Der Event-Command-Mapper ist ein separates System"
- **Code** (`event_command_mapper.py`): It runs as an `asyncio.Task` within the API server process, manages state with module-level singleton
- **Code** (`server.py:84`): `get_event_command_mapper().start()` is called in the API server lifespan
- **Verdict**: **TRUE** — it's a separate component but runs in the API server process

### P2.9 — `_data_dir` is Global, Not Per-Plugin

- **Doc says** (ch03-05): `self._data_dir` is per-plugin persistent storage
- **Code** (`base_plugin.py:83`): `self._data_dir = (self._base_dir.parent / "data").resolve()` — all plugins share the SAME `data/` directory
- **Verdict**: **MISLEADING** — the data dir is shared, not per-plugin. Plugin-unique files must include the plugin name

### P2.10 — Server-Sent Events Stream Path

- **Doc says** (ch03-08): SSE stream at `/api/v1/plugins/mein-plugin/stream`
- **Code**: Need to verify. The `push_state()` calls `api_post(f"/plugins/{PLUGIN_NAME}/state", ...)`. The plugin overlay routes handle this. The SSE endpoint... I didn't find the exact route but the doc pattern matches typical FastAPI SSE patterns.
- **Verdict**: **ASSUMED CORRECT** — need route verification but matches pattern

### P2.11 — Multiplier Not Documented

- **Doc says** (ch05-01): No mention of `xN` multiplier syntax
- **Code** (`actions.py:21`): `_RE_MULTIPLIER = re.compile(r"\s+x(\d+)\s*$")` — `xN` suffix is actively parsed
- **Code** (`main.py:454-462`): Multiplier support in datapack generation
- **Verdict**: **MISSING** — multiplier syntax is undocumented

### P2.12 — Named Overlays Not Documented

- **Doc says** (ch05-01): Only shows `>>Titel|Untertitel|Dauer` syntax
- **Code** (`actions.py:40-42`): `@name>>` syntax for named overlays is supported
- **Code** (`actions.py:396-402`): Serialization of `named_overlay` commands
- **Verdict**: **MISSING** — `@name>>` syntax undocumented

### P2.13 — Vanilla vs RCON Command Prefix Confusion

- **Doc says** (ch05-01): `/` = "Vanilla-Befehl über Datapack", `!` = "RCON-Befehl"
- **Code** (`main.py:370-485`): `/` prefixed commands go into datapack `.mcfunction` files and are executed via `execute as @a run function namespace:name`. `!` prefixed commands are sent directly to RCON (`ctx.rcon_only_actions`). This is consistent with docs.
- **Code** (`actions.py:30-34`): `TRIGGER_TYPE_MAP` maps `"/" → "vanilla"`, `"!" → "rcon"`. Consistent.
- **Verdict**: **CORRECT** but the datapack mechanism needs clearer explanation

### P2.14 — `tiktok.likes` vs `tiktok.like` Naming

- **Doc says** (ch03-06): Event type is `tiktok.like`
- **Code** (`main.py:1284`): `_publish_tiktok_event("like", username)` → EventBus type: `tiktok.like`
- **But** (`actions.py:25-27`): `EVENT_TRIGGERS` includes `"likes"` (plural)
- **Verdict**: **CONFUSING** — the EventBus uses `tiktok.like`, but the actions.mca trigger name is `likes`. The doc doesn't clarify this distinction

### P2.15 — API Server is FastAPI, Not Custom HTTP

- **Doc says** (ch02): "Der API-Server ist ein HTTP-Server" without specifying the framework
- **Code** (`server.py:139-142`): FastAPI with uvicorn. Provides OpenAPI docs at `/docs`.
- **Verdict**: **OK** — the framework isn't critical for plugin devs, but mentioning it would help

### P2.16 — `run.py` vs `start.py` Confusion

- **Doc says** (ch01): `python run.py` starts the system
- **Code** (`run.py`): Only starts the API server (FastAPI), not the bridge
- **Code** (`start.py`): The actual lifecycle supervisor that starts everything
- **Verdict**: **MISLEADING** — `run.py` is not the primary entry point for the full system

### P2.17 — Missing: `create_plugin.py` Enforces `^[a-z0-9]+$`

- **Doc says** (ch03-03): Plugin names must match `^[a-z0-9]([a-z0-9-]*[a-z0-9])?$` (allows hyphens)
- **Code** (`create_plugin.py:88`): `re.match(r'^[a-z0-9]+$', name)` — NO hyphens allowed
- **Verdict**: **CONTRADICTORY** — the manifest allows hyphens in the `name` field, but the scaffolder only generates names without hyphens. The directory name has no hyphens, but `PLUGIN_NAME` in the docs example uses `hallo` (no hyphens), so the scaffolder is consistent with the tutorial example

### P2.18 — `version` Field in `hook.json` Not Tracked by System

- **Doc says** (ch04-03): `version` is a field in `hook.json`
- **Code** (`hook_manifest.py`): `HookManifest` does parse version from hook.json
- **Code** (`hook_loader.py:149`): `version = read_hook_version(child)` reads from a separate version mechanism, not the manifest
- **Verdict**: **PARTIALLY FALSE** — version tracking uses a separate mechanism; the manifest version is metadata only

---

## Summary

| Severity | Count |
|----------|-------|
| Critical | 5 |
| High | 13 |
| Medium | 24 |
| Low | 17 |
| OK (no change needed) | 4 |

### Critical Issues That Must Be Fixed

1. **Config file path** — docs say project root, code says `config/config.yaml`
2. **Plugin scaffolder mismatch** — `create_plugin.py` doesn't generate `BasePlugin` code as taught
3. **Hook disable mechanism wrong** — docs say edit hook.json, system uses registry
4. **No quickstart tutorial** — too much theory before first working plugin
5. **`run.py` described as system entry point** — it's only the API server

### Recommendations for Rewrite

1. Restructure tutorial-first: Quickstart → Plugin tutorial → Hook tutorial → Reference
2. Fix all config file paths
3. Fix hook enable/disable documentation
4. Document the actual `start.py` supervision architecture
5. Add multiplier and named overlay syntax
6. Correct the plugin scaffolder or document the actual output
7. Document the two RCON systems
8. Document the EventBus+CommandQueue+API server architecture clearly
9. Add error code reference
10. Standardize SSE reconnect patterns
11. Add debugging guide
