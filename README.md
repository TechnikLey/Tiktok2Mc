# TikTok2Mc

Connect your TikTok Live stream to a Minecraft server. When viewers send gifts, follow, or hit like milestones, Minecraft commands are triggered in real-time.

TikTok2Mc bundles a Minecraft server, a central API, and a plugin system that lets you enable only the features you need. Each plugin runs independently — turning on the Timer will not accidentally trigger the Death Counter.

> **v1.0.0 is a clean break.** Config files, plugins, and data from versions 0.x are not compatible. This is intentional.

## Features

- **Real-time TikTok Live connection** via [TikTokLive](https://github.com/isaackogan/TikTokLive) — follows, likes, shares, gifts, comments, joins
- **Customizable action mappings** — map any event to Minecraft commands in `data/actions.mca`
- **Central API server** — one FastAPI backend manages plugins, configuration, events, and updates
- **Manifest-driven plugin system** — 8 built-in plugins, each with its own `plugin.json`, enabled or disabled individually
- **Built-in overlays for OBS** — Death Counter, Win Counter, Like Goal, Stream Timer, Overlay Text, Spotify, Channel Points
- **Comment commands** — let viewers send Minecraft commands or control Spotify via TikTok chat with role-based access
- **Auto-updater** — checks for new versions on startup, installs updates automatically
- **Security warnings** — alerts you if the default RCON password is still set or if services are exposed to the network
- **Config backups** — automatic backups before every config change
- **285 automated tests** — run on every commit via GitHub Actions

## System Requirements

| Requirement | Details |
|-------------|---------|
| **OS** | Windows 10+ or Linux |
| **RAM** | 12 GB minimum recommended (Minecraft server uses up to 4 GB by default) |
| **Python** | 3.10+ (for development; release builds include a bundled runtime) |
| **TikTok** | Active TikTok Live stream required for event connection |
| **Minecraft** | Java Edition 1.13+ (datapacks and RCON support required) |

## Installation

### From release (recommended)

1. Download the latest release from [GitHub Releases](https://github.com/TechnikLey/Tiktok2Mc/releases).
2. Extract the archive to any folder.
3. Edit `config/config.yaml` — set your TikTok username and change the RCON password.
4. Run `start.exe` (Windows) or `sudo ./start.bin` (Linux).

### From source (development)

```bash
git clone https://github.com/TechnikLey/Tiktok2Mc.git
cd Tiktok2Mc
python -m venv .venv
source .venv/bin/activate  # Linux
# .venv\Scripts\activate   # Windows
pip install -r requirements.txt
python run.py              # starts the API server on 127.0.0.1:29185
```

## Quick Start

1. **Edit the configuration** — open `config/config.yaml` and change:
   ```yaml
   tiktok:
     user: your_tiktok_username   # without @
   rcon:
     password: ABC1234            # change to something secure
   ```

2. **Set up actions** — open `data/actions.mca` and define what happens when events occur. Example actions are included. See the [User Guide](./docs/GUIDE.md) for the full syntax.

3. **Launch the tool**:
   - **Windows:** `start.exe`
   - **Linux:** `sudo ./start.bin`

4. **Join the Minecraft server** — open Minecraft Java Edition, go to Multiplayer, add server `localhost:25565`.

> You must be live on TikTok for the connection to work. The tool keeps trying to reconnect until your stream is live.

## Configuration

All settings are in `config/config.yaml`. Every option is documented with inline comments explaining its purpose, allowed values, and defaults.

For detailed explanations of all configuration sections, see the [User Guide](./docs/GUIDE.md).

## API Overview

The central API server runs on `127.0.0.1:29185` and exposes a REST interface at `/api/v1`. Interactive documentation is available at `http://localhost:29185/docs` when the server is running.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Server health check |
| `/status` | GET | Detailed server status (plugins, uptime, config) |
| `/config` | GET / PUT | Read or update the main configuration |
| `/plugins` | GET | List all registered plugins |
| `/plugins/register` | POST | Register a new plugin |
| `/plugins/{name}` | GET / PUT / DELETE | Get, update, or remove a plugin |
| `/plugins/{name}/enable` | POST | Enable a plugin |
| `/plugins/{name}/disable` | POST | Disable a plugin |
| `/plugins/updates` | GET | Check all plugins for available updates |
| `/plugins/discover` | GET | Scan filesystem for plugin manifests (read-only) |
| `/updates/check` | GET | Check the main repo for a newer tool release |
| `/updater/signal` | GET / PUT / DELETE | Update coordination signal |
| `/events` | POST | Inject an event into the event bus |
| `/events/stream` | GET | Server-Sent Events stream |
| `/ws` | WebSocket | Bidirectional event stream |

## Plugin System

Plugins are discovered from `plugin.json` manifest files in `src/plugins/*/`. Each manifest declares the plugin's name, version, entry point, ports, and capabilities.

**Plugin lifecycle:**

1. **Discovered** — manifest file found on filesystem
2. **Registered** — registered with the central API via `POST /plugins/register`
3. **Enabled** — activated via `POST /plugins/{name}/enable`
4. **Disabled** — deactivated via `POST /plugins/{name}/disable`

All plugins start disabled by default (opt-in). Enable only what you need.

**Built-in plugins:**

| Plugin | Port | Description |
|--------|------|-------------|
| `timer` | 29189 | Stream countdown timer |
| `death-counter` | 29190 | Player death counter |
| `win-counter` | 29191 | Win/loss tracker |
| `like-goal` | 29193 | Like milestone progress bar |
| `overlay-text` | 29186 | Text notifications for OBS |
| `spotify-control` | 29194 | Spotify playback control and overlay |
| `channel-points` | 29195 | Viewer loyalty points system |
| `test` | — | Development test plugin |

## Development

### Running tests

```bash
pip install -r requirements.txt
pytest
```

The test suite includes 285 tests covering the API, plugin system, configuration, update checker, manifest validation, and smoke tests. 4 tests are skipped (SSE/WebSocket integration — TestClient limitation).

### Project structure

```
src/
  core/
    api/              # FastAPI server, routes, models, registry
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
docs/
  GUIDE.md            # User guide
  CHANGELOG.md        # Release history
  ROADMAP.md          # Project roadmap
  TODO.md             # Development task list
```

## Documentation

- **[User Guide](./docs/GUIDE.md)** — complete usage documentation, configuration reference, plugin setup, troubleshooting
- **[Changelog](./docs/CHANGELOG.md)** — release history and what changed in each version
- **[Roadmap](./docs/ROADMAP.md)** — current progress and what comes next
- **Developer Documentation** — [English](https://technikley.github.io/Tiktok2Mc/en) / [Deutsch](https://technikley.github.io/Tiktok2Mc/de)

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

## Contributing

Issues and pull requests are welcome. Before contributing:

- Open an issue to discuss significant changes
- Ensure all tests pass (`pytest`)
- Follow the existing code style
- Update documentation if behavior changes

## Contact

- **GitHub:** [Open an Issue](https://github.com/TechnikLey/Tiktok2Mc/issues)
- **Profile:** [TechnikLey on GitHub](https://github.com/TechnikLey)
