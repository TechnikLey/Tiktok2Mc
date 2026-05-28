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
  thoroughly. 155 automated checks run on every change to catch
  regressions early.
- Trigger files (.mca) are validated when loaded. Mistakes like
  missing brackets or wrong command prefixes are caught before
  they reach Minecraft.
- Your configuration is backed up automatically. If something goes
  wrong during a save, the last good version is still there.
- The system warns you if you try to expose it to the internet
  accidentally (`0.0.0.0` is not the default).

---

## What We Are Working On Now

The focus is on completing the remaining pieces before the 1.0.0
release. The core engine is done. What is left is mostly
integration and safety.

**Current priorities:**

- **Update system** — The auto-updater still uses a temporary file
  to signal that an update is ready. We are replacing that with a
  proper API-based approach so the status is visible and reliable.
- **Security** — Adding an optional API key for users who need to
  access the backend from other devices. Also making the RCON
  default password warning more visible so nobody accidentally
  leaves `ABC1234` in place.
- **Fewer ports** — Right now, each plugin runs on its own port.
  That adds up (Minecraft, RCON, API, plugins — over 10 ports).
  We are routing plugin communication through the central backend
  to reduce this to just a handful.
- **Plugin metadata** — Adding a small manifest file inside each
  plugin folder so the backend knows what is available without
  having to launch every plugin first.

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

*Last updated: 2026-05-28*