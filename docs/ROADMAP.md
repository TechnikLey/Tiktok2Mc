# Roadmap

## Current Status

**v1.0.0 released (2026-08-15).** The desktop GUI, plugin system, event reactions, installers for Windows and Linux, and auto-updates are all shipped. Remaining work is ongoing polish and UX improvements.

## Available Now

* **TikTok → Minecraft bridge** — gifts, follows, likes, shares, comments, and joins can trigger in-game events
* **Desktop GUI** — manage everything from a visual dashboard: config editor, actions editor, plugin manager, setup wizard
* **Event Reactions** — a visual editor that lets you decide what happens when events occur (no files to edit)
* **Live Dashboard** — see plugin health, recent activity, and system status in real time
* **Stream overlays** — timer, death counter, win counter, Spotify info, and text overlays for OBS
* **Overlay preview & live theme editor** — see how overlays look before going live, tweak colors in real time
* **Chat commands** — viewers can trigger actions by typing in chat, with role-based permissions and cooldowns
* **Spotify integration** — connect your Spotify account, let viewers control playback, show album art on stream
* **Minecraft server console** — view live server output and send commands directly from the GUI
* **Installers** — one-click setup for Windows (NSIS) and Linux (shell installer with desktop entry)
* **Auto-updates** — the tool checks for updates on startup and installs them automatically
* **GUI integration tests** — automated tests for the dashboard and editors (`templates/gui/tests/`)
* **Accessibility (WCAG AA)** — keyboard navigation, modal focus management, screen-reader labels (`docs/GUI_UX_TODO.md` P1 #2)
* **Mobile / LAN UX** — responsive drawer sidebar and dashboard polish on smaller screens (`docs/GUI_UX_TODO.md` P2 #8)
* **Windows + Linux support** — runs on both platforms with native installers

## In Progress

* **Documentation refresh** — keeping the user guide and developer docs in sync with the v1.0.0 GUI

## Long-Term Ideas

* Mobile-friendly web dashboard for managing the tool from a phone or tablet
* Plugin ecosystem — making it easier for the community to create and share plugins
