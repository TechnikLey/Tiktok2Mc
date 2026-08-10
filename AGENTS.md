# AGENTS.md — TikTok2Mc

## 1. Overview & Stack
TikTok Live → Minecraft: viewer gifts/follows/likes/comments trigger MC commands (RCON/datapack), overlays, plugins, or shell commands. Multi-process Python desktop app: FastAPI control plane (port `29185`), web dashboard, plugin/hook system, Minecraft server manager.

**Stack:** Python 3.12 · FastAPI/uvicorn · Flask (legacy webhook) · TikTokLive 6.6.5 · mcrcon · pywebview+PyQt6 · PyYAML+ruamel.yaml (comment-preserving) · PyInstaller · pytest · Vitest+jsdom · Node/VSCode LSP (`.mca`) · mdBook

## 2. Architecture
- **Supervisor** `src/python/start.py` runs the FastAPI control plane in-process (`create_app`, `core/api/server.py`) and spawns: `main.py` (bridge), `gui.py`, plugins, overlay, update. `run.py` = standalone dev API server.
- **Bridge** `src/python/main.py`: TikTokLive events → `BotContext` queues → RCON `/`, datapack, overlay `>>`, shell `&`, hooks `$`. Publishes to in-process `event_bus` (`api/eventbus.py`). **Most sensitive file** (events/queues/retries) — minimize changes.
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
| `templates/gui/` | Web dashboard (vanilla JS): `app.js`, `actions-editor.js`, `index.html`, `launcher.html`, `style.css`, `design-system.css`; tests in `tests/` (vitest) |
| `mca-language-server/` | VSCode extension + JS language server for `.mca` (parity with Python validator); tests in `server/test/` |
| `defaults/` | Templates copied to `config/`+`data/` on first run: `config.yaml`, `actions.mca`, `gifts.json`, `event_commands.yaml`, server configs |
| `tests/` | pytest: `test_core/`, `test_api/`, `conftest.py` (WriteGuard + heavy-dep mocks), `workspace/` (only writable area) |
| `docs/dev-book-{en,de}/src/` | mdBook docs — keep both languages in sync |
| `tools/` | `diff_test_mca.py` (Python↔JS diff), `generate_mca_spec.py`, `update_test/` (updater E2E harness, see `README.md`) |

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
Four layers: Python (pytest + static analysis), GUI (vitest + ESLint), MCA (JS LSP + parity diff), updater E2E (`tools/update_test/`). CI (`.github/workflows/`) runs pytest + build; static analysis tools are local-only.

### 7.1 Python — pytest, pyright, ruff
- **pytest** — test framework/runner. Config `pytest.ini`: asyncio auto-mode, markers `integration`/`unit`/`validator`, 40 s timeout. `tests/conftest.py` installs a **WriteGuard** — writes outside `tests/workspace/` raise `PermissionError`; never point tests at real `config/`/`data/`.
  - Commands: `pytest tests/` · `pytest tests/test_core/test_x.py -m unit` · `pytest tests/test_api/`
  - When: after any Python change — run the relevant `test_<module>.py`; full suite before merge/PR.
- **pyright** — static type checker (optional; **not in CI, not in `requirements.txt`, no config file in repo**).
  - Commands: `pyright` or `pyright <path>`
  - When: after type-hint-sensitive changes (Pydantic models, API, `trigger_engine`); local check before committing.
- **ruff (format)** — the project's **formatter** (Python only). All Python files are formatted with `ruff format`; scope is `[format]` in `ruff.toml` (restricted to `.py`/`.pyi` — non-Python files are never changed purely for formatting). `ruff format` is the one and only formatting style — don't replace it with hand-made formatting. Formatting is **required**, not optional.
  - Commands: `ruff format .` · `ruff format --check .`
  - When: after any change to Python files, run `ruff format` on the touched files; `ruff format --check .` must pass before committing.
- **ruff (lint)** — linter (optional; **not in CI**). Config: `ruff.toml` — curated `select` that passes clean (`ruff check .` = 0 findings); rules with remaining findings are listed there as *deferred* (fix them, then move from deferred into `select`). Broad-except policy `BLE001`/`S110` is enforced via per-file-ignores (error-boundary architecture, see the config comments).
  - Commands: `ruff check .` · `ruff check --fix .` · `ruff check --select <deferred-rule> .` (inspect a deferred rule)
  - When: after Python changes, before committing; keeps style consistent.

### 7.2 GUI — Vitest + jsdom, ESLint
- **Vitest + jsdom** (`templates/gui/vitest.config.js`, `templates/gui/package.json`): DOM-level tests in `templates/gui/tests/*.test.js` (dashboard, actions-editor, config-editor, plugin-config-editor, server-manager, helpers).
  - Commands: `cd templates/gui && npm test` (aliases: `test:watch`, `test:ui`)
  - When: after any change under `templates/gui/`.
- **ESLint** (`templates/gui/eslint.config.js`, eslint 10): lint for `templates/gui/`.
  - Command: `cd templates/gui && npx eslint .`
  - When: after GUI changes, before committing.

### 7.3 MCA Language Server & parity tests
- **LSP tests** (`mca-language-server/server/test/`: `run.js` + `test_parser.js`, `test_validator.js`, `test_spec.js`, `test_hover.js`, `test_completions.js`; `benchmark.js` = performance benchmark).
  - Commands: `node mca-language-server/server/test/run.js` (also `npm test` inside `mca-language-server/`)
  - When: after any change to the JS language server.
