# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

Each version is split into two sections:

- **User** — changes relevant to end users (new features, bug fixes, behavior changes).
- **Developer** — internal/technical changes relevant to contributors and developers (build system, code structure, tooling).

> [!IMPORTANT]
> Please note that the **Developer** category starting after version `v0.3.0` is now deprecated and will no longer be maintained. Internal technical changes will continue to be documented in commit messages and the `dev-book`. Please use GitHub to review changes by checking the commits and viewing the diffs to see exactly what has been modified.

---

## [Unreleased]

### User

#### Added
* **Config Option: `max_update_logs`** — A new configuration option under the `Updater` section in `config.yaml` that allows users to specify how many update log files to keep in the `logs/update_logs` directory.

#### Changed
* **Updater Logging (Linux)** — The updater now creates a new log file for each update attempt in the `logs/update_logs` directory, named with a timestamp in 24-hour format (e.g., `updater_2026-04-19_14-30.log`). This allows users to keep a history of update attempts and their outcomes without overwriting previous logs.
* **Documentation rewrite** — The user guide (`docs/GUIDE.md`) has been completely rewritten as `docs/rework_temp.md` with improved structure, readability, and beginner-friendliness. All configuration explanations outside the Quick Start section have been replaced with references to `config.yaml`.
* **Improved config template** — A new annotated config template (`docs/config_explanatory.yaml`) with enhanced inline comments and a quick-start checklist has been added.
* **AI Prompt documentation** — The `AIPrompt.md` file is now referenced in the user guide under Additional Resources.

#### Fixed
* **Revenue logging shows wrong daily values** — Fixed a bug where the daily revenue log (`revenue_log.jsonl`) showed the **cumulative** earnings since bot start instead of only the current day's revenue. The bot now correctly resets its baseline at the start of each calendar day.
* **Webhook server ignored `server_host` setting** — The internal webhook server (for MinecraftServerAPI events) now respects the `server_host` configuration. Previously it always bound to `127.0.0.1`, even when `server_host` was set to `0.0.0.0`.
* **Startup crash when config is broken** — The bot now properly stops if the configuration file cannot be loaded, instead of continuing with invalid settings and failing silently later.
* **Updater EOFError** - Fixed an issue where the updater could raise an `EOFERROR` when no input is available (In most cases only on Linux) during the update process. The updater now catches this exception and prints an informational message instead of crashing.
* **Overlay `>>` command not working** — Fixed a bug where the `>>` overlay command (without `@Name`) used the wrong fallback name (`"defaults"` instead of `"default"`), causing overlay text to silently fail.
* **default overlay not available after removing from config** — Fixed a bug where removing the `default` overlay from `config.yaml` caused the `>>` command to stop working. A fallback `default` overlay is now always created internally.
* **Gift revenue counter not updating** — Fixed a bug where the gift revenue counter never actually ran. It now works and updates correctly.
* **Deathcounter port configuration ignored** — The deathcounter plugin now correctly reads the configured port from `config.yaml`. Previously a custom port setting was silently ignored.
* **Overlay text without overlay name** — Overlay text commands now work reliably even when no specific overlay name is provided.
* **Missing error messages in plugins** — Errors when loading or saving plugin data (window sizes, stats) are now shown in the console instead of being silently ignored.
* **Missing error messages for RCON connection** — Connection issues to the Minecraft server are now shown in the console, making it easier to spot problems.
* **Wrong Linux command in README** — Fixed the startup command in the quick-start guide (`./start` → `./start.bin`).

---

## [v0.3.0] - 2026-04-18

### User

> [!WARNING]
> When updating your project to this version, errors may occur.
> If you encounter problems, please download the latest release and copy your `data` folder (and any > other important files like `config.yaml`) into the new release directory.

#### Added
* **Named Overlays (`@Name>>`)** — You can now run multiple overlay windows simultaneously and route messages to specific ones. Define names in `config.yaml` under `Overlaytxt > Overlays` and use `@Name>>` in `actions.mca` to target a window. Using `>>` without a name still targets the `default` overlay.
* **`random_included` configuration** — A new whitelist in `config.yaml` under `Gifts` that allows you to precisely control which triggers are eligible for selection by the `$random` command.
* **Release Documentation** — The entire `docs` folder is now included in the release, allowing you to access all documentation files and changelogs directly without visiting GitHub.
* **Trigger Names** — You can now use descriptive trigger names instead of just trigger numbers within the `actions.mca` file for better readability.
* **Share Trigger** — Added a new trigger type `share` that fires whenever a viewer shares the live stream.
* **Streaming Income Tracking** — The application now tracks income based on received gifts and their USD value. This data is stored in `revenue_log.jsonl` and can be used for analytics.
* **Autosave for Revenue Logs** — Added `autosave_interval_seconds` to the config to control how often revenue data is saved to disk (default is `60` seconds), ensuring data integrity in case of crashes.
* **Automatic Shutdown** — The application can now automatically shut down when the live stream ends.
* **Configurable Shutdown Behavior** — You can now define a custom shutdown delay or disable the automatic shutdown entirely via the configuration settings to allow for post-live processing.
* **Network Access (`server_host`)** — Web servers (GUI, plugins, overlays) can now be made accessible from other devices in your network by setting `server_host: "0.0.0.0"` in `config.yaml`. This is useful for using overlays on separate PCs or OBS instances.
* **Enhanced Configuration Info** — Added additional explanatory info to the `config.yaml` file to prevent errors caused by misinterpreting list key values.
* **New Guide Chapters** — Updated `GUIDE.md` with a new chapter on using trigger names/IDs, priority rules, and handling names that contain spaces.
* **Config Option: `no_sudo_warning`** — New config key to suppress the warning about missing sudo/root privileges on Linux systems.

