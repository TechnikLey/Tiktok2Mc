# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

Each version is split into two sections:

- **User** — changes relevant to end users (new features, bug fixes, behavior changes).
- **Developer** — internal/technical changes relevant to contributors and developers (build system, code structure, tooling).

---

## [Unreleased]

### User

#### Added
- **Named overlays (`@Name>>`)** — You can now run multiple overlay windows simultaneously and route messages to specific ones. Define overlay names in `config.yaml` under `Overlaytxt > Overlays` and use `@Name>>` instead of `>>` in `actions.mca` to target a specific window. Writing `>>` without a name still targets the `default` overlay automatically.
- **random_included config options** — The `$random` command now respects one new list in `config.yaml` under `Gifts`: `random_included` (whitelist). This allows you to precisely control which triggers are eligible for random selection.
- **`docs` folder** - The entire `docs` folder is now included, so you can access all documentation files (like this changelog) directly from the release without needing to visit GitHub.
- **Triggers Names** - Now you can use trigger names instead of just trigger numbers in the `actions.mca` file.
- **Add New Chapter to GUID.md** - Added a new chapter to the GUIDE.md about using trigger names or IDs in the `actions.mca` file, including priority rules and handling names with spaces. 
- **New Trigger** - Added a new trigger type `share` that fires when a viewer shares the live stream.
- **Track Income from Streaming** - The application now tracks the income based on received gifts and their USD value. This Informations is stored in the `revenue_log.jsonl` file and can be used for analytics.
- **Config value for Autosave** - Added a new config value `autosave_interval_seconds` to control how ofte the `revenue_log.jsonl` file is saved to disk, allowing for more frequent updates and better data integrity in case of crashes. Default is set to `60` seconds.
- **Auto shutdown on live end** - The application now automatically shuts down when the live stream ends
- **Configurable shutdown behavior** – The automatic shutdown after a live session can now be controlled via configuration. Users can define a custom shutdown delay or disable automatic shutdown entirely, allowing time for final statistics review or post-live processing before manually terminating the system.
- **Configurable network access (`server_host`)** — All web servers (main GUI, plugins, overlay, etc.) can now be made accessible from other devices in your network by setting `server_host: "0.0.0.0"` in your `config.yaml`. This allows you to use overlays and APIs from other PCs or OBS instances.

#### Fixed
- **Comment** – Fixed an issue where comments sent before establishing the connection were displayed immediately after joining a live stream. The application now temporarily filters out these earlier messages, ensuring that only new chat activity is shown.
- **Config Comment** - Fixed a Comment for the Prefix option in the `CommentCommands` section of the `config.yaml` file.

#### Changed
- **Edit actions.mca examples** — Commented out the `join` trigger because it can spam the overlay with many messages.
- **Edit default config values** - Updated `GoalMultiplier` default from `2` to `1` to prevent overwhelming growth of goal-based triggers for new users.
- **Edit default config values** - Add `join` and `comment` to the default `random_exclude` list for `$random`-Command
- **Update random_excluded list function** - The function of the `random_exclude` list has been changed to work better with the new `random_included` list.
- **Edit GUIDE.md** - Updated the `$random` section to reflect the new configurable inclusion list and added a note about automatic exclusion of triggers containing `$random` to prevent recursion.
- **VS Code extension** - Updated `mca.vsix` to include the new `''` syntax for trigger names with a with space between the leeters.
- **GUIDE.md** - Added the new trigger `share` to the list of available triggers.
- **Edit actions.mca examples** - Rewrite some Comments and Commands examples to be more clear and concise.

### Developer

#### Added
- **Named overlay routing (`main.py`)** — The `>>` parser now extracts an optional `@Name` prefix. The overlay name is stored alongside the body and forwarded to `send_overlay_text()` as the `overlay_name` parameter. Without a name, `"default"` is used automatically.
- **`@Name>>` validator support (`validator.py`, `server.js`)** — The `.mca` validator and the VS Code language server both recognise `@Name>>` as a valid command prefix. No error is raised for this syntax.
- **`@Name>>` syntax highlighting (`mca.tmLanguage.json`)** — The `@Name` part is coloured distinctly (entity type colour) and the `>>` operator is highlighted separately to visually distinguish named overlays from plain `>>`.
- **Exclude files/folder from build (`build.py`)** — The `sync_folder()` function now accepts an `exclude` parameter with glob patterns to specify files or folders that should be ignored during the build process.

#### Fixed
- **$random logic:** - Resolved an issue where an empty action list would trigger a misleading `[HOOK] [WARN] Unknown script action: 'random'` error.

#### Changed
- **Config version** - bumped from `3` to `4`
- **Edit main.py** - Refactored the `$random` trigger selection logic to first apply the new `random_included` whitelist and then the `random_exclude` blacklist, ensuring that only explicitly allowed triggers are considered for random selection.
- **Unified host configuration** — All Flask servers and plugin APIs now consistently read the server_host value from config.yaml for their bind address, but internal URLs and webview windows are hardcoded to 127.0.0.1 to avoid cross-device issues.

#### Docs
- **Dev-Book `ch03-06`** - Added a NOTE block and updated the example to recommend importing `HookAPI` for better IntelliSense and docstrings in editors.

---

## [0.2.0] - 2026-04-13

### User

