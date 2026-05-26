# TikTok to Minecraft Integration

> [!IMPORTANT]
> # v1.0.0 — Coming Soon
>
> A major rewrite is in active development. v1.0.0 will ship:
>
> - **Graphical User Interface** — manage everything through a GUI. 
>   No more editing YAML, actions files, or configs by hand.
> - **Plugin overhaul** — each plugin becomes a true standalone module.
>   Enable only what you need (opt-in). Timer, Death Counter, and Win
>   Counter are no longer hardwired together.
> - **Unified API server** — one central backend instead of a dozen
>   separate executables. Drastically fewer ports and better stability.
> - **Quality of Life** — first-run setup wizard, live log viewer,
>   overlay previews, theme editor with color pickers, Spotify setup
>   assistant, and integrated trigger testing.
>
> **⚠️ Breaking Change:** v1.0.0 will **not** be compatible with v0.x
> configurations, plugins, or workflows. This is intentional — the v0.x
> line was an experimental phase, and v1.0.0 is the first stable release
> built on a clean foundation.
>
> If you are a new user, start with the latest **v0.5.0**.
> Existing users can continue using v0.5.0 — it remains
> stable and supported for day-to-day streaming.
>
> **Release date:** Unknown. Quality over speed.
> See [`docs/ROADMAP.md`](./docs/ROADMAP.md) for current progress.

Connect your TikTok Live stream to a Minecraft server. Gifts, follows, and likes from your viewers trigger real-time commands in the game.

The tool includes a ready-to-use Minecraft server (1.21.11). On Windows, Java is automatically downloaded and set up if not already present, no manual installation required. On Linux, the tool will locate or install Java automatically.

## Features

- Real-time connection to TikTok Live via [TikTokLive](https://github.com/isaackogan/TikTokLive)
- Trigger Minecraft commands through gifts, follows, and like milestones
- Customizable action mappings with support for chaining, repeating, and randomizing commands
- Built-in overlay plugins for OBS (Death Counter, Win Counter, Like Goal, Timer, Text Overlay)
- Configurable like triggers with custom thresholds
- Support for vanilla commands, server plugin commands, and special actions
- Auto-updater for easy version management

## Requirements

- **OS:** Windows or Linux
- **RAM:** 12 GB minimum recommended (the Minecraft server uses up to 4 GB by default, adjustable)

## Quick Start

1. Open the file `config/config.yaml` in a text editor (for example Notepad).
2. Find the line `User: your_tiktok_username` and replace `your_tiktok_username` with your actual TikTok username.
3. Find `Password: ABC1234` and change it to any password you like. This is the password for the connection between the tool and the Minecraft server.
4. Save the file.
5. Open `data/actions.mca` and set up your actions. This file defines what happens in Minecraft when viewers send gifts, follow, or hit like milestones. There are already some example actions included, but you should adjust them to your liking. See the [User Guide](./docs/GUIDE.md#setting-up-actions) for a full explanation.
6. Run `start.exe` (Windows) or `sudo ./start.bin` (Linux) to launch everything.

That's it. The tool will start the Minecraft server, connect to your TikTok Live, and begin listening for events.

> [!IMPORTANT]
> You must be live on TikTok for the connection to work. The tool will keep trying to reconnect until your stream is live.

For a detailed walkthrough of all settings, action syntax, overlays, and troubleshooting, see the **[User Guide](./docs/GUIDE.md)**.

For a list of all changes between versions, see the **[Changelog](./docs/CHANGELOG.md)**.

## Developer Documentation

The developer documentation is best viewed online:

- **[English-Dev-Documentation](https://technikley.github.io/Tiktok2Mc/en)**
- **[Deutsche-Dev-Dokumentation](https://technikley.github.io/Tiktok2Mc/de)**

> [!TIP]
> The online docs are better organized and easier to navigate. You can also browse the Markdown files directly in the repository if you prefer:
> - [English-Dev-Documentation](./docs/dev-book-en/src/Introduction.md)
> - [Deutsche-Dev-Dokumentation](./docs/dev-book-de/src/Introduction.md)

> [!WARNING]
> The developer documentation may not always be fully up to date.

## License

This project is licensed under the **PolyForm Noncommercial License 1.0.0** with a special exception for TikTok content creators.

**Allowed:**
- Use during TikTok Lives, including earning money through Gifts, Diamonds, and the Creator Program.
- Personal and educational use.
- Modifying the code, provided changes are shared under the same license.

**Not allowed:**
- Commercial use on other platforms (Twitch, YouTube, Kick) without permission.
- Selling the software or any modified version of it.

**Attribution:** When sharing or redistributing, include this notice:

`Required Notice: Copyright (c) 2026 TechnikLey - https://github.com/TechnikLey/Tiktok2Mc.git`

For the full legal text, see the [LICENSE](LICENSE) file.

## Contact

- **GitHub:** [Open an Issue](https://github.com/TechnikLey/Tiktok2Mc/issues) or start a discussion.
- **Profile:** [TechnikLey on GitHub](https://github.com/TechnikLey)
