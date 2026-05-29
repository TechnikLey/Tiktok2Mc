# TikTok2Mc — User Guide

This guide explains how to use TikTok2Mc. No programming knowledge is required.

If you are setting the tool up for the first time, start with the [Quick Start](../README.md#quick-start) in the README.

---

## Table of Contents

- [Configuration](#configuration)
- [Actions and Triggers](#actions-and-triggers)
- [Plugins](#plugins)
- [Comment Commands](#comment-commands)
- [Overlays](#overlays)
- [Updating the Tool](#updating-the-tool)
- [Troubleshooting](#troubleshooting)
- [FAQ](#faq)

---

## Configuration

All settings are in `config/config.yaml`. Open this file with any text editor.

**Every setting has a comment above it explaining what it does.** Read the comments — they tell you exactly what each option controls.

### The three most important settings

1. **Your TikTok username** — under `tiktok.user`. Enter your username without the `@` symbol.
2. **Your RCON password** — under `rcon.password`. Change this from the default `ABC1234` to something secure. This password connects the tool to your Minecraft server.
3. **Which features are enabled** — each plugin section has `enabled: true` or `enabled: false`. Everything starts turned off. Turn on only what you need.

### Other useful settings

- **Java RAM** — under `java.xms` and `java.xmx`. Default is 4 GB each. If your computer has less than 12 GB RAM, lower both to `2G` or `1G`.
- **Server visibility** — under `console.log_level`. Controls which windows you see when the tool starts. Level 2 is recommended.
- **Auto-shutdown** — under `shutdown`. The tool can automatically shut down after your stream ends.
- **Comment commands** — under `comment_commands`. Let viewers send commands via TikTok chat.

> **Tip:** If you are unsure about a setting, leave it at the default. The inline comments in `config.yaml` explain every option.

---

## Actions and Triggers

The file `data/actions.mca` controls what happens in Minecraft when TikTok events occur.

### How it works

Each line has two parts, separated by a colon:

```
Trigger:Command
```

**Trigger** — what causes the action. This can be:
- A gift ID (like `5655`)
- A gift name (like `Rosa`)
- `follow` — someone follows your account
- `join` — someone joins your stream
- `comment` — someone writes a comment
- `share` — someone shares your stream
- `likes` — like milestone reached
- `like_2` — second like milestone reached

**Command** — what happens in Minecraft. The first character tells the tool what kind of command it is:

| Symbol | What it means | Example |
|--------|--------------|---------|
| `/` | Normal Minecraft command | `/give @a minecraft:diamond` |
| `!` | Server plugin command | `!tnt 5 0.5 2` |
| `$` | Special action | `$random` |
| `>>` | Show text on your stream overlay | `>>New Follower!\|{user}\|5` |

### Simple examples

```
# When someone follows, give everyone a golden apple
follow:/give @a minecraft:golden_apple 7

# When gift 5655 is received, spawn an Evoker
5655:/execute at @a run summon minecraft:evoker ~ ~ ~

# When someone follows, show a message on stream
follow:>>New Follower!|{user} is now following you!|5

# When gift 16071 is received, pick a random action
16071:$random
```

### Chaining commands

Use `;` to run multiple commands from one trigger:

```
follow:/give @a minecraft:golden_apple 7; >>New Follower!|{user}!|5
```

### Repeating commands

Add `xN` to run a command multiple times:

```
8913:/execute at @a run summon minecraft:evoker ~ ~ ~ x3
```

This spawns 3 Evokers instead of 1.

### Overlay text

The `>>` command shows text on your stream. Format:

```
>>Title|Subtitle|Duration
```

- **Title** — main text (large)
- **Subtitle** — smaller text below
- **Duration** — how many seconds it stays visible

**Placeholders:**
- `{user}` — replaced with the viewer's TikTok username
- `{comment}` — replaced with the comment text (only for `comment` trigger)

Example:

```
comment:>>{user} wrote:|{comment}|3
follow:>>New Follower!|{user} is now following you!|5
```

### The $random action

`$random` picks a random action from your list and runs it. Good for variety.

```
16071:$random
```

You can control which triggers are eligible in `config.yaml` under `random_triggers`.

### Like triggers

Like triggers fire when your stream reaches a certain number of likes. You set these up in two places:

1. **`config.yaml`** — under `like_goal.triggers`, set how many likes between triggers.
2. **`actions.mca`** — add a line using the trigger name to define what happens.

Example:

In `config.yaml`:
```yaml
like_goal:
  triggers:
    - id: likes_standard
      every: 100
      function: likes
```

In `actions.mca`:
```
likes:/execute at @a run summon minecraft:creeper ~ ~ ~
```

Every 100 likes, a Creeper spawns.

### Commenting out lines

Lines starting with `#` are ignored. Use this to temporarily disable an action:

```
#follow:/say Thanks for the follow!
```

---

## Plugins

Plugins are optional features you can turn on or off. Each runs independently — turning on the Timer does not affect the Death Counter.

### How to enable a plugin

Open `config/config.yaml`, find the plugin section, and change `enabled: false` to `enabled: true`.

Example:

```yaml
timer:
  enabled: true
  port: 29189
  start_time: 10
```

### Available plugins

| Plugin | What it does | OBS URL |
|--------|-------------|---------|
| **Timer** | Countdown timer. Can pause on player death. | `http://localhost:29189` |
| **Death Counter** | Counts player deaths. Updates automatically. | `http://localhost:29190` |
| **Win Counter** | Tracks wins and losses. | `http://localhost:29191` |
| **Like Goal** | Progress bar for stream likes. | `http://localhost:29193` |
| **Overlay Text** | Shows custom text messages on stream. | `http://localhost:29186/?overlay=default` |
| **Spotify Control** | Viewers control your Spotify via chat. | `http://localhost:29194` |
| **Channel Points** | Loyalty points for active viewers. | `http://localhost:29195` |

> **Note:** Everything starts disabled. Only turn on what you actually need.

### Timer

A countdown timer for your stream. Set the starting time in minutes under `timer.start_time`.

Control it via chat commands (if configured) or REST endpoints. See the inline comments in `config.yaml` for details.

### Death Counter

Automatically counts player deaths. No setup needed beyond enabling it. The counter updates in real-time on the overlay.

### Win Counter

Tracks wins and losses. You can add wins via webhook or chat command. Enable `decrement_on_death` if you want deaths to subtract from the win count.

### Like Goal

A progress bar that fills as your stream accumulates likes. Configure:
- `initial_goal` — how many likes to reach the first goal
- `goal_multiplier` — what happens after a goal is reached (0 = reset, 1 = add same amount, 2+ = multiply)
- `display_text` — text shown above the bar

### Overlay Text

Shows custom text messages on your stream. Triggered by `>>` commands in `actions.mca`.

You can create multiple named overlays. Each name gets its own URL:
- `http://localhost:29186/?overlay=default`
- `http://localhost:29186/?overlay=alerts`

Target a specific overlay from `actions.mca`:

```
follow:@alerts>>New Follower!|{user}!|5
```

Define overlay names in `config.yaml` under `overlay_text.overlays`.

### Spotify Control

Lets viewers control your Spotify playback through TikTok chat. Viewers can type commands like `$play`, `$pause`, `$skip`, `$volume 50`.

**Setup:**
1. Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) and create an app.
2. Add `http://127.0.0.1:29194/callback` as a Redirect URI.
3. Copy your Client ID and Client Secret into `config.yaml` under `spotify`.
4. Enable the plugin: `enabled: true`
5. On first start, your browser will open for Spotify login.

The overlay shows the current track with album art. Add it as an OBS Browser Source at `http://localhost:29194`.

> You also need to enable the `$` comment command group in `config.yaml` under `comment_commands` for chat commands to work.

### Channel Points

A loyalty system that awards points to active viewers automatically. Viewers earn points by interacting (commenting, liking, following, etc.).

Configure:
- `award_amount` — points earned per interval
- `award_interval_seconds` — how often points are awarded
- `ping_timeout_minutes` — how long after last interaction a viewer stays active
- `leaderboard_count` — how many top viewers to show on the overlay

No additional setup needed. Enable it and it starts working.

---

## Comment Commands

Let viewers send commands via TikTok chat. Each group has its own prefix character.

**Example:** A moderator types `#say Hello` and the tool sends `say Hello` to the Minecraft server.

### How it works

Commands are organized into **groups**. Each group has:
- A **prefix** (like `#` or `$`) that triggers it
- **Allowed roles** (who can use it)
- A **mode** (`deny-all` or `allow-all`)
- A **commands list**

### Default groups

The default `config.yaml` includes two groups:

1. **`#` group** — Minecraft commands via RCON. Only moderators and superfans can use it.
2. **`$` group** — Spotify control. Anyone can use it.

### Security

RCON commands send raw commands to your Minecraft server. If you allow `all` roles, use `deny-all` mode and only list safe commands.

### Cooldowns

Each group can have cooldowns to prevent spam:
- `cooldown` — seconds between any command in this group
- `user_cooldown` — seconds the same viewer must wait before their next command

Global cooldowns also exist at the top of the `comment_commands` section and apply across all groups.

> For full details, read the inline comments in `config.yaml` under `comment_commands`.

---

## Overlays

Most plugins provide a web page you can add as a **Browser Source** in OBS Studio (or any streaming software).

### How to add an overlay to OBS

1. In OBS, click the **+** under Sources and select **Browser Source**.
2. Enter a name (like "Death Counter").
3. Paste the plugin's URL (see the plugin table above).
4. Set the width and height to match your stream resolution.
5. Click **OK**.

The overlay will update automatically when events occur.

### Common overlay sizes

| Resolution | Width | Height |
|------------|-------|--------|
| 1080p | 1920 | 1080 |
| 720p | 1280 | 720 |

The overlays scale automatically, so any size works.

---

## Updating the Tool

The tool checks for updates automatically on startup (enabled by default). If a new version is available, it downloads and installs it.

**Before updating, back up these files:**
- `config/config.yaml` — your settings
- `data/actions.mca` — your action rules
- `data/shell_actions.txt` — your shell actions
- `server/mc/` — your Minecraft world

Copy them to a safe location outside the tool folder.

**To disable auto-updates:**

Set `update.enabled: false` in `config.yaml`.

**To check for updates manually:**

Visit `http://localhost:29185/api/v1/updates/check` in your browser while the tool is running.

---

## Troubleshooting

### "Address already in use" error

Another program is using one of the ports the tool needs. Common causes:
- Another Minecraft server running on port 25565
- Another instance of the tool already running

**Fix:** Close the other program, or change the port in `config.yaml`.

### TikTok connection fails

- You must be **live on TikTok** for the connection to work.
- Check your username in `config.yaml` — no `@` symbol.
- The tool retries automatically. Wait a few moments.

### Minecraft server won't start

- **Windows:** Java is included automatically. If it still fails, try restarting your computer.
- **Linux:** The tool will detect Java or help you install it. Make sure you run with `sudo`.

### Plugin not showing in OBS

- Make sure the plugin is enabled in `config.yaml` (`enabled: true`).
- Check that the URL is correct (see the plugin table above).
- Make sure the tool is running.

### Config file looks wrong after update

The updater creates a backup in `data/backups/migration/` before migrating. If something went wrong:
1. Close the tool.
2. Locate the most recent backup in `data/backups/migration/` and copy it to `config/config.yaml`.
3. Restart the tool.

### Security warnings in the console

- **RCON password warning** — Change the default password from `ABC1234` in `config.yaml`.
- **Network exposure warning** — Only appears if `server_host` is set to `0.0.0.0`. For most users, `127.0.0.1` is correct and safe.

These are just warnings. The tool will still run.

---

## FAQ

**Q: Do I need to be live on TikTok for the tool to work?**

A: Yes. The tool connects to your active TikTok Live stream. It will keep retrying automatically until you go live.

**Q: Can I test actions without going live?**

A: Yes. Use the included test tool (`test/test_trigger.exe` on Windows or `test/test_trigger.bin` on Linux). Enter a trigger name (like `follow` or a gift ID) to simulate it.

**Q: How do I know if the tool is working?**

A: The console window shows live output. If you see "Connected to TikTok" and the Minecraft server starts without errors, everything is running.

**Q: How often is the tool updated?**

A: There is no fixed schedule. Updates come out when new features or fixes are ready.

**Q: Can I use a different Minecraft version?**

A: Yes. Replace the `.jar` file in `server/mc/`. The new server must support RCON and datapacks (most do).

**Q: Can I use modded servers (Forge, Fabric, Paper)?**

A: Yes. Replace the server `.jar` as described above. Make sure the modded server supports RCON and datapacks.

**Q: Does the tool work with Minecraft Bedrock Edition?**

A: No. Only Java Edition supports the features this tool needs.

**Q: Can I run the Minecraft server on a different computer?**

A: Yes. Set the RCON IP and port in `config.yaml` to match your remote server. The tool itself must still run on your streaming PC.

**Q: Can I use the overlays without OBS?**

A: Yes. The overlays are web pages. You can open them in any browser or add them to any streaming software that supports Browser Sources.

**Q: How do I find gift IDs?**

A: Open `core/gifts.json` in a text editor. Each gift has an `id` field.

**Q: Can I use the tool with Twitch or YouTube?**

A: The tool is designed for TikTok Live. The license restricts commercial use on other platforms.

**Q: My server is lagging. What can I do?**

A: Lower the RAM allocation in `config.yaml` under `java.xms` and `java.xmx`. Also avoid using `comment` or `join` triggers with complex commands on busy streams.

**Q: Can viewers spam commands?**

A: Use cooldowns in `config.yaml` under `comment_commands` to limit how often commands can be used.

---

## Additional Resources

- **README:** [README.md](../README.md) — quick start and overview
- **Changelog:** [CHANGELOG.md](./CHANGELOG.md) — release history
- **GitHub:** [https://github.com/TechnikLey/Tiktok2Mc](https://github.com/TechnikLey/Tiktok2Mc)
- **Report Issues:** [GitHub Issues](https://github.com/TechnikLey/Tiktok2Mc/issues)