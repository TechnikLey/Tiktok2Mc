# TikTok2Mc

Connect your TikTok Live stream to a Minecraft server. When viewers send gifts, follow you, or hit like milestones, things happen in your Minecraft world automatically. Configure everything through the Web Dashboard or via simple text files — no programming required.

## Features

TODO: Add a small list of features no big Table, just a few important bullet points.

## Requirements

| Component | Requirement |
|-----------|-------------|
| **OS** | Windows 10+ or Linux |
| **RAM** | 4 GB minimum, 8 GB recommended (Minecraft server uses up to 4 GB adjustable) |
| **Free space** | ~1 GB for the tool, ~500 MB per additional Minecraft version |
| **TikTok** | You must be live on TikTok for the connection to work |
| **Minecraft** | Java Edition (the tool bundles a PaperMC server, or use your own) |

## Installation

**Windows** — Download `TikTok2MC-<version>-Windows-Setup.exe` from [Releases](https://github.com/TechnikLey/Tiktok2Mc/releases) and run the installer. A portable ZIP is also available — extract anywhere and run.
The installer is recommended as it lets configure the tool and create a desktop shortcut.

**Linux** — Download `TikTok2Mc-<version>-Linux-Setup.sh`, make it executable (`chmod +x`), and run it. The installer itself needs no `sudo` — it installs to `~/.local/share/TikTok2Mc` with a desktop entry and a `tiktok2mc` terminal command. A portable `.tar.gz` archive is also available.

> [!NOTE]
> Running the tool on Linux requires root privileges (`sudo ./start.bin`) — otherwise it exits with an error. Launched via the desktop entry it runs but shows a warning and some features may fail. Set `show_sudo_warning: false` in `config.yaml` to skip the check.

### Installation for advanced users
You can also clone the repository and build the tool yourself.
Keep in mind that the tool requires a few dependencies to be installed on your system before it can be built. See [Dev documentation](./docs/dev-book-en/src/ch01-00-getting-started.md).
Please note that the build process is very slow and heavy on resources so on
Low-end systems it may take a long time to build the tool. If you want to build the tool yourself, make sure you have enough free space, RAM and CPU Power available.

## Quick Start

1. **Launch** — Run `start.exe` (Windows) or `sudo ./start.bin` (Linux). The Dashboard opens at `http://127.0.0.1:29185`.
2. **Set up** — On first launch a setup wizard guides you through the required settings: enter your TikTok username (without `@`) and set a secure RCON password. Everything else is managed from the Dashboard.
3. **Enable features** — Turn on what you need from the Dashboard (Plugins, Comment Commands, etc.).
4. **Define actions** — Use the Actions page in the Dashboard, or edit `data/actions.mca` directly. Each line is `trigger:command`. Example: `follow:/give @a minecraft:diamond`.
5. **Connect** — Open Minecraft Java Edition → Multiplayer → Add Server → `localhost:25565`.

> You must be live on TikTok for the tool to connect. The Dashboard is at `http://127.0.0.1:29185` — most settings can also be edited by hand in `config/config.yaml` and `data/actions.mca`.

## Overlay URLs (OBS Browser Source)

All overlays are served through the central API at `http://127.0.0.1:29185`:

| Overlay | URL |
|---------|-----|
| Text overlay (default) | `http://127.0.0.1:29185/api/v1/overlay?overlay=default` |
| Timer | `http://127.0.0.1:29185/api/v1/plugins/timer/overlay` |
| Death Counter | `http://127.0.0.1:29185/api/v1/plugins/death-counter/overlay` |
| Win Counter | `http://127.0.0.1:29185/api/v1/plugins/win-counter/overlay` |
| Spotify Control | `http://127.0.0.1:29185/api/v1/plugins/spotify-control/overlay` |

## Getting help

- **User Guide** — [`docs/GUIDE.md`](./docs/GUIDE.md) covers installation, configuration, actions, comment commands, plugins, overlays, server management, and FAQ in detail.
- **Issues** — Open a [GitHub Issue](https://github.com/TechnikLey/Tiktok2Mc/issues) for bugs or feature requests.

## License

PolyForm Noncommercial License 1.0.0 with a special exception for TikTok content creators.

**Allowed:** Use during TikTok Lives (including monetized streams), personal and educational use, modifying the code.
**Not allowed:** Commercial use on other platforms (Twitch, YouTube, Kick) without permission, selling the software.

See [LICENSE](LICENSE) for the full legal text.