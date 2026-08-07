# AGENTS.md — TikTok2Mc

## 1. Overview & Stack
TikTok Live → Minecraft: viewer gifts/follows/likes/comments trigger MC commands (RCON/datapack), overlays, plugins, or shell commands. Multi-process Python desktop app: FastAPI control plane (port `29185`), web dashboard, plugin/hook system, Minecraft server manager.

**Stack:** Python 3.12 · FastAPI/uvicorn · Flask (legacy webhook) · TikTokLive 6.6.5 · mcrcon · pywebview+PyQt6 · PyYAML+ruamel.yaml (comment-preserving) · PyInstaller · pytest · Vitest+jsdom · Node/VSCode LSP (`.mca`) · mdBook

## 2. Architecture
- **Supervisor** `src/python/start.py` runs the FastAPI control plane in-process (`create_app`, `core/api/server.py`) and spawns: `main.py` (bridge), `gui.py`, plugins, overlay, update. `run.py` = standalone dev API server.
- **Bridge** `src/python/main.py`: TikTokLive events → `BotContext` queues → RCON `/`, datapack, overlay `>>`, shell `&`, hooks `$`. Publishes to in-process `event_bus` (`api/eventbus.py`).
- **Control plane** `src/core/api/`: thin routes (`routes/`) + logic (`services/`), Pydantic v2 models (`models.py`), plugin registry/launcher/watcher, health monitor, TikTok live tracker, updater.
- **Plugins** `src/plugins/*`: subprocess, `BasePlugin` long-polls `?wait=1`; manifest `plugin.json`. **Hooks** `src/hooks/*`: in-process, `register(api: HookAPI)`; manifest `hook.json`.
- **Data flow:** TikTok → bridge → queues → actions/plugins/hooks/RCON. Bridge→API `POST /api/v1/events`; GUI→API REST + SSE (`routes/ws.py`); API→GUI via EventBus.
- **Root `core/` = runtime artifacts only; source is `src/core/`.**

## 3. Repository Structure
| Path | Purpose / new code goes here |
|---|---|
| `src/python/*.py` | Entry points, one binary each (see `build.py` tasks): `start`, `main` (bridge), `gui` (pywebview), `server`, `overlay`, `update`, `send_trigger` (CLI trigger tester) |
| `src/core/` | Shared library `core.*` — API, trigger_engine, validator, paths, logger, plugins/hooks, utils |
| `src/core/api/routes/` | New REST endpoints (must be registered in `routes/__init__.py`) |
| `src/core/api/services/` | Business logic for routes; `actions.py` = `.mca` parse/serialize; `__init__.py` = `ApiService` (config read/write) |
| `src/core/trigger_engine/` | `TriggerEngine` — **only** place for trigger execution/test logic |
| `src/plugins/<name>/` | `plugin.json` + `main.py` + `config.yaml`. Scaffold: `python create_plugin.py` |
| `src/hooks/<name>/` | `hook.json` + `main.py` + `config.yaml`. Scaffold: `python create_hook.py` |
| `templates/gui/` | Web dashboard (vanilla JS): `app.js`, `actions-editor.js`, `index.html`, `launcher.html`, `style.css`, `design-system.css` |
| `mca-language-server/` | VSCode extension + JS language server for `.mca` (parity with Python validator) |
| `defaults/` | Templates copied to `config/`+`data/` on first run: `config.yaml`, `actions.mca`, `gifts.json`, `event_commands.yaml`, server configs |
| `tests/` | pytest; `tests/workspace/` is the only writable area (WriteGuard) |
| `docs/dev-book-{en,de}/src/` | mdBook docs — keep both languages in sync |
| `tools/` | `diff_test_mca.py` (Python↔JS diff), `generate_mca_spec.py` |

**Priority files (read first):** `src/core/paths.py` (dev/release layout) · `src/core/version.py` (all versions) · `src/core/api/server.py` (app factory/lifecycle) · `src/core/api/services/__init__.py` (`ApiService`, config read/write) · `src/core/validator.py` + `src/core/api/services/actions.py` (`.mca` source of truth) · `src/core/error_codes.py` · `src/core/trigger_engine/engine.py` · `src/core/base_plugin.py`

## 4. Backend Rules (Python)
- Paths via `core.paths` only (dev: `src/`, `templates/`; release: `core/...`) — never hardcode.
- Versions only in `src/core/version.py` (`TOOL_VERSION`, `API_VERSION`, `UPDATER_VERSION`, `EXPECTED_CONFIG_VERSION`).
- Singletons via `get_x()` factories (`get_health_monitor`, `get_crash_manager`); `event_bus` is a module singleton.
- Log via `core.logger.initialize_logging(__name__)` — no print logging.
- Errors: codes from `core/error_codes.py` (e.g. `TIKTOK_0001`); wrap external calls with `with_context()`. Add new codes there, don't invent inline.
- API routes thin; logic in `services/`; validate with Pydantic v2 models (`api/models.py`). Dataclasses+Enums for `trigger_engine/models.py`.
- Trigger dispatch only via `TriggerEngine` — never construct payloads or bridge calls elsewhere.
- Type hints everywhere (`X | None`); PascalCase classes, snake_case functions.
- Async via `asyncio`, supervised by `CrashManager` (`observe_task`, `supervised_async_task`).
- Don't remove the heavy-dep mocks in `tests/conftest.py` (TikTokLive, mcrcon, flask).

