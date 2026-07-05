# Documentation Clarity Review — TikTok2Mc Dev Book

**Review Date:** 2026-07-04
**Scope:** `docs/dev-book-de/src/` (29 files)

---

## 1. Overall Assessment

**Usable: Partially**

The documentation is **well-structured and conceptually sound** for a reader who already understands the system's architecture. A developer familiar with Python and basic pub/sub patterns can follow most tutorials. However, **several critical gaps and inconsistencies** prevent the documentation from being fully self-sufficient. A developer attempting to implement plugins or hooks without consulting source code will hit concrete blockers.

---

## 2. Major Problems

### P1: Inconsistent naming convention between Quickstart and Plugin Structure chapter

**Files:** `ch01-00-getting-started.md`, `ch03-01-your-first-plugin.md`, `ch03-02-plugin-structure.md`
**Section:** All examples

**What:** The Quickstart and "Dein erstes Plugin" create a plugin named `meinplugin` (no hyphen, lowercase only). Directory is `src/plugins/meinplugin/`, `PLUGIN_NAME = "meinplugin"`, and the implied `plugin.json` name is `"meinplugin"`. But `ch03-02-plugin-structure.md` explicitly documents a naming convention table stating:
- `name` in `plugin.json` → Kebab-Case (`mein-plugin`)
- Directory name → lowercase + digits only (`meinplugin`)
- `PLUGIN_NAME` → exactly like `name` in json

The full example in ch03-02 uses `"name": "mein-plugin"` and `PLUGIN_NAME = "mein-plugin"` — directly contradicting the preceding chapters where the same plugin uses `"meinplugin"` throughout.

**Why it's a problem:** A developer following the Quickstart will create a plugin with `"name": "meinplugin"`, then read ch03-02 and be told the name must be kebab-case. They cannot determine which convention is correct without reading source code or testing.

**Improvement needed:** Align the Quickstart tutorial with the documented convention. Or document that both work but which is preferred.

---

### P2: `comment_handler` field in plugin.json manifest is undefined

**File:** `ch03-02-plugin-structure.md`, line 43
**Section:** "Wichtige optionale Felder"

**What:** The table lists `comment_handler` as an optional field with description "Deklaration, dass das Plugin auf TikTok-Kommentare reagiert". No further explanation exists anywhere in the documentation — not in Events chapters, not in the FAQ, not in config reference. The expected type, value format, and behavior are completely absent.

**Why it's a problem:** A developer who wants to handle comments sees this field and has no idea what to put there (boolean? string? object?). They must read source code to discover its meaning.

**Improvement needed:** Either document the field's type and behavior, or remove it from the table if it's not yet ready.

---

### P3: Error code format is inconsistent (underscore vs. hyphen)

**Files:** `error-codes.md` vs. `ch04-03-hook-api.md` vs. `troubleshooting.md`

**What:** `error-codes.md` explicitly states the format as `SUBSYSTEM-NNNN` (hyphen) and lists `HOOK-0001`, `HOOK-0002` etc. But `ch04-03-hook-api.md` lists them as `HOOK_0001`, `HOOK_0002` (underscore). `ch04-01-your-first-hook.md` references `HOOK_0007` (underscore). The troubleshooting section uses plain text like `[HOOK] has no register() function — skipped` without any code.

**Why it's a problem:** A developer searching logs for error codes doesn't know which format to grep for. The mismatch suggests the documentation was written against different code versions.

**Improvement needed:** Decide on one format and apply it consistently everywhere.

---

### P4: Thread-safety of `self._state` is contradictory

**File:** `ch03-04-plugin-api.md`, lines 38–44
**Section:** "Zustandsverwaltung"

**What:** The note says `self._state["key"] = val` bypasses the lock and recommends alternatives. But two paragraphs below, the threading hint says `self._state` and `self.state` are thread-safe. The example code then uses `self._state["count"] = self._zaehler` and calls it "OK".

**Why it's a problem:** A developer cannot determine whether direct `_state` mutation is safe or not. Is the lock important or not? The conflicting guidance could lead to subtle race conditions or overly complex code.

**Improvement needed:** Clarify: is `_state` internally locked or not? If it is, remove the warning. If it isn't, explain when race conditions can actually occur and when they don't matter.

---