- **Python ↔ JS parity** (`tools/diff_test_mca.py`): generates hundreds of valid/invalid `.mca` snippets, runs Python validator and JS language server, reports every mismatch.
  - Commands: `python tools/diff_test_mca.py --count 500` (optional `--seed S`); npm script `diff-test` inside `mca-language-server/`
  - When: after any `.mca` handling change (Python `validator.py`/`services/actions.py`, JS `server/`, spec generation).

### 7.4 Updater E2E test harness
- **Purpose:** `tools/update_test/` runs the **compiled** updater (`update.exe`/`update.bin`) against a local GitHub-compatible mock server, exercising the real `src/python/update.py` path: version check, asset selection, download, checksum, extraction, self-update, whitelisted copy, config migration, exit codes. Only the HTTP source is simulated (via `TIKTOK2MC_UPDATE_SOURCE`); everything else is the real binary.
  - Commands: `python build.py app --only update` (build first — the harness never builds itself) → `python tools/update_test/run_update_test.py --list` / `success` / `all` (add `--clean` for a from-scratch run). Port `29185` must be free.
  - When: after any change to `src/python/update.py` or the release asset naming/checksums; also update scenarios/`mock_github.py` in `tools/update_test/` if behavior changed.
  - Note: Windows Defender may flag the freshly built unsigned `update.exe` (`Behavior:Win32/DefenseEvasion.A!ml`) — heuristic false positive, see `tools/update_test/README.md`; do not work around it in code.

### 7.5 Build validation & dev tools
- `python build.py test` — runs the MCA LSP test suite; `--all` also runs full pytest. `python build.py --check` runs `check_deps.py` first.
- `python build.py spec` — regenerates `mca-language-server/mca-spec.json` (generated file — never hand-edit).
- `python check_deps.py` — verifies Python packages + system tools (node/npm); `--install` installs everything, `--system-only` checks tools only.
- **Utility tools:** `rg` (ripgrep) for fast code search, `fd` for fast file search, `jq` for JSON parsing/inspection (configs, manifests, API output). Not part of `check_deps.py`.
- **CI:** `test.yml` runs `pytest tests/` (+ a warnings pass) on push/PR to `main`; `build.yml` runs `python build.py --installer` on version tags (Windows + Linux) and creates the GitHub release; `mdbook.yml` builds the docs.

### 7.6 Test style & validation priority
- One `test_<module>.py` per module in `tests/test_core/` or `tests/test_api/`.
- **Validation priority:** relevant pytest file → vitest (only if GUI touched) → LSP + diff test (only for `.mca` changes). Static analysis (ruff/pyright/eslint) before larger changes; `ruff format --check .` before committing.

## 8. Commands (reference)
```bash
# Environment
python check_deps.py                  # verify deps; --install / --system-only
pip install -r requirements.txt

# Dev start
python run.py --reload                # dev: API server only
python src/python/start.py            # dev: full supervisor

# Tests
pytest tests/                         # full Python suite
pytest tests/test_core/test_x.py -m unit
cd templates/gui && npm test          # GUI tests (vitest, jsdom)
node mca-language-server/server/test/run.js    # MCA LSP tests
python tools/diff_test_mca.py --count 500      # Python↔JS parity
python tools/update_test/run_update_test.py all --clean   # updater E2E harness
python build.py test                  # MCA tests (--all adds pytest)

# Validation
ruff format --check .                  # format check (config: [format] in ruff.toml)
ruff check .                          # lint (config: ruff.toml; local-only)
pyright                               # type check (not in CI; local-only)
cd templates/gui && npx eslint .      # GUI lint

# Build
python build.py spec                  # regenerate mca-spec.json
python build.py vsix                  # VSCode extension
python build.py app --installer --only <name>  # single binary + installer
python build.py all | ci | clean

# Scaffolding / utility
python create_plugin.py / create_hook.py      # plugin/hook scaffold
python src/python/send_trigger.py follow      # manual trigger test

# Search / inspect
rg <pattern> [<path>]                # fast code search
fd <pattern> [<path>]                # fast file search
jq '.key' <file.json>                # JSON parsing/inspection
```

## 9. AI Agent Workflow
Working rules:
- **Analyze first:** read `src/core/paths.py`, `src/core/version.py`, and the relevant route/service before editing.
- **Reuse existing systems** instead of re-implementing: `TriggerEngine` / `services/actions.py` for triggers, `core/validator.py` for validation, `get_x()` singletons, `ApiService`, `BasePlugin`.
- **Prefer small, scoped changes;** no drive-by refactors, touch only files the task needs.
- **Run tests after changes** (see §7 priority); resolve failures before moving on.
- **Keep docs and code in sync:** this AGENTS.md, `docs/dev-book-{en,de}/` (both languages), and the `.mca` spec.
- **Never edit generated files:** `mca-language-server/mca-spec.json` (regenerate: `python build.py spec`), `build/`, `data/backups/`.
- **No new dependencies without reason** — check `requirements.txt`/`package.json` first.
- **Ask before** touching live-stream behavior, config migration, or release packaging.

Change checklists:
- **API change:** Pydantic model (`api/models.py`) → route (`routes/`) → register in `routes/__init__.py` → tests in `tests/test_api/`.
- **`.mca` change:** mirror in Python + JS + `mca_spec.py`; verify with `tools/diff_test_mca.py`.
- **Config change:** don't remove/rename `defaults/config.yaml` keys silently; `EXPECTED_CONFIG_VERSION` bumps need `auto_update_config` migration.
- **Updater change:** update scenarios/`mock_github.py` in `tools/update_test/` if behavior changed; verify with `python tools/update_test/run_update_test.py all --clean` (build `update.exe` first via `python build.py app --only update`).