## 5. GUI (JS)
- Vanilla JS, no framework/bundler; globals on one object, `<script>` tags.
- API helpers at top of `app.js`: `fetchJSON`/`postJSON`/`putJSON`/`_throwResError` (`/api/v1`).
- Real-time via SSE (`/api/v1/ws`); pywebview bridge = `pywebview.api.*` (`src/python/gui.py` `LauncherAPI`).
- Shared DOM helpers stay in `app.js`; `actions-editor.js` reuses them — don't duplicate.
- Dark UI: design tokens in `design-system.css`.

## 6. Configuration System
- **User config:** `config/config.yaml` (copied from `defaults/config.yaml`; in dev this file may be absent — `ApiService` falls back to `defaults/config.yaml`). Read/written by `ApiService` (`services/__init__.py`) via ruamel — preserves comments/formatting. `write_config(replace_keys=[...])` replaces whole nested sections.
- **`auto_update_config`** merges new keys from `defaults/config.yaml` on startup while preserving user values — never remove keys silently; new defaults must stay backward compatible.
- **Actions:** `data/actions.mca` — lines `trigger:command`. Prefixes: `/` vanilla, `!` rcon/plugin, `$` script, `&` shell, `>>` overlay, `@name>>` named overlay. `;` chains, `xN` multiplier, `{user}`/`{comment}` placeholders, `##` disables, `#` comments. Gift IDs/names in `defaults/gifts.json`.
- **Plugins/hooks:** `config.yaml` next to the manifest; schema-driven GUI via `config_schema` in `plugin.json`/`hook.json`.
- **Runtime signals:** `core/runtime/` files (e.g. reload signals) are IPC, not config — don't hardcode content.

## 7. Testing & Validation
- **pytest** (`pytest.ini`): asyncio auto-mode; markers `integration`/`unit`/`validator`. `tests/conftest.py` installs a **WriteGuard** — writes outside `tests/workspace/` raise `PermissionError`; never point tests at real `config/`/`data/`.
- **GUI:** vitest in `templates/gui/` (`npm test`), jsdom.
- **MCA LSP:** `node server/test/run.js`; parity via `tools/diff_test_mca.py` (Python vs JS) — run after validator/spec changes.
- **Test style:** one `test_<module>.py` per module in `tests/test_core/` or `tests/test_api/`.
- **Validation priority:** relevant pytest file → vitest (only if GUI touched) → LSP + diff test (only for `.mca` changes).

## 8. Commands
```bash
python check_deps.py                  # verify/install dependencies
pip install -r requirements.txt
python run.py --reload                # dev: API server only
python src/python/start.py            # dev: full supervisor
pytest tests/                         # Python tests
cd templates/gui && npm test          # GUI JS tests
node mca-language-server/server/test/run.js  # LSP tests
python tools/diff_test_mca.py --count 500    # validator parity
python build.py app|spec|vsix|test|all|ci|clean  # build; --only <name> = single binary
python create_plugin.py / create_hook.py     # scaffolding
python src/python/send_trigger.py follow     # manual trigger test
```

## 9. Do / Don't
- **Analyze first:** read `src/core/paths.py`, `src/core/version.py`, and the relevant route/service before editing.
- **Scope:** touch only files the task needs; no drive-by refactors.
- **Reuse, don't re-implement:** `TriggerEngine` / `services/actions.py` for triggers, `core/validator.py` for validation, `get_x()` singletons, `ApiService`, `BasePlugin`.
- **Never edit generated files:** `mca-language-server/mca-spec.json` (regenerate: `python build.py spec`), `build/`, `data/backups/`.
- **Don't confuse root `core/` (runtime) with source `src/core/`.**
- **Config compat:** don't remove/rename `defaults/config.yaml` keys silently; `EXPECTED_CONFIG_VERSION` bumps need `auto_update_config` migration.
- **API change checklist:** Pydantic model → route → register in `routes/__init__.py` → tests in `tests/test_api/`.
- **`.mca` change:** mirror in Python + JS + `mca_spec.py`; verify with `tools/diff_test_mca.py`.
- **`src/python/main.py` is the most sensitive file** (events/queues/retries) — minimize changes.
- **After changes:** run the relevant pytest, vitest (GUI), node LSP suites.
- **Ask before** touching live-stream behavior, config migration, or release packaging.