### P5: `enabled` field in hook.json — documented inconsistently

**Files:** `ch04-01-your-first-hook.md` (line 127) vs. `ch04-02-hook-structure-and-manifest.md` (line 31)

**What:** 
- `ch04-01` says: "Setze in der `hook.json` das Feld `"enabled"` im `config_schema` auf `false`"
- `ch04-02` lists `enabled` as a top-level optional field in `hook.json`, documented as "Ob der Hook beim Start geladen wird (Default: `true`)"

Putting `"enabled"` inside `config_schema` is semantically wrong — `config_schema` defines the *schema for config.yaml*, not the manifest itself. The instruction in ch04-01 would create an invalid or ignored field.

**Why it's a problem:** A developer following ch04-01's instructions will set `enabled` in the wrong place and the hook will not be disabled as expected.

**Improvement needed:** Fix ch04-01 to reference the correct manifest-level `enabled` field.

---

### P6: Plugin overlays are duplicated across two chapters with inconsistent detail

**Files:** `ch03-07-overlays-and-state.md` (161 lines) vs. `ch05-04-overlay-system.md` (72 lines)

**What:** Both chapters describe overlays, but:
- `ch03-07` is comprehensive (SSE, push_state, theme_style, `register_overlay()`, persistence, pywebview, troubleshooting table)
- `ch05-04` is a shallow summary referencing back to hooks and actions.mca

A reader looking for overlay information might read ch05-04 (under "Aktionen & Minecraft") and miss the detailed documentation in ch03-07.

**Why it's a problem:** Redundant, confusing navigation. A developer following the chapter sequence linearly will encounter overlays twice and might not realize ch03-07 has crucial information not in ch05-04.

**Improvement needed:** Consolidate into one primary location and cross-reference from the other.

---

### P7: No HTTP API contract reference for non-Python plugins

**Files:** `faq.md` (line 7), `ch03-04-plugin-api.md`

**What:** The FAQ states "Plugins können in jeder Sprache geschrieben werden" but there is no specification of the HTTP API contract that a non-Python plugin must implement. The docs only describe the Python `BasePlugin` class. A developer writing a plugin in another language needs to know:
- Exact request/response formats for every endpoint
- Authentication (if any)
- Health check expectations
- The command polling protocol details
- How to register the plugin with the system

**Why it's a problem:** The claim of multi-language support is misleading — it's technically true but practically impossible from this documentation alone.

**Improvement needed:** Either provide an HTTP API reference, add a warning that only Python is documented, or remove the claim.

---

### P8: `min_api_version` — no way to determine the current API version

**Files:** `ch03-02-plugin-structure.md`, `ch04-02-hook-structure-and-manifest.md`

**What:** Both manifest references document `min_api_version` as an optional field, but nowhere does the documentation specify:
- What the current API version is
- Where to find API version information (code constant, endpoint, changelog)
- What happens specifically when versions mismatch (error code `PLUGIN-0007` is listed but no details)

**Why it's a problem:** A developer cannot meaningfully use this field. They don't know what version to put or what the system expects.

**Improvement needed:** Document the current API version and how it's maintained.

---

### P9: Project directory structure (`src/core/` vs `src/python/`) not explained

**Files:** `ch02-00-core-concepts.md`, architecture diagram

**What:** The architecture diagram shows:
- Supervisor at `src/python/start.py`
- Bridge at `src/python/main.py`
- API server at `src/core/api/server.py`

Code examples import from `from core.base_plugin import BasePlugin`. The relationship between `src/core/` and `src/python/` is never explained. A developer doesn't know whether `core` is a separate package, a symlink, or how Python resolves these imports.

**Why it's a problem:** When debugging import errors or trying to understand the codebase structure, the developer cannot reason about the module layout.

**Improvement needed:** Either explain the Python module/package layout or cross-reference to the project's own README.

---

## 3. Minor Issues

### M1: Incomplete `on_tick()` example

**File:** `ch03-04-plugin-api.md`, lines 108–113

The example uses `self._remaining` but never shows where this attribute is initialized. A developer copying this pattern will get an `AttributeError`.

---

### M2: Hook deactivation guidance in ch04-01 is imprecise

**File:** `ch04-01-your-first-hook.md`, line 127

