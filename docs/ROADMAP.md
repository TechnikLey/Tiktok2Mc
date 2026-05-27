# TikTok2Mc v1.0.0 — Roadmap

> **Status:** Active development on the new FastAPI-based architecture.
> v1.0.0 is a clean break from v0.x — configs, plugins, and workflows
> from previous versions will not be compatible.

---

## What's Already Shipped

The foundation for v1.0.0 is built and working:

| Area | Status |
|------|--------|
| **FastAPI Backend** (`src/core/api/`) | ✅ Done |
| REST endpoints (health, config, plugins CRUD, events) | ✅ Done |
| PluginRegistry (thread-safe, JSON-persisted) | ✅ Done |
| EventBus (async pub/sub with SSE + WebSocket) | ✅ Done |
| PluginAPIClient + `register_plugin()` (HTTP drop-in) | ✅ Done |
| PluginLauncher (API-only, no legacy file fallback) | ✅ Done |
| `get_root_dir()` robust für dev + release | ✅ Done |
| Legacy registry removed (`python/registry.py`, `PLUGIN_REGISTRY.json`) | ✅ Done |
| `--register-only`, `plugin_updater`, registry in build | ✅ Removed |

---

## Current Phase — Consolidation

The API exists but isn't fully wired into the runtime yet. Plugins still run
as standalone Flask servers on separate ports. The focus is on turning the
API from "exists" into "is the center of everything."

| Area | Status |
|------|--------|
| Port consolidation (API routes plugin traffic) | 🔴 Not started |
| Plugin communication via EventBus | 🔴 Not started |
| API-as-primary-orchestrator (start.py integration) | 🟡 Partially done |
| Plugin manifests (`plugin.json`) | 🔴 Not started |
| `start.py` manages API server lifecycle | 🟡 Partially done |

---

## Upcoming Milestones

### Phase 1 — API Consolidation
- Wire the API server into `start.py` as the first-launched component
- Route plugin-to-plugin communication through the central API
- Introduce `plugin.json` manifests for reliable plugin discovery
- Reduce port footprint: plugins communicate over the API channel
- Integrate EventBus into plugin messaging (loose coupling)

### Phase 2 — GUI
- Desktop GUI built from scratch (tech stack TBD)
- First-run setup wizard (TikTok user, RCON password, plugin selection)
- Config editor (form-based YAML editing with validation)
- Actions editor (visual .mca trigger/command editor)
- Dashboard with live status (Minecraft, TikTok, plugins, overlays)
- Live log viewer (WebSocket/SSE)
- Plugin manager with enable/disable toggles
- Spotify setup assistant, overlay preview, theme editor

### Phase 3 — Stability
- API integration tests (every endpoint)
- Validator unit tests (.mca parsing, edge cases)
- Plugin smoke tests (each plugin starts and serves its API)
- End-to-end test (simulated stream → API → plugin → Minecraft)
- Security review (API auth, RCON password, `0.0.0.0` warnings)
- Config schema freeze (`config_version: v1.0.0`)

### Phase 4 — Release
- README.md and GUIDE.md rewritten for v1.0.0
- Dev book (EN + DE) updated — API reference, plugin lifecycle, manifests
- CHANGELOG v1.0.0 documenting all breaking changes
- Build system updated (SPA + PyInstaller if applicable)
- Platform-specific packaging (Windows installer, Linux AppImage)
- CI/CD smoke test: build → start → API responds → GUI opens

---

## What v1.0.0 Will Include

- Central FastAPI server (one port instead of a dozen)
- Desktop GUI for full control (no YAML editing required)
- Plugin opt-in model — enable only what you use
- Timer, Death Counter, Win Counter fully decoupled from each other
- Live log viewer and server dashboard
- Overlay preview with theme editor
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
