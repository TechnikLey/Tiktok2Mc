# TikTok2Mc

Connect your TikTok Live stream to a Minecraft server. When viewers send gifts, follow you, or hit like milestones, things happen in your Minecraft world automatically. Configure everything through the Web Dashboard or via simple text files — no programming required.

## Features

| Category | Description |
|----------|-------------|
| **Gift reactions** | Each gift ID (e.g. `5655`, `16111`) triggers a Minecraft command — spawn mobs, give items, run effects, show overlays |
| **Follow / share / join** | Run actions when viewers follow, share, or join your stream |
| **Like milestones** | Configure thresholds (every 100, 1000, 100k likes) to trigger commands |
| **Chat commands** | Viewers type `#give`, `$skip`, etc. in TikTok chat to control Minecraft or Spotify |
| **Stream overlays** | Browser-source overlays for countdown timers, death counters, win counters, and text alerts |
| **Web Dashboard** | Full GUI at `http://127.0.0.1:29185` — manage actions, config, plugins, and server |
| **Auto-updates** | Checks for new versions on startup and installs automatically |
| **Plugin system** | Extend with Python plugins (Timer, Death Counter, Win Counter, Spotify, etc.) |
| **Hooks** | Custom Python scripts that run on specific events |
| **Setup wizard** | Guides you through the minimal configuration on first launch |
| **Comment commands** | Configurable command groups with role-based access, cooldowns, and allow/deny lists |
| **Event mapper** | React to in-game events (player death, join, etc.) with configurable commands |
| **Server manager** | Start, stop, and manage your Minecraft server from the Dashboard |
| **Auto-shutdown** | Automatically shuts down when your live stream ends |
| **Port conflict resolution** | Automatically finds free ports when the default ones are in use |

## Requirements

| Component | Requirement |
|-----------|-------------|
| **OS** | Windows 10+ or Linux |
| **RAM** | 8 GB minimum, 12 GB recommended (Minecraft server uses up to 4 GB) |
| **Free space** | ~1 GB for the tool, ~500 MB per additional Minecraft version |
| **TikTok** | You must be live on TikTok for the connection to work |
| **Minecraft** | Java Edition (the tool bundles a PaperMC server, or use your own) |

## Installation

**Windows** — Download `TikTok2MC-<version>-Windows-Setup.exe` from [Releases](https://github.com/TechnikLey/Tiktok2Mc/releases) and run the installer. A portable ZIP is also available — extract anywhere and run.

**Linux** — Download `TikTok2Mc-<version>-Linux-Setup.sh`, make it executable (`chmod +x`), and run it. The installer itself needs no `sudo` — it installs to `~/.local/share/TikTok2Mc` with a desktop entry and a `tiktok2mc` terminal command. A portable `.tar.gz` archive is also available.

> Running the tool on Linux requires root privileges (`sudo ./start.bin`) — otherwise it exits with an error. Launched via the desktop entry it runs but shows a warning and some features may fail. Set `show_sudo_warning: false` in `config.yaml` to skip the check.

> The portable archives include everything needed (including Java). No separate installation required.

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

## Actions syntax (`.mca`)

```
follow:/give @a minecraft:golden_apple 7
5655:/execute at @a run summon minecraft:creeper ~ ~ ~
likes:/give @a minecraft:diamond x3
comment:>>{user} wrote:|{comment}
share:!tnt 5 0.5 2
```

Command prefixes: `/` = Minecraft command, `!` = server plugin command, `>>` = overlay text, `$` = special action, `&` = shell command.

Chain multiple commands with `;`, repeat with `xN`, use `{user}` / `{comment}` placeholders.

## Important files

| File / URL | Purpose |
|------------|---------|
| `config/config.yaml` | Main settings — TikTok user, RCON, features, ports, Java RAM |
| `data/actions.mca` | Action rules — trigger → command mappings |
| `docs/GUIDE.md` | Complete user guide with examples, plugins, overlays, troubleshooting |
| `docs/CHANGELOG.md` | Release history and breaking changes |
| `http://127.0.0.1:29185` | Web Dashboard — visual editor for everything |

## Getting help

- **User Guide** — [`docs/GUIDE.md`](./docs/GUIDE.md) covers installation, configuration, actions, comment commands, plugins, overlays, server management, and FAQ in detail.
- **Issues** — Open a [GitHub Issue](https://github.com/TechnikLey/Tiktok2Mc/issues) for bugs or feature requests.

## License

PolyForm Noncommercial License 1.0.0 with a special exception for TikTok content creators.

**Allowed:** Use during TikTok Lives (including monetized streams), personal and educational use, modifying the code.
**Not allowed:** Commercial use on other platforms (Twitch, YouTube, Kick) without permission, selling the software.

See [LICENSE](LICENSE) for the full legal text.