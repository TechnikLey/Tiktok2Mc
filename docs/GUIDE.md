# TikTok2Mc — User Guide

Complete operational and usage documentation for TikTok2Mc v1.0.0.

> **Author:** TechnikLey — [GitHub](https://github.com/TechnikLey/Tiktok2Mc)
> **License:** PolyForm Noncommercial 1.0.0 (with creator exception)

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Folder Structure](#folder-structure)
- [Installation](#installation)
  - [Windows](#windows)
  - [Linux](#linux)
  - [From Source](#from-source)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Plugin System](#plugin-system)
  - [Plugin Lifecycle](#plugin-lifecycle)
  - [Built-in Plugins](#built-in-plugins)
  - [Plugin Manifests](#plugin-manifests)
  - [Creating Custom Plugins](#creating-custom-plugins)
- [API Usage](#api-usage)
  - [Health and Status](#health-and-status)
  - [Configuration](#configuration-api)
  - [Plugins](#plugins-api)
  - [Events](#events-api)
  - [Updates](#updates-api)
- [Actions and Triggers](#actions-and-triggers)
  - [Understanding actions.mca](#understanding-actionsmca)
  - [Trigger Types](#trigger-types)
  - [Command Types](#command-types)
  - [Chaining and Repeating](#chaining-and-repeating-commands)
  - [The $random Action](#the-random-action)
  - [Like Triggers](#like-triggers)
  - [Comment Commands](#comment-commands)
  - [Shell Actions](#shell-actions-shell_actionstxt)
- [Minecraft Server](#minecraft-server)
- [Update System](#update-system)
- [Runtime Behavior](#runtime-behavior)
- [Logging](#logging)
- [Troubleshooting](#troubleshooting)
- [Development](#development)
  - [Running Tests](#running-tests)
  - [Project Structure](#project-structure)
  - [Build Process](#build-process)
- [FAQ](#faq)
- [Additional Resources](#additional-resources)

---

## Architecture Overview

TikTok2Mc bridges TikTok Live events to a Minecraft server through a central API and plugin system.

```
┌─────────────────────────────────────────────────────────────┐
│                        start.py                              │
│  (Process orchestrator — launches all components)            │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐   │
│  │ TikTok Live  │    │  API Server  │    │  Minecraft   │   │
│  │  Connection  │───▶│  (FastAPI)   │◀──▶│   Server     │   │
│  │              │    │  :29185      │    │  :25565      │   │
│  └──────────────┘    └──────┬───────┘    └──────────────┘   │
│                             │                                │
│              ┌──────────────┼──────────────┐                │
│              │              │              │                 │
│        ┌─────▼─────┐ ┌─────▼─────┐ ┌─────▼─────┐          │
│        │  Plugin   │ │  Plugin   │ │  Plugin   │  ...      │
│        │  (Timer)  │ │ (Spotify) │ │ (Overlay) │          │
│        │  :29189   │ │  :29194   │ │  :29186   │          │
│        └───────────┘ └───────────┘ └───────────┘          │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**Key components:**

- **start.py** — Main launcher. Starts the API server, Minecraft server, and all enabled plugins. Handles updates, shutdown coordination, and process lifecycle.
- **API Server** — Central FastAPI backend on port 29185. Manages plugins, configuration, events, and updates through a REST interface.
- **TikTok Live Connection** — Connects to your active TikTok stream and receives events (gifts, follows, likes, comments, joins, shares).
- **Minecraft Server** — Bundled Vanilla server (1.21.11). Receives commands via RCON.
- **Plugins** — Independent modules that provide overlays, integrations, and game logic. Each runs on its own port and is discovered via `plugin.json` manifests.

---

## Folder Structure

```
Tiktok2Mc/
├── config/
│   └── config.yaml              # Main configuration file
├── data/
│   ├── actions.mca              # Action mappings (triggers → commands)
│   ├── shell_actions.txt        # Shell commands triggered by gifts
│   └── followed_users.txt       # Follow tracking (auto-generated)
├── defaults/
│   └── config.yaml              # Default configuration template
├── docs/
│   ├── GUIDE.md                 # This file
│   ├── CHANGELOG.md             # Release history
│   ├── ROADMAP.md               # Project roadmap
│   └── TODO.md                  # Development task list
├── logs/
│   └── update_logs/             # Update attempt logs
├── server/
│   └── mc/                      # Minecraft server directory
├── src/
│   ├── core/
│   │   ├── api/                 # FastAPI server, routes, models
│   │   ├── models.py            # Application data models
│   │   ├── paths.py             # Path resolution
│   │   └── utils.py             # Config loading, utilities
│   ├── plugins/                 # Plugin directories
│   │   ├── channelpoints/
│   │   ├── deathcounter/
│   │   ├── likegoal/
│   │   ├── overlaytxt/
│   │   ├── spotify/
│   │   ├── test/
│   │   ├── timer/
│   │   └── wincounter/
│   └── python/
│       ├── start.py             # Main launcher
│       └── update.py            # Auto-updater
├── tests/                       # Test suite
├── run.py                       # Standalone API server entry point
├── build.py                     # Build script
├── create_plugin.py             # Plugin scaffolding tool
└── requirements.txt             # Python dependencies
```

---

## Installation

### Windows

1. Download the latest release from [GitHub Releases](https://github.com/TechnikLey/Tiktok2Mc/releases).
2. Extract the ZIP archive to any folder.
3. Edit `config/config.yaml` — set your TikTok username and change the RCON password.
4. Run `start.exe`.

No manual Java installation is required — the bundled Java runtime is used automatically.

### Linux

1. Download the latest release.
2. Extract the archive.
3. Run `sudo ./start.bin` from the terminal.

The tool will detect your system Java or prompt you to install it if missing. Running with `sudo` is required for updates and permission-sensitive paths.

> You can disable the sudo warning by setting `show_sudo_warning: false` in `config.yaml`.

### From Source

```bash
git clone https://github.com/TechnikLey/Tiktok2Mc.git
cd Tiktok2Mc
python -m venv .venv
source .venv/bin/activate  # Linux
# .venv\Scripts\activate   # Windows
pip install -r requirements.txt
python run.py              # starts the API server on 127.0.0.1:29185
```

To run the full system (API + Minecraft server + plugins):

```bash
python src/python/start.py
```

---

## Quick Start

1. **Edit the configuration** — open `config/config.yaml` and change:
   ```yaml
   tiktok:
     user: your_tiktok_username   # without @
   rcon:
     password: ABC1234            # change to something secure
   ```

2. **Set up actions** — open `data/actions.mca` and define what happens when events occur. Example actions are included. See [Actions and Triggers](#actions-and-triggers) for the full syntax.

3. **Launch the tool**:
   - **Windows:** `start.exe`
   - **Linux:** `sudo ./start.bin`

4. **Join the Minecraft server** — open Minecraft Java Edition, go to Multiplayer, add server `localhost:25565`.

> You must be live on TikTok for the connection to work. The tool keeps trying to reconnect until your stream is live.

---

## Configuration

All settings are stored in `config/config.yaml`. Every option is documented with inline comments explaining its purpose, allowed values, and defaults.

**See inline comments inside `config.yaml` for detailed explanations of all configuration keys.**

### Key Configuration Sections

| Section | Purpose |
|---------|---------|
| `tiktok` | TikTok username, reconnection, follow tracking |
| `rcon` | Minecraft server communication (password, port) |
| `java` | Minecraft server RAM allocation and port |
| `comment_commands` | Viewer chat commands (prefixes, roles, cooldowns) |
| `random_triggers` | Control which triggers are eligible for `$random` |
| `console` | Visibility levels and console behavior |
| `shutdown` | Auto-shutdown after stream ends |
| `update` | Auto-updater settings |
| `theme` | Overlay colors for each plugin |
| Plugin sections | Individual plugin settings (`timer`, `death_counter`, `win_counter`, `like_goal`, `overlay_text`, `spotify`, `channel_points`) |

### Configuration Versioning

The `config_version` field uses semantic versioning (e.g., `1.0`). When you update the tool, the updater automatically migrates your configuration to the latest version while preserving your custom values. A backup is created before each migration.

### Security Warnings

The tool logs non-blocking warnings when:
- The default RCON password (`ABC1234`) is still configured
- `server_host` is set to `0.0.0.0` (exposes all services to the network)

These warnings appear in the console at startup and do not prevent the tool from running.

---

## Plugin System

Plugins are independent modules that provide overlays, integrations, and game logic. Each plugin runs on its own port and is discovered via `plugin.json` manifest files.

### Plugin Lifecycle

1. **Discovered** — The launcher scans `src/plugins/*/plugin.json` for manifest files.
2. **Registered** — Valid manifests are registered with the central API via `POST /api/v1/plugins/register`.
3. **Enabled** — Plugins are activated via `POST /api/v1/plugins/{name}/enable` or by setting `enabled: true` in configuration.
4. **Disabled** — Plugins are deactivated via `POST /api/v1/plugins/{name}/disable`.

All plugins start **disabled** by default (opt-in). Enable only what you need.

### Built-in Plugins

| Plugin | Port | Description | OBS URL |
|--------|------|-------------|---------|
| `timer` | 29189 | Stream countdown timer | `http://localhost:29189` |
| `death-counter` | 29190 | Player death counter | `http://localhost:29190` |
| `win-counter` | 29191 | Win/loss tracker | `http://localhost:29191` |
| `like-goal` | 29193 | Like milestone progress bar | `http://localhost:29193` |
| `overlay-text` | 29186 | Text notifications for OBS | `http://localhost:29186/?overlay=default` |
| `spotify-control` | 29194 | Spotify playback control and overlay | `http://localhost:29194` |
| `channel-points` | 29195 | Viewer loyalty points system | `http://localhost:29195` |
| `test` | — | Development test plugin | — |

### Plugin Manifests

Each plugin declares its identity in `plugin.json`:

```json
{
  "name": "timer",
  "version": "1.0.0",
  "entry_point": "src/plugins/timer/main.py",
  "display_name": "Stream Timer",
  "description": "Countdown timer for streams",
  "author": "TechnikLey",
  "ports": {
    "declared": [29189],
    "protocol": "tcp"
  },
  "update_url": "",
  "auto_enable": false
}
```

**Required fields:**
- `name` — Unique kebab-case identifier (e.g., `death-counter`)
- `version` — Semantic version (e.g., `1.0.0`)
- `entry_point` — Relative path to the plugin's entry script
- `display_name` — Human-readable name

**Optional fields:**
- `description`, `author`, `homepage` — Metadata
- `ports` — Declared port requirements
- `update_url` — URL for checking plugin updates (GitHub Releases API or direct)
- `auto_enable` — Suggested default enabled state (default: `false`)
- `capabilities` — Feature flags for event routing
- `depends_on` — Plugins that must be running first

### Creating Custom Plugins

Use the scaffolding tool:

```bash
python create_plugin.py
```

This creates a complete plugin folder with `plugin.json`, `config.yaml`, and `version.txt`. You'll be asked whether the plugin should be updatable via GitHub.

---

## API Usage

The central API server runs on `127.0.0.1:29185` and exposes a REST interface at `/api/v1`. Interactive documentation is available at `http://localhost:29185/docs` when the server is running.

### Health and Status

```bash
# Health check
curl http://localhost:29185/api/v1/health

# Detailed status (plugins, uptime, config)
curl http://localhost:29185/api/v1/status
```

### Configuration API

```bash
# Read current configuration
curl http://localhost:29185/api/v1/config

# Update configuration (with automatic backup)
curl -X PUT http://localhost:29185/api/v1/config \
  -H "Content-Type: application/json" \
  -d '{"config": {"tiktok": {"user": "new_username"}}, "backup": true}'
```

### Plugins API

```bash
# List all registered plugins
curl http://localhost:29185/api/v1/plugins

# Discover plugins from filesystem (read-only)
curl http://localhost:29185/api/v1/plugins/discover

# Enable a plugin
curl -X POST http://localhost:29185/api/v1/plugins/timer/enable

# Disable a plugin
curl -X POST http://localhost:29185/api/v1/plugins/timer/disable

# Check for plugin updates
curl http://localhost:29185/api/v1/plugins/updates
```

### Events API

```bash
# Inject an event into the event bus
curl -X POST http://localhost:29185/api/v1/events \
  -H "Content-Type: application/json" \
  -d '{"type": "custom.event", "data": {"key": "value"}}'

# Server-Sent Events stream (connect with EventSource)
# GET http://localhost:29185/api/v1/events/stream?types=log,status
```

### Updates API

```bash
# Check for tool updates
curl http://localhost:29185/api/v1/updates/check
```

Returns:
```json
{
  "current_version": "1.0.0",
  "latest_version": "1.0.1",
  "update_available": true,
  "release_url": "https://github.com/TechnikLey/Tiktok2Mc/releases/tag/v1.0.1",
  "published_at": "2026-06-01T00:00:00Z",
  "error": null
}
```

---

## Actions and Triggers

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

**Examples:**

```
follow:/give @a minecraft:golden_apple 7
5655:!tnt 2 0.1 2 Notch
16071:$random
comment:>>{user} wrote:|{comment}|3
```

Lines starting with `#` are treated as comments and ignored.

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

> The `comment` and `join` triggers fire for **every** event. On active streams this can be very frequent. Avoid complex or expensive commands here to prevent overwhelming your server.

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

> Do not write vanilla Minecraft commands with `!`. Doing so may cause the server to crash or freeze.

#### `$` — Special Actions

Special built-in or script actions.

- **`$random`** — Picks and executes a random action from the available trigger pool.
- **Custom `$` commands** — Defined via Event Hooks.

#### `>>` — Overlay Text

Sends a text notification to the stream overlay.

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

### The $random Action

The `$random` command picks a random eligible trigger from your defined actions and executes it.

```
16071:$random
```

You can control which triggers are eligible using the `random_triggers` section in `config.yaml`. Use `mode: deny-all` to allow only the listed triggers, or `mode: allow-all` to allow all triggers except those listed.

> Triggers that contain `$random` are automatically excluded to prevent infinite recursion.

### Like Triggers

Like triggers fire when the total number of likes reaches a configured threshold. They are defined in two places that work together:

- **`config.yaml`** — under `like_goal.triggers`, you define the interval (every N likes), the trigger name, and whether it is enabled.
- **`actions.mca`** — you add a line using the trigger name from the config to specify which command to run.

See inline comments in `config.yaml` for the full configuration options and examples.

### Comment Commands

The `comment_commands` feature lets viewers send commands via TikTok chat. Viewers type a prefix (e.g., `#` or `$`) followed by a command, and the tool forwards it to Minecraft (via RCON) or to an HTTP endpoint (for plugins like Spotify).

Commands are organized into **groups** — each with its own prefix, role requirements, allowed commands list, and optional cooldowns.

**Example:** A moderator writes `#say Hello` → the command `say Hello` is sent to the Minecraft server via RCON.

> Some prefix characters like `!` may not work reliably in all streaming software. The `#` character is recommended for reliable operation.

All settings are configured in `config.yaml` under `comment_commands` — the file has detailed inline comments explaining every option.

### Shell Actions (shell_actions.txt)

The file `data/shell_actions.txt` runs shell commands on your computer when a gift is received.

**Format:**

```
GiftID:ShellCommand
```

**Example:**

```
18508:curl -X POST http://localhost:29191/add?amount=10
16071:curl -X POST http://localhost:29191/remove?amount=10
```

**Important notes:**
- HTTP actions are **gift-only** — not supported for `follow`, `join`, `comment`, or like triggers.
- Both `actions.mca` and `shell_actions.txt` are checked for every gift. If the same gift ID appears in both, **both run independently**.
- Lines starting with `#` are comments.
- Lines starting with `//define name = value` define variables that are replaced in all following commands with `{name}`.

---

## Minecraft Server

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

> Port forwarding varies by router model. Search "[your router model] port forwarding" for specific instructions.

### Server Details

| Setting | Default |
|---------|---------|
| Minecraft version | 1.21.11 (Vanilla) |
| Java | OpenJDK 21 (bundled on Windows) |
| RAM | 4 GB (configurable via `java.xms` / `java.xmx` in `config.yaml`) |
| Minecraft port | 25565 |
| RCON port | 25575 |
| Server directory | `server/mc/` |
| Server plugins | MinecraftServerAPI, DelayedTNT |

### Replacing the Server Version

1. Go to the `server/mc/` folder.
2. Note the **filename** of the current `.jar` file.
3. Replace it with your new server `.jar` file (Forge, Fabric, Paper, etc.).
4. **Rename** the new file to match the original filename exactly.

> Your replacement server must support RCON and datapacks (available in almost all Minecraft versions from 1.1 onward and 1.13 onward respectively).

---

## Update System

The tool can update itself automatically (enabled by default). On startup it checks for new versions and installs updates.

### How Updates Work

1. **Version check** — The updater queries the GitHub Releases API for the latest release.
2. **Download** — If a newer version is available, the update package is downloaded and extracted.
3. **Signal** — The updater signals the main process to shut down (via file and API).
4. **Install** — Files are copied according to a whitelist (core, config, plugins, scripts).
5. **Migrate** — Configuration is automatically migrated to the latest version with a backup.

### Plugin Updates

Plugins with an `update_url` in their manifest are checked for updates via `GET /api/v1/plugins/updates`. The tool supports:
- GitHub Releases API (`https://api.github.com/repos/...`)
- Direct download URLs with a `version` query parameter

### Disabling Auto-Updates

Set `update.enabled: false` in `config.yaml` to disable automatic updates.

---

## Runtime Behavior

### Startup Sequence

When you launch the tool:

1. **Configuration loaded** — `config/config.yaml` is read and validated.
2. **Security warnings** — Non-blocking warnings for default RCON password and network exposure.
3. **Updater runs** — Checks for new versions (if enabled).
4. **API server starts** — FastAPI server starts on `127.0.0.1:29185`.
5. **Plugin discovery** — Manifests are scanned and registered with the API.
6. **Plugin updates checked** — All registered plugins are checked for updates.
7. **Minecraft server starts** — Bundled server launches.
8. **Plugins start** — Enabled plugins are launched in separate processes.
9. **TikTok connection** — Connects to your active TikTok Live stream.

### Shutdown

- Type `exit` in the console to stop all programs and shut down cleanly.
- Type `stop` to cancel an active shutdown countdown.
- Auto-shutdown can be configured to trigger when the stream ends (see `shutdown` section in `config.yaml`).

### Console Commands

| Command | Description |
|---------|-------------|
| `exit` | Stop all programs and close |
| `stop` | Cancel active shutdown countdown |
| `help` | Show available commands |

---

## Logging

The tool creates several log files during operation:

| File | Purpose |
|------|---------|
| `logs/update_logs/updater_*.log` | Update check logs — one file per update attempt |
| `data/revenue_log.jsonl` | Gift revenue tracking — **gross estimate** (diamonds × 0.005 USD) |
| `data/window_state_*.json` | Window size/position for plugin overlays |

**Cleaning up:** Old update logs are automatically removed based on `max_update_logs` in `config.yaml` (default keeps recent ones, deletes older). Revenue logs and window state files are safe to delete manually if you want a fresh start.

---

## Troubleshooting

### Common Issues

**"Address already in use" error**
Another application is using one of the ports the tool needs. Check the [Ports Used by the Tool](#ports-used-by-the-tool) table and either close the conflicting application or change the port in `config.yaml`.

**TikTok connection fails**
You must be live on TikTok for the connection to work. The tool will keep trying to reconnect automatically. Check your username in `config.yaml` (without the `@` symbol).

**Minecraft server won't start**
Check that Java is installed. On Windows, the bundled Java runtime is used automatically. On Linux, the tool will detect or prompt you to install Java.

**Plugin not starting**
Ensure the plugin is enabled in `config.yaml` or via the API (`POST /api/v1/plugins/{name}/enable`). Check that the plugin's `plugin.json` manifest is valid.

**Config migration fails**
A backup is created before each migration at `config/config.yaml.bak`. If migration fails, restore from the backup and check the error message in the console.

### Ports Used by the Tool

| Port | Used For |
|------|----------|
| 25565 | Minecraft Server |
| 25575 | RCON (Server Communication) |
| 29185 | API Server |
| 29186 | Overlay Text |
| 29187 | Minecraft Server API |
| 29188 | Internal Web Server |
| 29189 | Stream Timer Overlay |
| 29190 | Death Counter Overlay |
| 29191 | Win Counter Overlay |
| 29193 | Like Goal Overlay |
| 29194 | Spotify Control |
| 29195 | Channel Points |

Under normal circumstances, you do not need to change any ports. Only change a port if you get an "Address already in use" error.

---

## Development

### Running Tests

```bash
pip install -r requirements.txt
pytest
```

The test suite includes 285 tests covering:
- API endpoints (health, config, plugins, events, discovery, updates)
- Plugin system (manifests, registration, enable/disable)
- Configuration (validation, versioning, backups)
- Update checker (GitHub API, version parsing)
- Event bus (SSE, WebSocket)
- Smoke tests (filesystem structure, manifest content)

4 tests are skipped (SSE/WebSocket integration — TestClient limitation).

### Project Structure

```
src/
  core/
    api/              # FastAPI server, routes, models, registry
      routes/         # API route handlers
      services/       # Business logic (config, plugin discovery)
    models.py         # Application data models
    paths.py          # Path resolution
    utils.py          # Config loading, version normalization
  plugins/            # Plugin directories (each with plugin.json)
  python/             # start.py, update.py (compiled entry points)
tests/
  test_api/           # API integration tests
  test_core/          # Core unit tests
defaults/
  config.yaml         # Default configuration template
```

### Build Process

The build script compiles the Python source into standalone executables:

```bash
python build.py
```

This creates release packages for Windows (`.zip`) and Linux (`.tar.gz`) with all necessary files.

---

## FAQ

**Q: Do I need to be live on TikTok for the tool to work?**

A: Yes. The tool connects to your active TikTok Live stream. It will keep retrying until you go live.

**Q: Can I test actions without going live?**

A: Yes. Use the included test tool (`test/test_trigger.exe` on Windows or `test/test_trigger.bin` on Linux).

**Q: How do I know if the tool is working correctly?**

A: The main console window shows live log output. If you see "Connected to TikTok" and the Minecraft server starts without errors, everything is running.

**Q: How often is the tool updated?**

A: There is no fixed schedule. Updates are published when new features, bug fixes, or compatibility improvements are ready.

**Q: Can I use a different Minecraft version?**

A: Yes. Replace the server `.jar` file in `server/mc/`. The replacement must support RCON and datapacks.

**Q: Can I use modded servers (Forge, Fabric, Paper)?**

A: Yes. Replace the server `.jar` as described above. Ensure the modded server supports RCON and datapacks.

**Q: Does the tool work with Minecraft Bedrock Edition?**

A: No. The tool is designed for Minecraft Java Edition. Bedrock Edition does not support datapacks or RCON in the same way.

**Q: Can the Minecraft server run on a different computer?**

A: Yes. You can run the Minecraft server on a separate machine and point the tool to it. Set the RCON IP and port in `config.yaml` to match your remote server.

**Q: Can I use the overlays without OBS?**

A: Yes. The overlays are standard web pages served on localhost ports. You can open them in any browser or add them as Browser Sources in any streaming software that supports that feature.

**Q: How do I find gift IDs?**

A: Open `core/gifts.json` in a text editor. Each gift entry has an `id` field.

**Q: Can I use the tool with Twitch or YouTube?**

A: The tool is designed for TikTok Live. The license restricts commercial use on other platforms.

---

## Additional Resources

- **README:** [README.md](../README.md)
- **Changelog:** [CHANGELOG.md](./CHANGELOG.md)
- **Roadmap:** [ROADMAP.md](./ROADMAP.md)
- **GitHub Repository:** [https://github.com/TechnikLey/Tiktok2Mc](https://github.com/TechnikLey/Tiktok2Mc)
- **Report Issues:** [GitHub Issues](https://github.com/TechnikLey/Tiktok2Mc/issues)
- **TikTokLive Library:** [https://github.com/isaackogan/TikTokLive](https://github.com/isaackogan/TikTokLive)
- **Developer Documentation (English):** [online](https://technikley.github.io/Tiktok2Mc/en)
- **Developer Documentation (Deutsch):** [online](https://technikley.github.io/Tiktok2Mc/de)