"Hooks, die nicht geladen werden sollen, können auch aus dem Verzeichnis `src/hooks/` entfernt werden." — This is technically true but unusual. Typically you'd disable via config, not delete files. Consider softer language.

---

### M3: Event-Bridge vs Event-Command-Mapper overlap in ch03-05

**File:** `ch03-05-events-and-subscriptions.md`, section "Zwei Wege zu deinem Plugin"

The two paths differ in source (TikTok-only vs all EventBus), but both ultimately enqueue commands to the plugin's CommandQueue. The table doesn't explain *why* there are two nearly-identical delivery mechanisms. A developer might wonder when to prefer one over the other for custom events.

---

### M4: `get_hook_config()` parameter unclear

**File:** `ch04-03-hook-api.md`, line 83

The method's parameter is `name` but it's not explicitly documented what this name refers to — the hook directory name, the hook's `name` in `hook.json`, or something else. The example uses `"sprung"` which happens to be all three, but this isn't explained.

---

### M5: No example of a headless/minimal plugin

**File:** `ch03-04-plugin-api.md` (and preceding)

`get_overlay_html()` is required, but there's no example of a minimal valid return value for a plugin that doesn't need an overlay. A developer creating a backend-only plugin doesn't know what to return.

---

### M6: `self.run()` — no shutdown/cleanup documentation

**Files:** `ch03-04-plugin-api.md`, `ch03-01-your-first-plugin.md`

`run()` blocks indefinitely. There's no documentation on graceful shutdown, signal handling, `atexit` registration, or what happens when the supervisor kills the process. A plugin that opens network connections or writes files needs this.

---

### M7: `capabilities` field in plugin.json is vague

**File:** `ch03-02-plugin-structure.md`, line 39

"Freie Schlagwörter für das System, z. B. `["timer:countdown"]`" — What does the system do with these? Are they used for discovery, filtering, something else? How are they consumed?

---

### M8: Event data structures in ch03-05 lack `tiktok.like` delta explanation

**File:** `ch03-05-events-and-subscriptions.md`, lines 70–78

The `tiktok.like` example shows `"delta": 3` and `"total": 150` but doesn't explain the semantics: is `delta` the increment, is `total` the session total or lifetime total? The comment event also has an empty `data` dict — missing `comment` and `comment_id` that were promised in ch03-01.

---

### M9: `api_post()` and `api_get()` base URL assumption

**File:** `ch03-04-plugin-api.md`, line 59

The methods prepend `http://127.0.0.1:29185/api/v1/` hardcoded. If the API server runs on a different host/port (as suggested by `config.yaml` options in `config-reference.md`), these methods would break. No mention of how the base URL is determined.

---

### M10: Glossary says `src/python/main.py` but code imports from `core`

**File:** `glossary.md` (Bridge-Prozess entry)

The glossary points to `src/python/main.py` as the Bridge process, but the code examples throughout import from `core.*` modules. The relationship is not explained.

---

### M11: `push_state()` vs SSE endpoint inconsistency

**File:** `ch03-07-overlays-and-state.md`, line 48

The docs say `push_state()` sends `POST /api/v1/plugins/{name}/state` but the SSE connection in the JavaScript is `/api/v1/plugins/{name}/stream`. The difference between `state` (REST endpoint) and `stream` (SSE endpoint) is not explained — a developer might try to connect to the wrong URL.

---

### M12: Missing information about `event_subscriptions` wildcard

**File:** `ch03-05-events-and-subscriptions.md`, line 24

The wildcard `"tiktok.*"` is mentioned in passing but only shown for TikTok events. Can the wildcard be used for custom event namespaces too? Not explained.

---

### M13: `send_overlay_text()` return value documented in ch05-04 but not ch04-03

**File:** `ch04-03-hook-api.md` vs `ch05-04-overlay-system.md`

`ch05-04` says the function returns `True`/`False`. `ch04-03` mentions this in `send_overlay_text` entry (line 106). ✓ Actually this is consistent. But ch04-03 doesn't mention what causes `False`.

---

### M14: No format specification for `version.txt`

**File:** `ch03-02-plugin-structure.md`, line 13

Mentioned as an automatically created file, but the format is never shown. Is it just a single version string? Does it have a trailing newline? Is it read by the system?

---

### M15: RCON command length limit detail

