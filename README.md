# TikTok2Mc

Connect your TikTok Live stream to a Minecraft server. When viewers send gifts, follow you, or hit like milestones, things happen in your Minecraft world automatically. Configure everything through the Web Dashboard or via simple text files — **for basic use no programming is required**.

## Features

- **Gift reactions** — every gift triggers Minecraft commands: spawn mobs, give items, run effects, show overlays
- **Follow, share & join actions** — react to viewers following, sharing, or joining your stream
- **Like milestones** — trigger commands at like thresholds (every 100, 100k likes by default)
- **Chat commands** — viewers type commands like `#give` or `$skip` in TikTok chat
- **Stream overlays** — OBS browser-source overlays for timers, counters, and text alerts
- **Web Dashboard** — manage actions, configuration, plugins, and your server at `http://127.0.0.1:29185`
- **Plugin & hook system** — extend TikTok2Mc with Python plugins and hooks
- **Auto-updates** — checks for new versions and installs them automatically

## Requirements

| Component | Requirement |
|-----------|-------------|
| **OS** | Windows 10+ or Linux |
| **RAM** | 4 GB minimum, 8 GB recommended (Minecraft server: up to 4 GB, adjustable) |
| **Free space** | ~1 GB for the tool, ~500 MB per additional Minecraft version |
| **TikTok** | An active TikTok account — the live connection requires you to be streaming |
| **Minecraft** | Java Edition (the tool bundles a PaperMC server, or use your own) |

## Installation

**Windows** — Download `TikTok2MC-<version>-Windows-Setup.exe` from [Releases](https://github.com/TechnikLey/Tiktok2Mc/releases) and run the installer. A portable ZIP is also available — extract anywhere and run.
The installer is recommended, as it lets you configure the tool and create a desktop shortcut.

**Linux** — Download `TikTok2Mc-<version>-Linux-Setup.sh`, make it executable (`chmod +x`), and run it. The installer itself needs no `sudo` — it installs to `~/.local/share/TikTok2Mc` with a desktop entry and a `tiktok2mc` terminal command. A portable `.tar.gz` archive is also available.

> [!NOTE]
> Running the tool on Linux requires root privileges (`sudo ./start.bin`) — otherwise it exits with an error. Launched via the desktop entry it runs but shows a warning and some features may fail (depends on your desktop environment: some assign a TTY, some don't). Set `show_sudo_warning: false` in `config.yaml` to skip the check. If `~/.local/bin` is not on your `PATH`, the installer will show you how to add it.

### Installation for advanced users
You can also clone the repository and build the tool yourself. Keep in mind that a few dependencies must be installed on your system before it can be built — see the [developer documentation](./docs/dev-book-en/src/ch01-00-getting-started.md).
Please note that building is very slow and resource-heavy: on low-end systems it can take a long time. Make sure you have enough free space, RAM, and CPU power available.

## Quick Start

1. **Launch** — Run `start.exe` (Windows) or `sudo ./start.bin` (Linux). The Dashboard opens at `http://127.0.0.1:29185`.
2. **Set up** — On first launch a setup wizard guides you through the required settings: enter your TikTok username (without `@`) and set a secure RCON password. Everything else is managed from the Dashboard.
3. **Enable features** — Turn on what you need from the Dashboard (Plugins, Comment Commands, etc.).
4. **Define actions** — Use the Actions page in the Dashboard, or edit `data/actions.mca` directly. Each line is `trigger:command`. Example: `follow:/give @a minecraft:diamond`.
5. **Connect** — Open Minecraft Java Edition → Multiplayer → Add Server → `localhost:25565`.

> You must be live on TikTok to receive live events; the tool can also be used with manual triggers. The Dashboard is at `http://127.0.0.1:29185` — most settings can also be edited by hand in `config/config.yaml` and `data/actions.mca`.

## Overlay URLs (OBS Browser Source)

All overlays are served through the central API at `http://127.0.0.1:29185`:

| Overlay | URL |
|---------|-----|
| Text overlay (default) | `http://127.0.0.1:29185/api/v1/overlay?overlay=default` |
| Text overlay (chroma key) | `http://127.0.0.1:29185/api/v1/overlay?overlay=default&chroma=true` |
| Timer | `http://127.0.0.1:29185/api/v1/plugins/timer/overlay` |
| Death Counter | `http://127.0.0.1:29185/api/v1/plugins/death-counter/overlay` |
| Win Counter | `http://127.0.0.1:29185/api/v1/plugins/win-counter/overlay` |
| Spotify Control | `http://127.0.0.1:29185/api/v1/plugins/spotify-control/overlay` |

**Real-time updates (SSE streams)** — for browser sources that need live updates without refresh:
- Core overlay: `http://127.0.0.1:29185/api/v1/overlay/stream`
- Plugin overlays: `http://127.0.0.1:29185/api/v1/plugins/{name}/stream`

## Getting help

- **User Guide** — [`docs/GUIDE.md`](./docs/GUIDE.md) covers installation, configuration, actions, comment commands, plugins, overlays, server management, and FAQ in detail.
- **Issues** — Open a [GitHub Issue](https://github.com/TechnikLey/Tiktok2Mc/issues) for bugs or feature requests.

## Developer Documentation

The developer documentation is best viewed online:

- **[English Dev Documentation](https://technikley.github.io/Tiktok2Mc/en)**
- **[Deutsche Entwickler-Dokumentation](https://technikley.github.io/Tiktok2Mc/de)**

> [!TIP]
> The online docs are better organized and easier to navigate. You can also browse the Markdown files directly in the repository if you prefer:
> - [English Dev Documentation](./docs/dev-book-en/src/Introduction.md)
> - [Deutsche Entwickler-Dokumentation](./docs/dev-book-de/src/Introduction.md)

> [!WARNING]
> The developer documentation may not always be fully up to date.

## License

PolyForm Noncommercial License 1.0.0 with a special exception for TikTok content creators.

**Allowed:** Use during TikTok Lives (including monetized streams), personal and educational use, modifying the code.
**Not allowed:** Commercial use on other platforms (Twitch, YouTube, Kick) without permission, selling the software.

See [LICENSE](LICENSE) for the full legal text.