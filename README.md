# TikTok2Mc

Connect your TikTok Live stream to a Minecraft server. When viewers send gifts, follow you, or hit like milestones, things happen in your Minecraft world automatically.

## What it can do

- **Gift reactions** — Viewers send a gift, a Creeper spawns. You decide what happens for each gift.
- **Follow alerts** — New followers trigger commands, overlay messages, or special effects.
- **Like milestones** — Every 100 likes (or whatever you set), run a command. Celebrate big milestones.
- **Chat commands** — Let viewers type commands in chat to control the game or your Spotify playback.
- **Stream overlays** — Show death counts, win counters, timers, and Spotify info on your stream.
- **Auto-updates** — The tool checks for updates on startup and installs them automatically.
- **Web Dashboard** — A browser interface at `http://127.0.0.1:29185` for managing actions, configuration, plugins, server instances, and event reactions visually. No file editing required.

Everything is controlled either through the Dashboard or via simple text files. No programming required.

## What you need

| Requirement | Details |
|-------------|---------|
| **Computer** | Windows 10+ or Linux |
| **RAM** | 12 GB recommended (the Minecraft server uses up to 4 GB) |
| **TikTok** | You need to be live on TikTok for the connection to work |
| **Minecraft** | Java Edition (the tool includes a server, but you can use your own) |

## Installation

### Windows

**Option A — Installer (Recommended)**

1. Download `TikTok2MC-<version>-Windows-Setup.exe` from [GitHub Releases](https://github.com/TechnikLey/Tiktok2Mc/releases).
2. Run the installer and follow the prompts.
3. TikTok2Mc will be installed to `Program Files` and can be launched from the desktop or Start Menu shortcut.

**Option B — Portable ZIP**

1. Download `TikTok2Mc-<version>-Windows.zip` from [GitHub Releases](https://github.com/TechnikLey/Tiktok2Mc/releases).
2. Extract the ZIP file to any folder.
3. That is it. The tool includes everything it needs, including Java.

> The ZIP also contains the `TikTok2MC-Setup.exe` installer if you later decide to install it properly instead of running it portably.

### Linux

**Option A — Shell Installer (Recommended)**

1. Download `TikTok2Mc-<version>-Linux-Setup.sh` from [GitHub Releases](https://github.com/TechnikLey/Tiktok2Mc/releases).
2. Make it executable and run as root:
   ```bash
   chmod +x TikTok2Mc-<version>-Linux-Setup.sh
   sudo ./TikTok2Mc-<version>-Linux-Setup.sh
   ```
3. TikTok2Mc will be installed to `/opt/TikTok2Mc` with a desktop entry and a `tiktok2mc` terminal command.

**Option B — Portable Archive**

1. Download `TikTok2Mc-<version>-Linux.tar.gz` from [GitHub Releases](https://github.com/TechnikLey/Tiktok2Mc/releases).
2. Extract the archive to any folder.
3. Java will be detected automatically, or the tool will help you install it.

> The archive also contains the `TikTok2Mc-Linux-Setup.sh` installer if you later decide to install it properly.

## Quick Start

**Step 1 — Set your TikTok username**

Open `config/config.yaml` in any text editor.

Find this line:

```yaml
tiktok:
  user: your_tiktok_username
```

Change `your_tiktok_username` to your actual TikTok username **without the @ symbol**.

**Step 2 — Change the RCON password**

In the same file, find:

```yaml
rcon:
  password: ABC1234
```

Change `ABC1234` to any password you want. This password connects the tool to your Minecraft server. You will see a warning at startup if you leave it as the default.

**Step 3 — Decide which features you want**

Still in `config/config.yaml`, each plugin has an `enabled:` setting. By default, everything is turned **off**. Change `enabled: false` to `enabled: true` for the features you want:

| Plugin | What it does | OBS Browser Source URL |
|--------|-------------|------------------------|
| Timer | Countdown timer for your stream | `http://localhost:29189` |
| Death Counter | Shows how many times the player has died | `http://localhost:29190` |
| Win Counter | Tracks wins and losses | `http://localhost:29191` |
| Overlay Text | Text notifications on stream | `http://localhost:29186/?overlay=default` |
| Spotify Control | Let viewers control your Spotify | `http://localhost:29194` |

Every setting has a comment above it explaining what it does. Read the comments carefully.

**Step 4 — Set up your actions**

Open `data/actions.mca`. This file decides what happens in Minecraft when TikTok events occur. Example actions are already included. Adjust them to your liking.

A simple action looks like this:

```
follow:/say Thanks for the follow!
5655:/give @a minecraft:diamond
```

The first part (`follow`, `5655`) is the trigger. The second part is the Minecraft command.

See the [User Guide](./docs/GUIDE.md) for more examples and the full action syntax.

**Step 5 — Start the tool**

- **Windows:** Double-click `start.exe`
- **Linux:** Open a terminal, run `sudo ./start.bin`

The tool will start the Minecraft server, connect to your TikTok Live stream, and begin listening for events.

**Step 6 — Join the Minecraft server**

Open Minecraft Java Edition, go to **Multiplayer > Add Server**, and enter `localhost:25565`.

> You must be live on TikTok for the connection to work. The tool will keep trying to reconnect automatically.

## Important files

| File | What it is |
|------|-----------|
| `config/config.yaml` | Main settings file. This is where you turn features on and off. |
| `data/actions.mca` | Your action rules. What happens when someone follows, sends a gift, etc. |
| `docs/GUIDE.md` | Complete user guide with examples, troubleshooting, and plugin setup. |
| `http://127.0.0.1:29185` | Web Dashboard — visual editor for actions, config, plugins, and server management. |
| `docs/CHANGELOG.md` | Release history — what changed in each version. |

## Getting help

- Read the [User Guide](./docs/GUIDE.md) for detailed setup instructions, plugin configuration, and troubleshooting.
- Open a [GitHub Issue](https://github.com/TechnikLey/Tiktok2Mc/issues) if something is not working.

## License

This project is licensed under the **PolyForm Noncommercial License 1.0.0** with a special exception for TikTok content creators.

**Allowed:**
- Use during TikTok Lives, including earning money through Gifts, Diamonds, and the Creator Program
- Personal and educational use
- Modifying the code, provided changes are shared under the same license

**Not allowed:**
- Commercial use on other platforms (Twitch, YouTube, Kick) without permission
- Selling the software or any modified version of it

For the full legal text, see the [LICENSE](LICENSE) file.