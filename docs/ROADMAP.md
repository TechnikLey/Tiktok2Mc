# TikTok2Mc — Project Roadmap

## What Is This?

TikTok2Mc connects your TikTok Live stream to Minecraft. When viewers follow, like, share, or send gifts, those events can trigger commands inside your Minecraft server. You decide what happens and when.

## What Works Today

The system is fully functional and ready for daily use.

**Live connection** — TikTok events (follows, likes, shares, gifts, comments, joins) arrive reliably during a stream.

**Minecraft command execution** — Events trigger actions in your Minecraft server through RCON or datapacks. You define the commands in `data/actions.mca`.

**Seven built-in plugins** — Each one adds a specific feature and can be turned on or off independently:
- **Timer** — Countdown with pause-on-death and auto-win
- **Death Counter** — Real-time death tracker overlay
- **Win Counter** — Wins and losses with optional death penalty
- **Like Goal** — Progress bar that fills from TikTok likes
- **Overlay Text** — Scrolling or static text displayed on stream
- **Channel Points** — Loyalty points viewers earn while watching
- **Spotify Control** — Control Spotify playback through chat commands

**Desktop application** — A graphical interface opens in your browser when you start the tool. It includes:
- A setup wizard for first-time configuration
- A settings editor where you can adjust every option through forms
- A plugin manager to turn features on and off
- A restart and shutdown button

**Configuration is backed up automatically** — Every time you save your settings, the previous version is preserved. Nothing is lost if something goes wrong.

**Automatic updates** — The tool checks for new versions and can update itself. All your settings are preserved during an update.

**Over 365 automated checks** run on every change to catch problems early.

---

## What We Are Working On Now

The engine is built. Plugins work. The desktop app works. What is left is polishing the last rough edges before the 1.0.0 release.

**Current priorities:**

- **Log viewer** — A live feed inside the desktop app so you can see what the system is doing in real time, without opening log files or the console window.

- **Actions editor** — A built-in editor for trigger rules so you can create and change Minecraft commands without editing files by hand.

- **Update testing** — Verifying that the update system works correctly with compiled releases, so you can be sure updates install safely.

- **Documentation improvements** — Making sure the guides match the current version of the tool.

---

## The v1.0.0 Vision

Version 1.0.0 represents a stable, complete foundation. Everything works end to end: TikTok connects to Minecraft, plugins add features, the desktop app lets you control everything, and updates keep you current without manual work.

This version is a clean break from older 0.x releases. Your configuration files and plugins from earlier versions will need to be set up again. Think of this as starting fresh with a much more solid base.

---

## What Comes After 1.0.0

Once the 1.0.0 release is out, focus will shift to convenience and deeper features:

- **Plugin improvements** — Better tools for managing plugin settings
- **Real-time dashboard** — Live status updates without refreshing the page
- **Overlay preview** — See what your stream overlays look like before going live
- **Minecraft console in the app** — Send commands to your server directly from the desktop interface
- **API access** — For advanced users who want to build their own tools on top of TikTok2Mc

There are no current plans to support Twitch, YouTube, or other platforms. The project stays focused on TikTok.

---

## In Summary

| Area | Status |
|------|--------|
| TikTok Live connection | Working |
| Minecraft command execution | Working |
| Plugins (Timer, Death/Win Counter, Like Goal, Overlay, Channel Points, Spotify) | Working |
| Desktop app (wizard, settings, plugin manager) | Working |
| Config editor with backup | Working |
| Update system | Working (needs final testing) |
| Log viewer | In development |
| Actions editor | In development |
| Guides and documentation | Being updated |

---

*Last updated: 2026-05-29*
