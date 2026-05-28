# TikTok2Mc — Project Roadmap

## Current Progress

The system works end to end. It has been fully rebuilt from the
ground up for version 1.0.0, which means existing setups from
earlier versions will need a fresh install. The old architecture
was held together by file-based configuration and hard-wired
connections between components. That is gone.

**What is stable right now:**

- TikTok Live connection works — follows, likes, shares, gifts,
  and other events come through reliably.
- Minecraft RCON connection works — commands arrive at your server
  as expected.
- All four plugins are stable and work independently:
  - **Timer** — runs a command after a set interval
  - **Death Counter** — tracks in-game deaths
  - **Win Counter** — tracks wins or milestones
  - **Overlay** — shows live notifications on stream (OBS browser
    source)
- Every plugin starts disabled by default. You choose what to turn
  on — nothing runs without your say-so.
- Plugins no longer depend on each other. Turning on the Timer
  will not accidentally trigger the Death Counter anymore.
- The central backend that manages all plugins is tested
  thoroughly. **274 automated checks** run on every change to catch
  regressions early.
- Trigger files (.mca) are validated when loaded. Mistakes like
  missing brackets or wrong command prefixes are caught before
  they reach Minecraft.
- Your configuration is backed up automatically. If something goes
  wrong during a save, the last good version is still there.
- The system warns you if you try to expose it to the internet
  accidentally (`0.0.0.0` is not the default).
- **Plugin discovery is now manifest-driven.** Each plugin ships
  with a `plugin.json` manifest that declares its name, version,
  entry point, ports, capabilities, and update URL. The backend
  discovers plugins by reading these files — no executable
  scanning, no guessing.
- **A plugin update checker is in place.** Every plugin with an
  `update_url` can be checked for newer versions via
  `GET /api/v1/plugins/updates`. Available updates are logged at
  startup.
- **Plugins can be enabled and disabled at runtime** via the API
  (`POST /api/v1/plugins/{name}/enable` and
  `POST /api/v1/plugins/{name}/disable`).
- **A read-only plugin discovery endpoint** (`GET /api/v1/plugins/discover`)
  scans `plugin.json` files on disk and merges registry state — no
  side effects, no plugin loading.

---

## What We Are Working On Now

The focus is on completing the remaining pieces before the 1.0.0
release. The core engine and plugin system are done. What is left
is mostly integration and safety.

## Plugin Lifecycle

A plugin passes through four distinct stages:

1. **Discovered** — The `GET /api/v1/plugins/discover` endpoint finds
   the plugin's `plugin.json` on disk. The discovery endpoint is
   **read-only** — it never registers or modifies state.
2. **Registered** — The launcher (or a manual API call) submits the
   plugin to `POST /api/v1/plugins/register`. The plugin now appears
   in `GET /api/v1/plugins` and the registry is the **source of truth**
   for execution state.
3. **Enabled** — The plugin's `enabled` flag is `true`
   (via `POST /api/v1/plugins/{name}/enable`). Only enabled plugins
   are started by the launcher.
4. **Disabled** — The plugin's `enabled` flag is `false`
   (via `POST /api/v1/plugins/{name}/disable`). Disabled plugins
   remain registered but are not started.

**What this means in practice:**
- Discovery shows what is *installable*. The registry shows what is
  *configured*.
- Enable/disable toggle execution without losing configuration.
- The discovery endpoint is safe to call at any time — zero side
  effects.

---

## What We Are Working On Now

The focus is on completing the remaining pieces before the 1.0.0
release. The core engine, plugin system, and API surface are done.
What is left is testing, safety, and documentation.

**Current priorities:**

- **Tool update check** — `GET /api/v1/updates/check` endpoint to
  check the main repository for new releases.
- **Update path testing** — The new API-based update signalling is
  implemented; the next step is to test the full update flow
  end-to-end (v1.0.0 → v1.0.1).
- **RCON default password warning** is already logged at startup
  (`docs/TODO.md`: ✅). API authentication is deferred to post-
  v1.0.0 since the API binds to localhost by default.
- **Documentation overhaul** — README, GUIDE, and CHANGELOG need to
  reflect the v1.0.0 architecture.

---

## What Comes Next

Once the items above are done, the focus shifts to making the
system easier to use for non-technical people.

**Upcoming milestones:**

1. **Desktop application** — A proper graphical interface so you
   do not have to edit YAML configuration files by hand. First-run
   wizard, configuration forms, trigger editor, live dashboard.
2. **Plugin manager** — See which plugins are installed, turn them
   on or off, check their status — all from the desktop app.
3. **Live log viewer** — See what the system is doing in real time
   without checking log files.
4. **Overhauled documentation** — New guides written for 1.0.0
   that reflect how the system actually works today.
5. **End-to-end testing** — Simulated TikTok events flowing all
   the way through to Minecraft commands, verified automatically.

---

## Future Vision

Long term, TikTok2Mc aims to be a set-and-forget bridge between
TikTok Live and Minecraft. The ideal flow:

1. Install the desktop app
2. Enter your TikTok username and RCON details
3. Write a few triggers (or use the built-in editor)
4. Go live — everything else runs automatically

There are no plans to support Twitch, YouTube, or other platforms
at this point. The project stays focused on TikTok. There will
also not be a mobile app or cloud component — everything runs
locally on your machine.

> **One more thing:** version 1.0.0 is a clean break. Config files,
> plugins, and data from versions 0.x are not compatible. Think of
> it as a fresh start with a much more solid foundation.

---

*Last updated: 2026-05-28* (plugin lifecycle, updated test count, discovery/enable/disable endpoints)
