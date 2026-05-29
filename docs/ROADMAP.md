# TikTok2Mc — Project Roadmap

## What This Is

TikTok2Mc links your TikTok Live stream to a Minecraft server. When viewers follow, like, share, comment, or send gifts, those events can trigger commands in your Minecraft world. You decide which events matter and what they do.

---

## What Works Today

All items listed here are implemented and functional in the current version.

### Live Stream Connection

TikTok events arrive reliably during a live stream. Supported event types:

- Follows
- Likes
- Shares
- Comments
- Gift sends
- Viewer joins

### Minecraft Command Execution

Events can trigger commands in your Minecraft server. Commands are defined in a file named `actions.mca` and can use different execution methods depending on your server setup.

### Built-in Add-ons

Seven optional features are included. Each one can be turned on or off independently:

- **Timer** — A visible countdown that can pause when a death happens
- **Death Counter** — Tracks and displays deaths during the stream
- **Win Counter** — Tracks wins and losses, with an optional death penalty
- **Like Goal** — A progress bar that fills as likes come in
- **Overlay Text** — Scrolling or static text shown on your stream overlay
- **Channel Points** — Loyalty points that viewers earn over time
- **Spotify Control** — Lets viewers control Spotify playback through chat commands

### Desktop Interface

When you start the tool, a dashboard opens in your browser. It includes:

- **Setup wizard** — Guides you through the initial configuration (TikTok username, server password)
- **Settings editor** — All tool options are available through forms organized by category (connection, Minecraft, system, appearance, chat commands). Changes are reviewed before saving.
- **Feature manager** — See which add-ons are installed, turn them on or off, and adjust their individual settings
- **Overlay URL display** — Shows the web addresses you need for OBS Browser Sources, with copy buttons
- **Restart and shutdown controls**

### Configuration Backups

Every time you save your settings, a backup is created automatically. If something goes wrong during a save, the previous version is preserved.

---

## Areas That Need Improvement

These are real gaps in the current version. None of them prevent the tool from functioning, but they affect the experience.

**No update notifications in the interface.** The tool checks for new versions at startup (in the console window), but the desktop interface does not show update status, check for updates, or notify you when a new version is available.

**No live log viewer.** The dashboard has a placeholder section for logs that reads "Log streaming not yet implemented." There is no way to see what the system is doing in real time without opening the console window or reading log files.

**No built-in trigger editor.** Trigger rules (the `actions.mca` file) must be edited by hand. There is no editor or validation tool in the desktop interface.

**Overlay URLs are not shown on the main dashboard.** They only appear inside the feature manager popup.

---

## What v1.0.0 Is Aiming For

The v1.0.0 release focuses on making the current foundation stable and complete. The main areas of work are:

- **Verifying the update system** works correctly with compiled releases, so updates install safely
- **Updating the guides** to match the current version of the tool
- **Resolving the known gaps** listed above where practical

This version is a clean break from older 0.x releases. Configuration files and add-ons from earlier versions are not compatible and will need to be set up again.

---

## Ideas After v1.0.0

These are possible future improvements. None are confirmed or scheduled.

- A live log viewer inside the desktop interface
- An editor for trigger rules
- Update notifications within the interface
- A preview of what stream overlays look like before going live
- A way to send Minecraft commands directly from the interface
- Better tools for managing add-on settings

---

*Last updated: 2026-05-29*
