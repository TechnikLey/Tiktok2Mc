# TikTok2Mc – User Documentation

This project connects your TikTok Live stream to a Minecraft server.  
When viewers send gifts, follow you, or hit like milestones, things happen in your Minecraft world — automatically.

## Quick Start

1. Open `config/config.yaml` and set your TikTok username (without `@`).
2. Change the RCON password to something secure.
3. Save the file and run `start.exe` (Windows) or `sudo ./start.bin` (Linux).

## Key Files

| File | Purpose |
|------|---------|
| `config/config.yaml` | All settings. Every option has a comment explaining what it does. |
| `data/actions.mca` | Defines what happens when TikTok events occur (gifts, follows, likes, etc.). |
| `docs/GUIDE.md` | Full user guide with examples, troubleshooting, and plugin setup. |
| `core/gifts.json` | TikTok gift IDs, names, and coin costs. |

## Actions and Triggers

The file `data/actions.mca` maps TikTok events to Minecraft commands.

**Format:** `Trigger:Command`

**Trigger types:** `follow`, `join`, `comment`, `share`, `likes`, `like_2`, or a gift ID (e.g. `5655`) or gift name (e.g. `Rosa`).

**Command types:**

| Prefix | Meaning | Example |
|--------|---------|---------|
| `/` | Minecraft command (RCON) | `/give @a minecraft:diamond` |
| `!` | Plugin command | `!tnt 5 0.5 2` |
| `$` | Special action (e.g. random) | `$random` |
| `>>` | Overlay text message | `>>New Follower!\|{user}\|5` |
| `&` | Shell / system command | `&curl ...` |

## Plugins

Optional features enabled in `config/config.yaml`:

- **Timer** – Countdown timer for your stream
- **Death Counter** – Tracks player deaths
- **Win Counter** – Tracks wins and losses
- **Spotify Control** – Viewers control Spotify via TikTok chat

Set `enabled: true` for any plugin you want to use.

## Comment Commands

Viewers can send commands via TikTok chat. Two default groups exist:

- **`#` prefix** (RCON) – Minecraft commands, moderator/superfan only
- **`$` prefix** – Spotify control, anyone can use

Configure them under `comment_commands` in `config.yaml`.

## Test Without Going Live

Use `send_trigger.py` (built as `test_trigger.exe` on Windows or `test_trigger.bin` on Linux) to simulate events like `follow` or a gift ID.

```bash
python src/python/send_trigger.py follow --user TestUser
python src/python/send_trigger.py gift --user TestUser --gift-id 5655
python src/python/send_trigger.py --list
```

## Overlays

Each plugin (and the core overlay) provides a web page you can add as a Browser Source in OBS. All overlays are served through the central API at `http://127.0.0.1:29185`:

- `http://127.0.0.1:29185/api/v1/plugins/timer/overlay`
- `http://127.0.0.1:29185/api/v1/plugins/death-counter/overlay`
- `http://127.0.0.1:29185/api/v1/plugins/win-counter/overlay`
- `http://127.0.0.1:29185/api/v1/overlay?overlay=default`
- `http://127.0.0.1:29185/api/v1/plugins/spotify-control/overlay`

## Updating

The tool checks for updates automatically on startup (configurable under `update` in `config.yaml`).
Before updating, back up `config/config.yaml`, `data/actions.mca`, and your Minecraft world (`server/default/`).

## Getting Help

- Read `docs/GUIDE.md` for detailed instructions.
- Open an issue at https://github.com/TechnikLey/Tiktok2Mc/issues.
