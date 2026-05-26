# TikTok to Minecraft Integration

Connect your TikTok Live stream to a Minecraft server. When viewers send gifts, follow you, or hit like milestones, Minecraft commands are triggered in real-time on your server.

> **Author:** TechnikLey — [GitHub](https://github.com/TechnikLey/Tiktok2Mc)  
> **License:** PolyForm Noncommercial 1.0.0 (with creator exception)

---

## Table of Contents

- [TikTok to Minecraft Integration](#tiktok-to-minecraft-integration)
  - [Table of Contents](#table-of-contents)
  - [Project Introduction](#project-introduction)
  - [Features](#features)
  - [Requirements](#requirements)
  - [Installation](#installation)
    - [Windows](#windows)
    - [Linux](#linux)
  - [Quick Start](#quick-start)
  - [Configuration](#configuration)
  - [Usage](#usage)
    - [Understanding actions.mca](#understanding-actionsmca)
    - [Trigger Types](#trigger-types)
    - [Command Types](#command-types)
      - [`/` — Vanilla Minecraft Commands](#--vanilla-minecraft-commands)
      - [`!` — Server Plugin Commands (RCON)](#--server-plugin-commands-rcon)
      - [`$` — Special Actions](#--special-actions)
      - [`>>` — Overlay Text](#--overlay-text)
    - [Chaining and Repeating Commands](#chaining-and-repeating-commands)
    - [Using Trigger Names vs IDs](#using-trigger-names-vs-ids)
    - [The $random Action](#the-random-action)
    - [Like Triggers](#like-triggers)
    - [Comment Commands](#comment-commands)
    - [Shell Actions (shell\_actions.txt)](#shell-actions-shell_actionstxt)
    - [Testing Triggers Without TikTok](#testing-triggers-without-tiktok)
  - [Minecraft Server](#minecraft-server)
    - [Starting the Server](#starting-the-server)
    - [Joining Locally](#joining-locally)
    - [Letting Friends Join (Port Forwarding)](#letting-friends-join-port-forwarding)
    - [Server Details](#server-details)
    - [Datapack Mechanics](#datapack-mechanics)
    - [Replacing the Server Version](#replacing-the-server-version)
  - [Plugins and Overlays](#plugins-and-overlays)
    - [Death Counter](#death-counter)
    - [Win Counter](#win-counter)
    - [Like Goal](#like-goal)
    - [Stream Timer](#stream-timer)
    - [Overlay Text](#overlay-text)
    - [Spotify Control](#spotify-control)
      - [Setup](#setup)
      - [Chat Commands via comment\_commands](#chat-commands-via-comment_commands)
      - [Direct Trigger Actions (for actions.mca)](#direct-trigger-actions-for-actionsmca)
    - [Channel Points](#channel-points)
      - [Setup](#setup-1)
      - [How Viewers Earn Points](#how-viewers-earn-points)
      - [Overlay](#overlay)
      - [Per-Command Points Cost, Cooldown \& Roles](#per-command-points-cost-cooldown--roles)
      - [Global Cooldown (Cross-Group)](#global-cooldown-cross-group)
    - [Follow Tracking](#follow-tracking)
    - [Multiple Overlays](#multiple-overlays)
    - [VS Code Extension for .mca Files](#vs-code-extension-for-mca-files)
  - [Maintenance](#maintenance)
    - [Updating the Tool](#updating-the-tool)
    - [Backing Up Your Data](#backing-up-your-data)
    - [Ports Used by the Tool](#ports-used-by-the-tool)
    - [Log Files](#log-files)
    - [Replacing the Minecraft Server Version](#replacing-the-minecraft-server-version)
  - [FAQ](#faq)
  - [AI Prompt File](#ai-prompt-file)
    - [What it does](#what-it-does)
    - [How to use it](#how-to-use-it)
    - [Who this is for](#who-this-is-for)
  - [Additional Resources](#additional-resources)

---

## Project Introduction

TikTok2Mc bridges TikTok Live events — gifts, follows, likes, comments, joins, and shares — to a Minecraft server in real-time. Each event can be mapped to one or more Minecraft commands, allowing your stream audience to interact directly with the game.

The tool bundles:

- A **Minecraft 1.21.11 server** (Vanilla)
- A **Java runtime** (auto-downloaded on Windows; auto-detected or installed on Linux)
- Two **server-side plugins**: MinecraftServerAPI (player event webhooks) and DelayedTNT (custom TNT spawning)
- **Overlay plugins** for stream notifications: Death Counter, Win Counter, Like Goal, Timer, Overlay Text
- An **auto-updater** for seamless version management

---

## Features

- **Real-time TikTok Live connection** via the [TikTokLive](https://github.com/isaackogan/TikTokLive) library
- **Customizable action mappings** — connect any gift, follow, like milestone, comment, or join to Minecraft commands
- **Multiple command types:**
  - Vanilla Minecraft commands (written to a datapack)
  - Server plugin commands (sent via RCON)
  - Built-in special actions (`$random`)
  - Stream overlay notifications
- **Command chaining** — run multiple commands from a single trigger
- **Command repeating** — repeat a command multiple times
- **Like milestones** — configure custom like thresholds with individual commands
- **Comment Commands** — let viewers send Minecraft commands via chat with role-based access control
- **HTTP Actions** — run shell commands on your PC when a gift is received
- **Built-in overlays** for OBS / streaming software
- **Event Hooks** — extend functionality with custom Python hook scripts
- **Auto-updater** — keeps the tool up to date
- **Cross-platform** — Windows and Linux

---

## Requirements

| Requirement | Details |
|-------------|---------|
| **Operating System** | Windows 10+ or Linux |
| **RAM** | 12 GB minimum recommended (Minecraft server uses up to 4 GB by default — adjustable) |
| **TikTok Account** | Required for live streaming |
| **Minecraft** | Java Edition (any version that supports datapacks and RCON, 1.13+) |
| **Streaming Software** | OBS Studio, vMix, Streamlabs Desktop, or TikTok Live Studio / Twitch Studio |

---

## Installation

### Windows

1. Download the latest release from the [GitHub Releases page](https://github.com/TechnikLey/Tiktok2Mc/releases).
2. Extract the ZIP archive to any folder.
3. Run `start.exe` to launch the tool.

No manual Java installation is required — the bundled Java runtime is used automatically.

### Linux

1. Download the latest release.
2. Extract the archive.
3. Run `sudo ./start.bin` from the terminal.

The tool will detect your system Java or prompt you to install it if missing. Running with `sudo` is required for updates and permission-sensitive paths.

> [!TIP]
> The tool shows a sudo warning on Linux. You can disable it by setting `show_sudo_warning: false` in `config.yaml`.

---

## Quick Start

1. **Edit the configuration**

   Open `config/config.yaml` in any text editor and change these two values:

   ```yaml
   TikTok:
     User: your_tiktok_username   # Replace with your TikTok username (no @)
   RCON:
     Password: ABC1234            # Replace with any password you like
   ```

> [!IMPORTANT]
> Do not use Tab for indentation — always use spaces. Keep a space after colons (e.g., `User: myname`, not `User:myname`).

2. **Set up actions (optional)**

   The file `data/actions.mca` defines what happens in Minecraft when events occur. It comes with example actions — adjust them to your liking. See [Understanding actions.mca](#understanding-actionsmca) for the full syntax.

3. **Launch the tool**

   - **Windows:** Double-click `start.exe`
   - **Linux:** Run `sudo ./start.bin` in a terminal

   The tool will:
   - Start the Minecraft server
   - Connect to your TikTok Live
   - Begin listening for events

4. **Join the Minecraft server**

   - Open Minecraft Java Edition
   - Go to **Multiplayer > Add Server**
   - Enter `localhost:25565` as the address
   - Click **Done** and join

> [!IMPORTANT]
> You must be live on TikTok for the connection to work. The tool will keep trying to reconnect automatically.

---

## Configuration

All settings are stored in `config/config.yaml`. Open this file with any text editor — every option is documented with inline comments that explain its purpose, allowed values, and defaults.

---

## Usage

### Understanding actions.mca

The file `data/actions.mca` is the core of the tool. Each line maps a TikTok event to a Minecraft command.

**Format:**

```
Trigger:TypeCommand
```

- **Trigger** — What causes the action (gift ID, gift name, `follow`, `join`, `comment`, `share`, `likes`, `like_2`, or a custom like trigger name)
- **:** — A colon separates the trigger from the command (no spaces around it)
- **Type** — The first character(s) that tell the tool what kind of command it is:
  - `/` — Vanilla Minecraft command
  - `!` — Server plugin command
  - `$` — Special built-in or script action
  - `>>` — Overlay text notification
- **Command** — The actual command to run

> [!WARNING]
> The type character (`/`, `!`, `$`, `>>`) is required. Omitting it will cause the command to fail.

**Examples:**

```
follow:/give @a minecraft:golden_apple 7
5655:!tnt 2 0.1 2 Notch
16071:$random
comment:>>{user} wrote:|{comment}|3
```

Lines starting with `#` are treated as comments and ignored.

```
# This line is disabled
#8913:/execute at @a run summon minecraft:evoker ~ ~ ~ x3
```

---

### Trigger Types

| Trigger | Description | Example |
|---------|-------------|---------|
| **Gift ID** (number) | Fires when a specific TikTok gift is received | `5655:/give @a minecraft:diamond` |
| **Gift Name** (text) | Fires when a gift with that name is received | `Rosa:/give @a minecraft:rose` |
| **Gift Name with spaces** | Must be wrapped in single quotes | `'Tom the Tomato':/give @a minecraft:carrot 10` |
| `follow` | Fires when someone follows your account | `follow:/say Thanks for the follow!` |
| `join` | Fires when a viewer joins the stream | `join:>>Welcome!|{user} just joined!|3` |
| `comment` | Fires for every chat comment | `comment:>>{user} wrote:|{comment}|3` |
| `share` | Fires when a viewer shares the stream | `share:/give @a minecraft:emerald 1` |
| `likes` | Fires at a configured like interval (default: every 100) | `likes:/execute at @a run summon minecraft:creeper ~ ~ ~` |
| `like_2` | Fires at a second like interval (default: every 100,000) | `like_2:/clear @a *; /kill @a` |

> [!WARNING]
> The `comment` and `join` triggers fire for **every** event. On active streams this can be very frequent. Avoid complex or expensive commands here to prevent overwhelming your server.
>
> **Note:** If `comment_commands` is enabled and a comment matches a command prefix (e.g., `#say hello`), **both** the comment_commands handler AND the `comment` trigger in `actions.mca` fire by default. You can disable this per group with `trigger_comment_event: false` in `config.yaml`.

---

### Command Types

#### `/` — Vanilla Minecraft Commands

Standard Minecraft commands, compiled to a datapack and executed in-game.

```
follow:/give @a minecraft:golden_apple 7
8913:/execute at @a run summon minecraft:evoker ~ ~ ~ x3
```

#### `!` — Server Plugin Commands (RCON)

Commands sent directly to the Minecraft server via RCON. Used for server plugin commands that are not part of vanilla Minecraft.

```
5655:!tnt 2 0.1 2 Notch
```

> [!NOTE]
> **The `!tnt` Command (DelayedTNT Plugin):**
>
> | Syntax | Description |
> |--------|-------------|
> | `!tnt <Amount>` | Spawns TNT with the delay set in `config.yml` |
> | `!tnt <Amount> <Player>` | Spawns TNT for a specific player |
> | `!tnt <Amount> <Delay> <Fuse>` | Spawns TNT with custom delay and fuse |
> | `!tnt <Amount> <Delay> <Fuse> <Player>` | Spawns TNT with custom delay, fuse, and target player |
>
> - **Amount** — How many TNT to spawn
> - **Delay** — Seconds between each TNT spawn (e.g., `0.1`)
> - **Fuse** — Seconds before each TNT explodes
> - **Player** — Player name to spawn TNT at

> [!WARNING]
> Do not write vanilla Minecraft commands with `!`. Doing so may cause the server to crash or freeze, and the tool will require significantly more resources.

#### `$` — Special Actions

Special built-in or script actions.

- **`$random`** — Picks and executes a random action from the available trigger pool. See [The $random Action](#the-random-action).
- **Custom `$` commands** — Defined via Event Hooks. See [Event Hooks](#event-hooks--commands).

#### `>>` — Overlay Text

Sends a text notification to the stream overlay. Used as an OBS Browser Source.

```
>>Title|Subtitle|Duration
```

| Part | Description |
|------|-------------|
| **Title** | Main text to display (large) |
| **Subtitle** | Smaller text below the title |
| **Duration** | How many seconds the text stays visible (optional, default: 3) |

**Placeholders:**

- `{user}` — Replaced with the TikTok username of the viewer who triggered the action
- `{comment}` — Replaced with the comment text (only for the `comment` trigger)

**Examples:**

```
follow:>>New Follower!|{user} is now following you!|5
comment:>>{user} wrote:|{comment}|3
16111:>>Diamond!|Thank you {user}!
```

> [!NOTE]
> The overlay name can be specified with `@Name>>` syntax for multiple overlays. See [Multiple Overlays](#multiple-overlays).

---

### Chaining and Repeating Commands

**Chaining with `;`:**

Run multiple commands from a single trigger, separated by `;`. They execute left to right.

```
like_2:/clear @a *; /kill @a
follow:/give @a minecraft:golden_apple 7; >>New Follower!|{user} is now following you!|5
```

**Repeating with `xN`:**

Append `x` followed by a number to repeat a command that many times.

```
8913:/execute at @a run summon minecraft:evoker ~ ~ ~ x3
```

This summons 3 Evokers. Without `x3`, the command runs once.

---

### Using Trigger Names vs IDs

Triggers can be specified by either **gift ID** (number) or **gift name** (text). Both are valid:

```
16212:/give @a minecraft:diamond 5
Cool:/give @a minecraft:diamond 5
```

Both lines do the same thing — when the gift "Cool" (ID 16212) is received, all players get 5 diamonds.

**Priority rule:** The system checks names first, then IDs. If a name match is found, the ID-based line is ignored. If both a name and its ID are defined for the same gift, only the name-based trigger runs.

**Names with spaces** must be wrapped in single quotes:

```
'Tom the Tomato':/give @a minecraft:carrot 10
```

All available gift IDs and names are defined in `core/gifts.json`. Gift images are available in `core/assets/`.

---

### The $random Action

The `$random` command picks a random eligible trigger from your defined actions and executes it.

```
16071:$random
```

When gift ID 16071 is received, the tool selects one random trigger from the pool and runs its command.

You can control which triggers are eligible using the `random_triggers` section in `config/config.yaml`. Use `mode: deny-all` to allow only the listed triggers, or `mode: allow-all` to allow all triggers except those listed.

---

### Like Triggers

Like triggers fire when the total number of likes reaches a configured threshold. They are defined in two places that work together:

- **`config.yaml`** — under `like_goal.triggers`, you define the interval (every N likes), the trigger name, and whether it is enabled.
- **`actions.mca`** — you add a line using the trigger name from the config to specify which command to run.

See `config/config.yaml` for the full configuration options and examples.

---

### Comment Commands

The `comment_commands` feature lets viewers send commands via TikTok chat. Viewers type a prefix (e.g., `#` or `$`) followed by a command, and the tool forwards it to Minecraft (via RCON) or to an HTTP endpoint (for plugins like Spotify).

Commands are organized into **groups** — each with its own prefix, role requirements, allowed commands list, and optional cooldowns.

**Example:** A moderator writes `#say Hello` → the command `say Hello` is sent to the Minecraft server via RCON.

> [!WARNING]
> Some prefix characters like `!` may not work reliably in all streaming software. The `#` character is recommended for reliable operation.

All settings are configured in `config/config.yaml` under `comment_commands` — the file has detailed inline comments explaining every option.

> [!NOTE]
> Comment Commands are separate from the `comment` trigger in `actions.mca`. The `comment` trigger fires for every comment regardless of prefix. Comment Commands only activate when the prefix matches and the viewer has the required role.
>
> When a comment matches a command prefix, **both** systems fire — the Comment Command AND the `comment` trigger in `actions.mca`. If you have actions mapped to `comment`, they will execute in addition to the chat command.
>
> You can control this per group with `trigger_comment_event: true/false` in `config.yaml`. Set it to `false` to prevent the `comment` trigger from firing when a command matches that group.

---

### Shell Actions (shell_actions.txt)

The file `data/shell_actions.txt` runs shell commands on your computer when a gift is received.

**Format:**

```
GiftID:ShellCommand
```

- **GiftID** — Numeric gift ID (same as in `actions.mca` and `core/gifts.json`)
- **ShellCommand** — Any shell command that can run on your computer

**Example:**

```
18508:curl -X POST http://localhost:29191/add?amount=10
16071:curl -X POST http://localhost:29191/remove?amount=10
```

**Important notes:**

- HTTP actions are **gift-only** — not supported for `follow`, `join`, `comment`, or like triggers.
- Both `actions.mca` and `shell_actions.txt` are checked for every gift. If the same gift ID appears in both, **both run independently** — they do not conflict.
- Lines starting with `#` are comments.
- Lines starting with `//define name = value` define variables that are replaced in all following commands with `{name}`.
- The command runs directly on your computer. Only use commands you trust.

---

### Testing Triggers Without TikTok

A test tool is included to simulate triggers and comments without going live.

- **Windows:** `test/test_trigger.exe`
- **Linux:** `test/test_trigger.bin`

**Simulating triggers (gifts, follows, likes, etc.):**

1. Make sure the tool is running (TikTok connection is not required).
2. Start the test executable.
3. Enter any trigger name (e.g., `follow`, `like_2`, or a gift ID like `5655`) and optionally a username.
4. The tool simulates the trigger — all actions, overlays, and Minecraft commands will run as configured.

**Simulating chat comments:**

1. Enter `comment` as the trigger.
2. Enter a username, the comment text (including the prefix, e.g., `#say Hello` or `$play`), and optionally set moderator/superfan/fanclub roles.
3. The tool processes the comment exactly as if a viewer typed it in TikTok chat — prefix matching, role checks, command filters, cooldowns, and dispatch all apply.

**Toggle TikTok connection:** Enter `tiktok` as the trigger to toggle the TikTok connection on or off. This setting resets when the tool restarts.

> [!IMPORTANT]
> The test tool only confirms that the trigger or comment was sent to the tool. It does not guarantee that the action was executed in Minecraft or by a plugin. Always check in-game or in the logs.

---

## Minecraft Server

### Starting the Server

The Minecraft server starts automatically when you launch the tool. The server is managed by the orchestrator — no manual intervention needed.

### Joining Locally

1. Start the tool with `start.exe` (Windows) or `sudo ./start.bin` (Linux).
2. Open Minecraft Java Edition.
3. Go to **Multiplayer > Add Server**.
4. Enter `localhost:25565`.
5. Click **Done** and join.

### Letting Friends Join (Port Forwarding)

To let others join over the internet, set up port forwarding on your router:

1. Open your router's settings (usually `192.168.1.1` or `192.168.0.1`).
2. Find the **Port Forwarding** section.
3. Forward port **25565** (TCP/UDP) to the local IP of the computer running the server.
4. Share your public IP address with friends.

> [!NOTE]
> Port forwarding varies by router model. Search "[your router model] port forwarding" for specific instructions.

### Server Details

| Setting | Default |
|---------|---------|
| Minecraft version | 1.21.11 (Vanilla) |
| Java | OpenJDK 21 (bundled on Windows) |
| RAM | 4 GB (configurable via `Java.Xms` / `Java.Xmx` in `config.yaml`) |
| Minecraft port | 25565 |
| RCON port | 25575 |
| Server directory | `server/mc/` |
| Server plugins | MinecraftServerAPI, DelayedTNT |

### Datapack Mechanics

Vanilla commands (prefixed with `/` in `actions.mca`) are compiled to `.mcfunction` files in the `StreamingTool` datapack at `world/datapacks/StreamingTool/`. This datapack is generated dynamically each time the tool starts.

Plugin commands (prefixed with `!`) bypass the datapack and are sent directly to the server via RCON. The RCON queue uses dynamic throttling (0.01s–0.5s delay based on queue depth).

### Replacing the Server Version

1. Go to the `server/mc/` folder.
2. Note the **filename** of the current `.jar` file.
3. Replace it with your new server `.jar` file (Forge, Fabric, Paper, etc.).
4. **Rename** the new file to match the original filename exactly.

> [!NOTE]
> Your replacement server must support RCON and datapacks (available in almost all Minecraft versions from 1.1 onward and 1.13 onward respectively).

---

## Plugins and Overlays

The tool includes several built-in overlay plugins. These are small web pages that you can add as **Browser Sources** in your streaming software. Each plugin can be enabled or disabled individually in `config/config.yaml`.

### Death Counter

Displays the number of times the player has died. Updates automatically on in-game death.

- **OBS URL:** `http://localhost:29190`

### Win Counter

Tracks wins and losses. Decrements on player death, increments when the Stream Timer reaches zero.

- **OBS URL:** `http://localhost:29191`

### Like Goal

Shows a progress bar tracking likes toward a goal. Configure the display text, initial goal, and multiplier mode in `config/config.yaml`.

- **OBS URL:** `http://localhost:29193`

### Stream Timer

A countdown timer that pauses on player death and resumes on respawn. When it reaches zero, a win is counted. The starting time is set in `config/config.yaml`.

- **OBS URL:** `http://localhost:29189`

### Overlay Text

Displays custom text notifications on stream.

- **OBS URL:** `http://localhost:29186/?overlay=default`

> [!NOTE]
> Overlay Text works best with **DCS** mode. In **ICS** mode, a green screen filter is needed, which may reduce text quality.

---

### Spotify Control

Lets viewers control Spotify playback through TikTok chat comments and events. Displays the current track as an OBS overlay.

#### Setup

1. **Create a Spotify Developer App:**
   - Go to [https://developer.spotify.com/dashboard](https://developer.spotify.com/dashboard)
   - Click **Create App** and choose a name (e.g. "TikTok2Mc Spotify")
   - Under **Redirect URIs**, add: `http://127.0.0.1:29194/callback`
   - Copy the **Client ID** and **Client Secret**

2. **Add to config.yaml:**
   ```yaml
   spotify:
     enabled: true
     client_id: "YOUR_CLIENT_ID"
     client_secret: "YOUR_CLIENT_SECRET"
     playtrack_mode: "replace"     # "replace" — play immediately, "queue" — add to queue
   ```

3. **Start the plugin & log in:**
   - When the tool starts, your browser opens automatically for Spotify login
   - Alternatively: open `http://localhost:29194/login` in your browser

#### Chat Commands via comment_commands

The default `config.yaml` includes a `$` group for Spotify chat control (see `comment_commands` section). Viewers type `$play`, `$pause`, `$skip`, `$prev`, `$volume 50`, `$save`, `$shuffle`, `$repeat`, `$current`, `$playtrack Artist - Song`, etc. in TikTok chat. See [Comment Commands](#comment-commands) for details.

- **`$playtrack`** — Searches Spotify for the given artist and song, then either plays it immediately or adds it to the queue (configured via `spotify.playtrack_mode` in `config.yaml`). Unlike other commands, if the song is not found, no channel points are deducted and no cooldowns are triggered. Requires `comment_commands.commands_config.playtrack.conditional: true` to enable this safe-fail behavior.

> [!IMPORTANT]
> **Viewer feedback limitations** — TikTok chat is a one-way input: the tool can receive commands but cannot reply directly to a viewer. This means there is currently no built-in way to tell a viewer whether their `$playtrack` succeeded, why their points weren't deducted, or how many points they have left. While you could build custom overlay feedback using `>>` in `actions.mca`, this approach does not scale well — on busy streams with frequent commands, overlays can pile up or get overwritten, causing viewer confusion rather than clarity. A per-user notification system (whisper-style) is not feasible within TikTok's event model. For now there is no optimal solution that works across all stream sizes.

#### Direct Trigger Actions (for actions.mca)

Events (gifts, follows, likes) can also trigger Spotify actions:

```
follow:$spotify_current              # Shows current song on follow
5655:$spotify_play                   # Plays on gift
5655:$spotify_pause                  # Pauses on gift
8913:$spotify_next                   # Next track on gift
16071:$spotify_previous              # Previous track
6267:$spotify_volume_up              # Volume up
7168:$spotify_volume_down            # Volume down
18508:$spotify_save                  # Save song
'Tom the Tomato':$spotify_shuffle    # Toggle shuffle
```

- **OBS URL:** `http://localhost:29194`

All options are configured in `config/config.yaml` under `spotify:` — the file has detailed inline comments for each setting.

### Channel Points

Awards loyalty points to active viewers automatically. Points are deducted automatically when a viewer uses a command that has `points_cost` set — no separate commands needed.

#### Setup

No additional setup is needed beyond enabling it in `config.yaml`:

```yaml
channel_points:
  enabled: true
  port: 29195
  award_amount: 10
  award_interval_seconds: 60
  ping_timeout_minutes: 10
  leaderboard_count: 10
```

- **`award_amount`** — points earned per interval by each active viewer
- **`award_interval_seconds`** — how often points are awarded (e.g. 60 = every minute)
- **`ping_timeout_minutes`** — viewer's `last_seen` must be within this window to receive points. Resets on every interaction.
- **`leaderboard_count`** — number of top viewers shown on the overlay

#### How Viewers Earn Points

Viewers are tracked via TikTok Live events — each interaction updates their `last_seen` timestamp, keeping them in the active window:

| Event | Triggers ping | Notes |
|-------|--------------|-------|
| Joining the stream | ✅ | Fires once when viewer enters |
| Writing a comment | ✅ | Every comment (e.g. `$skip`) |
| Liking | ✅ | Each like event from that user |
| Sending a gift | ✅ | Each gift sent |
| Following | ✅ | Once per unique follow (tracked) |
| Sharing | ✅ | Each share event |

Every `award_interval_seconds`, all viewers whose `last_seen` is within `ping_timeout_minutes` get `award_amount` points. A viewer who types `$skip`, sends a gift, likes, or follows is immediately marked active — no manual claiming needed.

> [!NOTE]
> **Pure lurkers** (watching without any interaction) are **not** tracked — TikTok does not expose passive viewership data. Viewers must join, comment, or otherwise interact to accumulate points.

#### Overlay

- **OBS URL:** `http://localhost:29195`
- Shows a live leaderboard that updates every 10 seconds via SSE.

#### Per-Command Points Cost, Cooldown & Roles

Per-command settings go in a separate `commands_config` block — the `commands` list stays clean with just names:

```yaml
commands:
  - play
  - pause
  - skip
  - prev
  - volume
  - save
  - repeat
  - shuffle
  - current
  - playtrack

commands_config:
  skip:
    points_cost: 50        # viewer needs 50 points
    cooldown: 30           # 30s between any $skip
  prev:
    points_cost: 20
  playtrack:
    points_cost: 50
    cooldown: 30
    conditional: true      # points & cooldowns only apply if song is found
    url: "http://127.0.0.1:{spotify_port}/playtrack?user={user}&text={text}"
    handler: http
  volume:
    roles: [moderator]     # only moderators
```

When a viewer uses `$skip`, the system checks their balance, deducts the cost, applies the cooldown, and dispatches the command.

**Conditional commands** (like `$playtrack`) behave differently: the system first sends the request to the plugin, waits for the response, and only deducts points and applies cooldowns if the song was found. If the song could not be found, nothing is deducted and no cooldown fires — the viewer can try again immediately.

#### Global Cooldown (Cross-Group)

Global cooldowns live at the top of the `comment_commands` section, **outside** any group, and apply across **all** groups.

- **`cooldown`** — When set to `10`, a viewer who triggers `$skip` must wait 10 seconds before ANY command works (even `#op` or `!points`) from ANY viewer.
- **`user_cooldown`** — When set to `30`, a viewer who triggers `$skip` must wait 30 seconds before THEIR next command works in any group. Other viewers are not affected.

```yaml
comment_commands:
  enabled: true
  cooldown: 10              # 10s global cooldown across ALL groups (any user)
  user_cooldown: 30         # 30s per-user global cooldown across all groups
  groups:
    - prefix: "$"
      cooldown: 0            # per-group cooldown still works on top
      ...
    - prefix: "#"
      cooldown: 0
      ...
```

Each group keeps its own `cooldown` and `user_cooldown` — those still apply in addition to the global ones. Set a global value to `0` to disable.

---

### Follow Tracking

Prevents viewers from repeatedly unfollowing and refollowing to farm the follow trigger. Each unique follower is written to a file — subsequent follows from the same user are ignored.

Configured in `config/config.yaml` under `tiktok.follow_tracking`:

```yaml
tiktok:
  follow_tracking:
    mode: "all_time"    # or "per_stream"
    file: "data/followed_users.txt"
```

- **`all_time`** (default) — Follows are tracked across all streams. Once a user is recorded, their future follows are ignored, even after restarting the tool.
- **`per_stream`** — The tracked list resets every time the tool starts. Each stream starts fresh.

> [!IMPORTANT]
> Only new follows that happen **while the tool is running** are tracked. Users who already followed before the tool was started **cannot** be detected — they will trigger the follow action the first time they follow during a tracked stream. This is a limitation of TikTok's event system: we only see follow events that occur while connected.

---

### Multiple Overlays

You can run several overlay windows simultaneously — each as a separate OBS Browser Source pointing to a different named overlay. Configure the list of overlay names in `config/config.yaml` under `overlay_text.overlays`.

Each name creates a unique URL: `http://localhost:29186/?overlay=NAME`

**Targeting overlays from `actions.mca`:**

```
follow:@alerts>>New Follower!|{user} is now following you!|5
join:@stats>>Welcome!|{user} just joined!|3
```

Writing `>>` without a name targets the `default` overlay automatically.

> [!IMPORTANT]
> The name must exactly match one of the names defined under `Overlays` in `config.yaml`. If no match is found, the message is silently dropped.

---

### VS Code Extension for .mca Files

A custom VS Code extension (`mca.vsix`) is included in `core/assets/mca.vsix`.

**Features:**
- Syntax highlighting for `.mca` files
- Error highlighting for common mistakes (missing colons, wrong prefixes)
- Colorful formatting for triggers, commands, and comments

**Installation:**
1. Open VS Code.
2. Go to Extensions (Ctrl+Shift+X).
3. Click the three-dot menu > **Install from VSIX...**.
4. Select `core/assets/mca.vsix`.
5. Open any `.mca` file to see syntax highlighting.

---

## Maintenance

### Updating the Tool

The tool can update itself automatically (enabled by default). On startup it checks for new versions and installs updates. You can disable this in `config/config.yaml`.

> [!IMPORTANT]
> Always back up your data before updating. See [Backing Up Your Data](#backing-up-your-data).

### Backing Up Your Data

Before updating or making major changes, save copies of these items:

- `server/mc/` — Your Minecraft world and server data
- `data/actions.mca` — Your custom action mappings
- `data/shell_actions.txt` — Your shell action mappings
- `config/config.yaml` — Your configuration

Copy them to a safe location outside the tool folder.

### Ports Used by the Tool

| Port | Used For |
|------|----------|
| 25565 | Minecraft Server |
| 25575 | RCON (Server Communication) |
| 29185 | Web Dashboard (GUI) |
| 29187 | Minecraft Server API |
| 29188 | Internal Web Server |
| 29189 | Stream Timer Overlay |
| 29190 | Death Counter Overlay |
| 29191 | Win Counter Overlay |
| 29186 | Overlay Text |
| 29193 | Like Goal Overlay |
| 29194 | Spotify Control |

Under normal circumstances, you do not need to change any ports. Only change a port if you get an "Address already in use" error.

### Log Files

The tool creates several log files during operation. Here's what each contains:

| File | Purpose |
|------|---------|
| `logs/update_logs/updater_*.log` | Update check logs — one file per update attempt |
| `data/revenue_log.jsonl` | Gift revenue tracking — **gross estimate** (diamonds × 0.005 USD). TikTok pays out only a portion of this amount to the streamer (typically around 50%, varies by region and agreement). The actual net revenue is **not** tracked by this tool. |
| `data/window_state_*.json` | Window size/position for plugin overlays (not logs, but stored here) |

**Cleaning up:** Old update logs are automatically removed based on `max_update_logs` in `config.yaml` (default keeps recent ones, deletes older). Revenue logs and window state files are safe to delete manually if you want a fresh start.

### Replacing the Minecraft Server Version

See [Replacing the Server Version](#replacing-the-server-version) in the Minecraft Server section.

---

## FAQ

**Q: Do I need to be live on TikTok for the tool to work?**

A: Yes. The tool connects to your active TikTok Live stream. It will keep retrying until you go live.

**Q: Can I test actions without going live?**

A: Yes. Use the included test tool (`test/test_trigger.exe` on Windows or `test/test_trigger.bin` on Linux). See [Testing Triggers Without TikTok](#testing-triggers-without-tiktok).

**Q: How do I know if the tool is working correctly?**

A: The main console window shows live log output. If you see "Connected to TikTok" and the Minecraft server starts without errors, everything is running. You can also use the test trigger tool to verify actions fire correctly.

**Q: How often is the tool updated?**

A: There is no fixed schedule. Updates are published when new features, bug fixes, or compatibility improvements are ready.

**Q: How do I update the tool?**

A: Updates are automatic by default. The tool checks for new versions on startup and installs them. You can disable auto-updates in `config.yaml`.

**Q: Can I use a different Minecraft version?**

A: Yes. Replace the server `.jar` file in `server/mc/`. The replacement must support RCON and datapacks.

**Q: Can I use modded servers (Forge, Fabric, Paper)?**

A: Yes. Replace the server `.jar` as described above. Ensure the modded server supports RCON and datapacks.

**Q: Does the tool work with Minecraft Bedrock Edition?**

A: No. The tool is designed for Minecraft Java Edition. Bedrock Edition does not support datapacks or RCON in the same way.

**Q: Can the Minecraft server run on a different computer?**

A: Yes. You can run the Minecraft server on a separate machine and point the tool to it. Set the RCON IP and port in `config.yaml` to match your remote server. The tool itself must still run on your streaming PC.

**Q: Can I use the overlays without OBS?**

A: Yes. The overlays are standard web pages served on localhost ports. You can open them in any browser or add them as Browser Sources in any streaming software that supports that feature (vMix, Streamlabs Desktop, etc.).

**Q: How do I find gift IDs?**

A: Open `core/gifts.json` in a text editor. Each gift entry has an `id` field. You can also enable the GUI search tool in `config.yaml`.

**Q: I get an "Address already in use" error. What can I do?**

A: Another application is using one of the ports the tool needs. Check the [Ports Used by the Tool](#ports-used-by-the-tool) table and either close the conflicting application or change the port in `config.yaml`.

**Q: Can I use the tool with Twitch or YouTube?**

A: The tool is designed for TikTok Live. The license restricts commercial use on other platforms.

**Q: My Minecraft server is lagging. What can I do?**

A: Increase the RAM allocation (`Java.Xms` / `Java.Xmx` in `config.yaml`) if your system has enough memory. Reduce the frequency of expensive commands in `actions.mca`. Avoid using `comment` or `join` triggers with complex commands on busy streams.

---

## AI Prompt File

The file [`AIPrompt.md`](../AIPrompt.md) at the project root is a **system prompt template for AI-powered coding assistants** such as opencode, Cursor, GitHub Copilot, or Claude Projects.

### What it does

When loaded into a compatible AI assistant, this prompt instructs the AI to:

- Start in **English** by default, then **ask the user for their preferred language** during the first conversation.
- **Save the user's choice** by editing the `USER_LANGUAGE` field in `AIPrompt.md` itself.
- Follow strict **safety rules**: always read `GUIDE.md` first when unsure, never guess, and never proceed if required information is missing.
- Always **propose changes before editing files** and wait for explicit user confirmation.
- Only use information that is directly supported by the project files or documented comments — no invented facts.
- Treat event hooks as advanced and potentially error-prone.

### How to use it

1. Open your AI assistant's configuration or custom instructions settings.
2. Copy the entire contents of `AIPrompt.md`.
3. Paste it as the system prompt / custom instructions.
4. The assistant will now follow the rules defined in the prompt when working on this project.

### Who this is for

This file is intended for **developers and project maintainers** who use AI tools to help with this project. It ensures consistent, safe, and beginner-friendly behavior regardless of which AI assistant is being used.

---

## Additional Resources

- **Developer Documentation (English):** [docs/dev-book-en/src/Introduction.md](./dev-book-en/src/Introduction.md) or [online](https://technikley.github.io/Tiktok2Mc/en)
- **Developer Documentation (Deutsch):** [docs/dev-book-de/src/Introduction.md](./dev-book-de/src/Introduction.md) or [online](https://technikley.github.io/Tiktok2Mc/de)
- **Changelog:** [docs/CHANGELOG.md](./CHANGELOG.md)
- **GitHub Repository:** [https://github.com/TechnikLey/Tiktok2Mc](https://github.com/TechnikLey/Tiktok2Mc)
- **Report Issues:** [GitHub Issues](https://github.com/TechnikLey/Tiktok2Mc/issues)
- **TikTokLive Library:** [https://github.com/isaackogan/TikTokLive](https://github.com/isaackogan/TikTokLive)
- **AI Prompt File:** [AIPrompt.md](#ai-prompt-file) (see section above)
