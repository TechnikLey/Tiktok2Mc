# TikTok2Mc v1.0.0 — Roadmap

> **Status:** Active development on the new FastAPI-based architecture.
> v1.0.0 is a clean break from v0.x — configs, plugins, and workflows
> from previous versions will not be compatible.

---

## What's Already Shipped

The v1.0.0 foundation is built and verified:

| Area | Status |
|------|--------|
| **FastAPI Backend** (`src/core/api/`) | ✅ Done |
| REST endpoints (health, config, plugins CRUD, events) | ✅ Done |
| PluginRegistry (thread-safe, JSON-persisted) | ✅ Done |
| EventBus (async pub/sub with SSE + WebSocket) | ✅ Done |
| PluginAPIClient + `register_plugin()` (HTTP drop-in) | ✅ Done |
| PluginLauncher (API-only, no legacy file fallback) | ✅ Done |
| **API lifecycle managed by `start.py`** | ✅ Done |
| Daemon-thread API server + health-poll before plugin discovery | ✅ Done |
| Plugin decoupling (Timer REST API, `auto_win`, `pause_on_death`) | ✅ Done |
| WinCounter decoupling (`decrement_on_death`) | ✅ Done |
| All plugins default disabled (opt-in model) | ✅ Done |
| Config schema freeze (`config_version: 1.0`, schema validation) | ✅ Done |
| Semantic versioning (`normalize_config_version()`, cross-format) | ✅ Done |
| Versioned config backups (`config.yaml.v1.bak`, …) | ✅ Done |
| `get_root_dir()` robust für dev + release | ✅ Done |
| Legacy registry removed (`python/registry.py`, `PLUGIN_REGISTRY.json`) | ✅ Done |
| `--register-only`, `plugin_updater`, `gui.py` (old) removed | ✅ Done |

---

## Current State

The API is the center of the runtime — it starts first, manages plugins,
and validates config.  What remains is hardening, testing, and closing
the gap between the API layer and the plugin communication model.

| Area | Status |
|------|--------|
| API integration tests | ✅ Done (62 tests, CI-integrated) |
| CORS lockdown (localhost-only default) | ✅ Done |
| `0.0.0.0` security warning in `run.py` | ✅ Done |
| Config validation on write (`_validate_config_schema`) | ✅ Done |
| `normalize_config_version()` single-part string fix | ✅ Done |
| Validator unit tests (.mca parsing) | 🔴 Not started |
| Updater ↔ API integration (status, signaling) | 🔴 Not started |
| API authentication (API key) | 🔴 Not started |
| Port consolidation (API routes plugin traffic) | 🔴 Not started |
| Plugin manifests (`plugin.json`) | 🔴 Not started |
| Plugin communication via EventBus | 🔴 Not started |
| GUI (new desktop app) | 🔴 Not started |
| E2E tests (stream → API → plugin → Minecraft) | 🔴 Not started |

---

## Immediate Priorities (Pre-v1.0.0)

### Phase 1 — Testing & Stability
- API integration tests (every endpoint)
- Validator unit tests (.mca parsing, edge cases)
- Plugin smoke tests (each plugin starts and serves its API)

### Phase 2 — Updater & Security
- Replace file-based `update_signal.tmp` with API endpoint
- API authentication (localhost + optional API key)
- RCON default-password warning on startup
- `server_host: 0.0.0.0` security notice

### Phase 3 — Architecture Completeness
- Port consolidation: route plugin-to-plugin communication through central API
- `plugin.json` manifests for reliable plugin discovery
- Integrate EventBus into plugin messaging (loose coupling)
- Plugin lifecycle states (installed → disabled → enabled → running → error)

### Phase 4 — GUI
- Desktop GUI (tech stack TBD: Tauri, Electron, pywebview)
- First-run setup wizard (TikTok user, RCON password, plugin selection)
- Config editor (form-based YAML editing with schema validation)
- Actions editor (visual .mca trigger/command editor)
- Dashboard with live status (Minecraft, TikTok, plugins, overlays)
- Log viewer (WebSocket/SSE)
- Plugin manager with enable/disable toggles

### Phase 5 — Release
- README.md and GUIDE.md rewritten for v1.0.0
- Dev book (EN + DE) updated — API reference, plugin lifecycle, manifests
- CHANGELOG v1.0.0 documenting all breaking changes
- E2E test (simulated stream → API → plugin → Minecraft)
- CI/CD smoke test: build → start → API responds → GUI opens
- Platform-specific packaging (Windows installer, Linux AppImage)

---

## What v1.0.0 Will Include

- Central FastAPI server (one port instead of a dozen)
- Desktop GUI for full configuration (no YAML editing required)
- Plugin opt-in model — enable only what you use
- Timer, Death Counter, Win Counter fully decoupled
- Live log viewer and server dashboard
- Setup wizard for first-time users
- Spotify setup assistant
- Integrated trigger testing
- Much fewer ports (3–4 instead of 10+)
- Complete documentation overhaul

## What v1.0.0 Will NOT Include

- Twitch / YouTube support (remains TikTok-focused)
- Mobile app
- Cloud features
- v0.x compatibility (config, plugins, data — fresh install required)

---

*Last updated: 2026-05-28*