#### Changed
* **GoalMultiplier Default** — Updated the default `GoalMultiplier` from `2` to `1` to prevent overwhelming growth of goal-based triggers for new users.
* **Random Command Defaults** — Added `join` and `comment` to the default `random_exclude` list for the `$random` command to reduce spam.
* **Random List Logic** — Updated the logic of the `random_exclude` list to work more effectively alongside the new `random_included` whitelist.
* **Example Actions** — Commented out the `join` trigger in the `actions.mca` examples to prevent overlay spam. Rewrote various command examples to be more concise.
* **VS Code Extension** — Updated the `mca.vsix` extension to support the new `''` syntax for trigger names that contain spaces.
* **Updater Error Reporting** — The updater now provides more specific error messages for YAML parsing, including the exact filename and line number where the error occurred.
* **Recursive Random Protection** — Added a note in `GUIDE.md` about the automatic exclusion of triggers containing `$random` to prevent infinite loops.
* **sudo Requirement** — The updater and the start script now require sudo privileges on Linux.
* **Configuration Guide Improved** — The [Configuration](./GUIDE.md#Configuration) chapter in `GUIDE.md` has been revised and expanded for clarity.
* **Linux Suffixes** - All executable Files now use `.bin` suffix on Linux.

#### Fixed
* **Early Comment Filtering** — Fixed an issue where chat messages sent before the connection was established were displayed immediately upon joining. The application now filters these out to ensure only new activity is shown.
* **Config Syntax** — Fixed a descriptive comment for the Prefix option in the `CommentCommands` section of the `config.yaml`.
* **Updater False Positives** — Resolved an issue where the updater falsely reported a critical 'NoneType' error during YAML parsing.
* **Config Loading** — Fixed a bug where the `random_included` list was not being read correctly, which previously caused unexpected behavior in the updater script.
* **UTF-8 Encoding** — Fixed a potential UTF-8 encoding error in the updater that occurred when printing emojis to the console. The updater now uses only ASCII output to ensure compatibility with all terminals.
* **Java (Windows)** — Fixed an issue where Java was missing from the project directory after download. The tool now automatically downloads and installs a portable Java runtime in the project directory on Windows if it is not already present.
* **Update handler** — Fixed a bug where the updater sometimes failed to detect the correct `version.txt` file in the release folder, which could cause the version to be set to `v0.0.0`. The updater now reliably locates and reads the correct version information after an update.
* **Permission Errors on Linux** — Fixed various permission-related issues on Linux by ensuring that all necessary files are created with appropriate permissions and that the updater and start script require sudo privileges to run.

### Developer

#### Deprecated
* **Developer Changelog Section** – Starting after release `v0.3.0`, the `"Developer"` section will no longer be maintained. Internal technical changes will continue to be documented in commit messages and the `dev-book`. Please use GitHub to review changes by checking the commits and viewing the diffs to see exactly what has been modified.

#### Added
* **Named Overlay Routing (`main.py`)** — Refactored the `>>` parser to extract optional `@Name` prefixes. The overlay name is now stored with the message body and passed to `send_overlay_text()` via the `overlay_name` parameter (defaults to `"default"`).
* **Validation Support** — Added support for `@Name>>` syntax in the `.mca` validator (`validator.py`) and the VS Code language server (`server.js`) to prevent false-positive syntax errors.
* **Syntax Highlighting** — Updated `mca.tmLanguage.json` to include distinct scoping for the `@Name` entity and the `>>` operator, providing better visual separation in editors.
* **Build Exclusions (`build.py`)** — Enhanced the `sync_folder()` function to support an `exclude` parameter, allowing for glob patterns to ignore specific files or directories during the build process.
* **IntelliSense Improvements** — Updated Dev-Book `ch03-06` with a new `NOTE` block recommending the import of `HookAPI` to enable better docstrings and IntelliSense support in development environments.
* **valid_functions** - Added `get_valid_functions` to the hook API to allow plugins to retrieve a list of valid functions.
* **ch03-06** - Added a new section on using `get_valid_functions` and `send_overlay_text`.

#### Changed
* **Config Versioning** — Bumped the configuration version from `3` to `4`.
* **Random Selection Logic** — Refactored the selection logic in `main.py`. The system now applies the `random_included` whitelist first, followed by the `random_exclude` blacklist, ensuring precise control over eligible triggers.
* **Host Configuration Binding** — Standardized Flask and Plugin API servers to pull bind addresses from `server_host` in `config.yaml`. Internal URLs and webview windows remain hardcoded to `127.0.0.1` to prevent cross-device security issues.
* **Advanced Error Handling** — Upgraded the updater's YAML parser to catch specific `YAMLError` exceptions. It now reports the exact file name and line number, replacing generic exception handling.

#### Fixed
* **`$random` Hook Logic** — Resolved a bug where an empty action list caused a misleading `[HOOK] [WARN] Unknown script action: 'random'` error. The logic now correctly handles empty sets.

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