**File:** `ch05-03-rcon-and-minecraft.md`, line 54

"ca. 1400 Zeichen" — This is loose language. The actual Minecraft RCON limit is well-documented (1463 bytes including header). The vague "ca." could lead to a developer hitting the limit unexpectedly.

---

## 4. Missing Knowledge — What a Developer Still Needs From Source Code

A developer **cannot** fully implement plugins and hooks from this documentation alone. They would need to consult source code for:

| # | Missing Knowledge | Why It's Needed |
|---|---|---|
| 1 | **Full HTTP API contract** | To write a plugin in any language other than Python (FAQ claim). Endpoints, request/response bodies, status codes, error formats. |
| 2 | **Current API version for `min_api_version`** | No documented location or value for the current API version. |
| 3 | **`BasePlugin.__init__` internals** | To understand what `super().__init__()` does, how `self.config`, `self._state`, `self._data_dir` are initialized, and whether custom `__init__` parameters are possible. |
| 4 | **Signal file mechanism `core/runtime/`** | The docs mention signal files (`plugin_start_<name>`, `plugin_stop_<name>`) but not their format, polling interval, or how the plugin process detects the stop signal. |
| 5 | **HookAPI implementation details** | The exact behavior of `rcon_enqueue()`, `enqueue_trigger()`, and how queue full / chain depth are enforced at the code level. |
| 6 | **How `api_post("/events", ...)` reaches the Bridge Process's EventBus** | The API server and Bridge process are separate processes. How does a POST to the API server publish to the EventBus in the Bridge? This is a significant architectural gap. |
| 7 | **`execute_global_command()` behavior** | Referenced multiple times but never fully documented. What exactly does it do with each action type? Error handling? Return values? |
| 8 | **Config healing algorithm** | Mentioned as "Healing" but the rules for when and how invalid/missing fields are corrected are not specified. |
| 9 | **`PluginWatcher` scan interval and triggers** | When exactly does the watcher rescan? On startup only? Periodically? On file change events? |
| 10 | **`data/api_plugin_registry.json` and `data/hook_registry.json` format** | If a developer needs to debug registry issues, they need to understand the file format. |

---

## 5. Final Verdict

**Can a developer realistically build plugins and hooks using only this documentation?**

### Plugins: Partially

A developer can **build a basic Python plugin** by following the tutorials. The lifecycle, event handling, overlay, and configuration patterns are sufficiently documented with working examples. However, they will be blocked or slowed by:

- The **contradictory naming convention** (P1) — uncertainty about which convention to use
- **No HTTP API reference** (P7) — cannot write non-Python plugins despite documentation claiming it's possible
- **No `min_api_version` guidance** (P8) — cannot use the compatibility check feature
- **Contradictory `_state` thread-safety** (P4) — risk of subtle bugs
- **No shutdown/cleanup documentation** (M6) — plugins that use external resources may not shut down gracefully
- **Undocumented `comment_handler`** field (P2) — broken by design if a developer tries to use it

### Hooks: Partially

A developer can **build a simple hook** by following the tutorial. The `register()` pattern, `$`-command flow, and `actions.mca` integration are well explained. However:

- The **`enabled` field misplacement** (P5) — the tutorial tells users to put it in `config_schema` which is wrong
- **No explanation of how to debug hooks that fail silently** — error handling guidance is thin
- **Import restrictions are clear** ✓ (this part is well done)
- **No guidance on testing hooks without the full system** — the test instructions only cover plugins

### Overall: Partially

The documentation is **structurally well-organized** with a logical progression. Tutorials exist for both extension types. The architecture diagram and communication flow diagrams are excellent. However, **at least 5 critical issues** (P1–P8, especially naming, error codes, enabled field, HTTP contract, thread-safety) **will cause concrete failures** for a developer who follows the documentation literally without also reading source code.

The documentation reads like it was written by someone intimately familiar with the codebase but not yet validated by a developer who only has the docs. A thorough **technical review by a fresh developer** following the tutorials end-to-end would likely uncover additional gaps.

**Recommendation:** Focus fixes on P1 (naming alignment), P3 (error code consistency), P5 (hook `enabled` field), P7 (HTTP API contract), and P8 (current API version) as these are the issues most likely to cause immediate developer confusion or failure.
