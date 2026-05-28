# TikTok2Mc — Project Roadmap

## Project Overview

TikTok2Mc connects your TikTok Live stream to a Minecraft server. When viewers send gifts, follow, or hit like milestones, things happen in your game — automatically.

Think of it as a bridge: TikTok events come in on one side, Minecraft commands go out on the other. Everything in between is handled by the tool. You just set up what you want to happen and go live.

The project has been around for a while, but version 1.0.0 is a complete rebuild from the ground up. It is more reliable, better organised, and much easier to maintain going forward.

---

## Current Progress

The core system works end to end. Here is what is stable right now:

- **TikTok Live connection** — follows, likes, shares, gifts, and other events come through reliably.
- **Minecraft commands** — when an event triggers an action, the command reaches your server as expected.
- **Plugins work independently** — Timer, Death Counter, Win Counter, Overlay, and more. Each one runs on its own. Turning on the Timer will not accidentally trigger the Death Counter anymore.
- **Everything starts disabled** — nothing runs unless you turn it on. You are in control.
- **Your config is backed up automatically** — if something goes wrong during a save, the last good version is still there.
- **The system warns you about risky settings** — exposing services to your whole network or leaving the default RCON password in place triggers a clear warning.
- **Over 270 automated checks** run on every change to catch problems early.

> **A quick note about version 1.0.0:**  
> This version is a clean break. Config files, plugins, and data from versions 0.x are not compatible. Think of it as a fresh start with a much more solid foundation.

---

## What We Are Working On Now

The engine is built. The plugins work. The backend is stable. What is left is wrapping things up for the 1.0.0 release.

**Current focus areas:**

- **An automatic update check** — so the tool can tell you when a new version is available, without you having to check manually.
- **End-to-end update testing** — the update system works on paper; now we are running it through a real version upgrade to make sure nothing breaks.
- **Documentation overhaul** — the existing guides still describe the old system. They need to be rewritten to match how things actually work today.

---

## What Comes Next

Once 1.0.0 is out, the focus shifts to making the tool easier to use for everyone.

**Planned milestones:**

1. **Desktop application** — a proper graphical interface so you do not have to edit configuration files by hand. First-run wizard, configuration forms, and a live dashboard.
2. **Plugin manager** — see which plugins are installed, turn them on or off, check their status — all from the desktop app.
3. **Live log viewer** — see what the system is doing in real time without opening log files.
4. **New guides and documentation** — rewritten from scratch for version 1.0.0.

---

## Future Vision

Long term, TikTok2Mc aims to be a set-and-forget bridge between TikTok Live and Minecraft. The ideal flow:

1. Install the desktop app
2. Enter your TikTok username and RCON details
3. Write a few trigger rules (or use the built-in editor)
4. Go live — everything else runs automatically

There are no plans to support Twitch, YouTube, or other platforms. The project stays focused on TikTok. There will also not be a mobile app or cloud component — everything runs locally on your machine.

---

## Fun Facts

- The project runs **over 270 automated tests** on every change. That is more than one test for every plugin, every configuration option, and every trigger rule — combined.
- Each plugin now ships with its own manifest file that describes what it does, what version it is, and how to update it. No more guesswork.
- The entire backend was rebuilt from scratch for version 1.0.0. The old system relied on files and hard-wired connections between components. That is all gone.
- Despite the rebuild, the core loop is surprisingly simple: TikTok event arrives → a trigger rule matches → a Minecraft command runs. Everything else is there to make that loop reliable and manageable.

---

*Last updated: 2026-05-28*