#### Added
- **Linux support** — the tool now runs on Linux in addition to Windows.
- **Terminal isolation** — each process runs in its own terminal session on Linux for better overview.
- **Interactive setup** — on first Linux launch, choose to install tmux/screen, continue without, or abort.
- **Configurable exclusions** — `$random` exclusion list is now configurable in `config.yaml` under `Gifts > random_exclude` instead of being fixed in the program.
- **`comment` trigger** — fires every time a viewer writes a comment in the live chat.
- **`join` trigger** — fires every time a viewer joins the live stream.
- **CommentCommands** — config option that lets viewers send Minecraft commands via chat comments. Configurable prefix, role restrictions (`all`, `moderator`, `superfan`, `fanclub`), whitelist, and blacklist.
- **VS Code extension** — `mca.vsix` adds syntax highlighting and error checking for `.mca` files in VS Code.
- **Overlay Validation** — give error if you use `{comment}` in overlay text for triggers other than `comment` (prevents mistakes).

#### Fixed
- **Overlay background** — now shows a transparent background when opened via browser URL instead of a green screen.
- **Auto-updater** — no longer falsely reports "Update has been installed" when no update was available.
- **Plugin releases** — now always include the plugin's `version.txt` and `README.md` if present, so users get all plugin info in the release folder.

#### Changed
- **Documentation (`README` / `GUIDE.md`)** — updated to reflect Linux support, platform-specific start commands, and Java availability per OS.
- **`data/actions.mca`** — rewritten with fewer examples, clear comments explaining each line, and a compact header summarizing the format.
- **`GUIDE.md`** — documented `comment` and `join` triggers, `CommentCommands` config options, and updated `http_actions.txt` section.

### Developer

#### Added
- **Cross-platform build script** — `build.py` replaces `build.ps1`, with parallel compilation via `ThreadPoolExecutor` and hash-based build caching.
- **Plugin scaffolding** — `create_plugin.py` replaces `create_plugin.ps1` for cross-platform support.
- **Release automation** — `upload.py` script for git tag & push to trigger CI/CD releases.
- **CI/CD workflow** — `.github/workflows/build.yml` for dual-platform (Windows + Linux), triggered by `v*` tags, produces `.zip` and `.tar.gz` release artifacts.
- **Shebangs** — `#!/usr/bin/env python3` added to all Python source files.
- **Dependencies** — `requirements.txt` added `PyQt6`, `PyQt6-WebEngine`, and `qtpy` to support the pywebview Qt backend.
- **`on_join` event handler** — added to `main.py`.
- **`CommentCommands` implementation (`main.py`)** — prefix and role check (moderator, superfan, fanclub), whitelist/blacklist filtering, direct RCON forwarding.
- **User status extraction (`main.py`)** — added to `on_comment` (moderator, superfan, fanclub via `fan_ticket_count`/`fans_club`/`fans_club_info`).
- **Trigger validation (`Validator.py`)** — `{comment}` in overlay text now only allowed for the `comment` trigger, otherwise outputs an error.

#### Changed
- **`README.md`** — updated OS requirements (Linux now supported), platform-specific start command, Java availability note for Linux.
- **`GUIDE.md`** — updated Java section (not bundled on Linux), platform-specific paths for `start` and `test_trigger` executables.
- **Linux session management (`start.py`)** — tmux/screen session management on Linux with interactive installer prompt if neither is found. Processes tracked by session name, listed with attach commands after startup.
- **Platform specific guards (`start.py`)** — `subprocess.CREATE_NEW_CONSOLE` and `taskkill` calls guarded by `sys.platform == "win32"` checks.
- **GUI compatibility (`start.py`)** — display environment variables (`DISPLAY`, `WAYLAND_DISPLAY`, `XDG_RUNTIME_DIR`) forwarded to tmux/screen sessions so GUI apps (pywebview) work.
- **Updater execution (`start.py`)** — updater runs synchronously without tmux/screen to preserve exit code handling.
- **Java Auto-discovery (`server.py`)** — via bundled path, then system `PATH`, then automatic install through detected package manager (apt/dnf/pacman/zypper).
- **Plugin discovery (`registry.py`)** — uses execute-permission checks on Linux instead of `.exe` file extension matching.
- **Dynamic extensions (`paths.py`)** — `EXE_SUFFIX` variable replaces all hardcoded `.exe` references.
- **Platform agnostic paths (`update.py`)** — whitelist and binary paths use dynamic `EXE`/`BIN` suffixes per platform.
- **Non-interactive updater (`update.py`)** — `--auto` flag for non-interactive mode when launched by `start.py` (skips all `input()` prompts).
- **Server binary naming** — uses `.bin` suffix on Linux to avoid name collision with system commands.
- **`config.yaml`** — added `CommentCommands` section (Enable, Prefix, AllowedRoles, Whitelist, Blacklist).

#### Fixed
- **PyInstaller logs** — build errors (stdout + stderr) are now captured and displayed on failure instead of being silenced.
- **Updater exit codes** — exit code `0` (no update) was not handled, causing false "Update installed" message in `start.py`.
- **Plugin artifacts** — the build script now copies `version.txt` and `README.md` from each plugin folder (if present) into the release, so plugin metadata and documentation are always included.

#### Docs
- **Dev-Book `ch03`** — documentation across all `ch03` chapters rewritten to be generic; prefixes are no longer hardcoded in multiple places but reference one authoritative list in `ch03-02`.
- **Dev-Book `ch03-02`** — added missing `>>` (Overlay) type to the "Command Types Explained" section.
- **Dev-Book `ch03-05`** — updated `$random` documentation to reflect configurable exclusion list via `config.yaml`.
- **`defaults/actions.mca`** — reduced from 23 to 8 representative examples covering all prefixes (`/`, `!`, `$`, `>>`), with inline comments explaining each action.
- **`GUIDE.md`** — `$random` section updated with `random_exclude` config example.