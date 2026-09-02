# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [v1.0.1]

### Added

- **Update splash window** — updates now show an always-on-top progress window displaying the current phase (checking, downloading, installing, done) with a progress bar. The window closes automatically once the update finishes and the tool is running again, so you always know what's happening.
- **Actions Editor validation** — the visual Actions Editor now checks your triggers as you type and shows any problems (errors and warnings) in a panel above the editor, so you can see what's wrong right away. Saving is blocked until all errors and warnings are resolved. Common issues it flags: `{comment}` used on a non-comment trigger, `{user}`/`{comment}` in a shell command (where they can't be substituted), `{user}` in a vanilla command without the `!rc` suffix, and duplicate triggers.

### Changed

- **TikTok connection failure protection** — if the TikTok connection failed repeatedly in the past, the tool would keep retrying silently or the account could get blocked. After multiple failed connection attempts, a warning dialog now appears in the GUI where you can choose to re-enable the connection or keep it disabled. The fail counter resets once the connection is successful again.
- **Documentation updates** — `README.md`, `GUIDE.md`, and both developer books (EN/DE) have been updated. The Linux section now includes run instructions for the portable archive, the Build & Release workflow is documented, and admonition syntax has been corrected across all docs.

### Fixed

- **Plugin platform info not showing in GUI** — the plugin manager always displayed "—" for the platform column, even when plugins declared a specific platform (e.g. "windows") in their `plugin.json`. The platform value is now correctly read from the manifest and displayed in the dashboard.
- **Automatic updates failing / tool not starting** — when the tool was started (e.g. via the GUI) while an update was being installed, the automatic restart could be interrupted mid-update, leaving the tool in a broken or unstarted state with no way for the user to see what was wrong. The update process now handles the restart correctly itself and the new splash window shows the progress, so the tool reliably comes back up after every update.
- **Portable Linux archive missing from releases** — the `Linux.tar.gz` download was unavailable because the build pipeline produced an archive exceeding GitHub's 2 GiB asset limit after symlinks were dereferenced. The archive is now built directly on the release runner so symlinks stay intact and the file fits within the limit.
- **Event Tester gift images and like milestones not working** — the Event Tester did not display gift images for the selected gift, and testing like events failed because only like milestones (not raw likes) exist. Both now work correctly: gifts show their image, and a milestone selector appears when testing like events.
- **GUI/overlay losing connection after port relocation** — when the API port was automatically relocated by `auto_resolve`, the GUI and overlay still tried to connect to the old default port. They now use the actual resolved port.
- **Bridge crash on older TikTokLive versions** — fixed a startup crash that could occur with certain bundled TikTokLive library versions. The tool now handles incompatible listener APIs gracefully instead of shutting down.
- **Download path traversal vulnerability** — file downloads from the web UI are now sanitized to prevent paths outside the intended download folder.
- **Plugin recovery not logged** — when an unhealthy plugin comes back online, this is now recorded in the log so you can see that everything is working again.
- **Linux installer accepted wrong Java version** — the Linux installer only checked whether Java was present but did not verify the version, allowing Java 21 to pass even though Java 25 is required. It now validates the major version and warns if it is too old, with correct package names for all distros.
- **Linux binaries fail to start (missing libpython)** — PyInstaller 6.x on Linux resolves `libpython3.12.so.1.0` relative to the executable directory, so `--onefile` binaries (`start.bin`, `update.bin`) need an `_internal/` directory alongside them. The build now creates a root-level `_internal` symlink pointing to the shared runtime.
- **Linux GUI crashes with missing xcb-cursor** — Qt6 >= 6.5 requires `libxcb-cursor.so.0` on Linux, but the install hints and dependency checks did not mention it. The GUI now detects the missing library before Qt init and prints the correct install command. The Linux installer also checks for it.
- **`!rc` toggle in the Actions Editor** — vanilla commands can now be switched to "Send via RCON" directly in the editor (adds the `!rc` suffix), so `{user}` is replaced with the viewer's name without typing it manually. Before, the setting failed to persist after saving.

---

## [v1.0.0] - 2026-08-30

> [!WARNING]
> **Breaking changes.** v1.0.0 is a clean break from v0.x. Configuration files, plugins, and data from versions 0.x are not compatible. This is intentional — v1.0.0 is the first stable release built on a new foundation.

> [!IMPORTANT]
> **The new GUI is the centerpiece of v1.0.0.** You can now manage servers, plugins, events, overlays, reactions, and settings entirely through the graphical interface — no more editing config files by hand.
>
> This changelog only lists the most important user-facing changes. A massive amount of work happened under the hood.

### Added

- **Server Manager** — create, start, stop, and restart Minecraft servers directly from the GUI. Switch between multiple server instances, see live uptime, and open server folders with one click.
- **Live Dashboard** — a new main screen showing the health status of all your plugins, recent activity, and live event feed at a glance.
- **Event Reactions** — a visual, step-by-step wizard to set up what happens when viewers follow, like, gift, share, join, or comment. No more editing raw config files for common reaction setups.
- **Overlay Preview & Theme Editor** — edit overlay colors and see the result instantly. Test how overlay messages will look before they appear on stream.
- **Event Tester** — simulate any viewer event (follow, like, gift, etc.) to test if your reactions work correctly, without needing a real TikTok stream.
- **Windows Installer** — one-click setup wizard with desktop shortcuts and start menu entry. Uninstall supported.
- **Spotify Login Helper** — a guided tool that opens your browser, connects to Spotify, and saves the authentication — no more manual token handling.
- **API Key Protection** — optional password protection for anyone accessing the tool over your network.
- **VS Code Extension for .mca Files** — syntax highlighting, error checking, and auto-complete when editing action files in VS Code.
- **Automatic Backups** — your configuration files are now automatically backed up before changes, so you can recover if something goes wrong.
- **Port Conflict Detection** — if the required network ports are already in use, the tool now detects this and resolves it automatically.
- **Security warnings** — you'll see a console warning if you're still using the default RCON password or if the tool is exposed to your whole network.
- **Mobile-friendly dashboard** — the sidebar collapses to an off-canvas drawer on screens ≤768px with a hamburger menu. Modals and the actions editor stack vertically on small screens. Fully usable from your phone over LAN.
- **Accessibility** — keyboard navigation for modals (`Esc` to close, `Tab` trap), `aria-labels` on icon buttons and nav items, `:focus-visible` outlines, `aria-live` toasts. The dashboard is now navigable without a mouse.
- **Context help** — a "?" button in every view header and editor opens a built-in help panel with explanations. No more digging through documentation.
- **Keyboard shortcuts** — `Ctrl+S` saves in any editor, `/` focuses search, `Esc` closes modals, `?` opens the shortcut reference.
- **Overlay preview & test** — see a live preview of each overlay directly in the GUI and trigger a test message with one click.
- **Console autocomplete & history** — Tab completes Minecraft command prefixes (e.g. `/give`, `/tp`), Up/Down arrows cycle through your command history.
- **Log-level filter** — filter the live log by All/Info/Debug/Warn/Error with the level persisted across sessions.
- **Dashboard density toggle** — switch between Spacious and Compact layout for the status cards.
- **Config bundle export & import** — download or upload your entire setup (config, actions, plugin configs) as a single ZIP file — handy for backups or moving to another machine.
- **Session summaries** — when a live stream ends, a summary is automatically saved (gifts, likes, follows, comments, shares, joins, gift value). View session history in the new Sessions tab and download a Markdown report.
- **Full English/German localization** — the entire GUI is fully translated into English and German. Switch languages anytime.
- **Revenue viewer** — view and filter your streaming income data (gifts, likes, follows) with statistics and history.
- **Remote connect button** — connect to a running TikTok2Mc instance on a different PC from the launcher.
- **Plugin README viewer** — read plugin documentation directly inside the dashboard.
- **New actions.mca `!rc` suffix** — add a `!rc` suffix to vanilla commands to send them via RCON, allowing `{user}` to be replaced with the viewer's name.
- **Auto-install updates** — a new config option lets updates install automatically without prompting.
- **Java detection** — the tool handles Java installation with checksum verification, fallback download mirrors, and a proper progress bar with cancel option in the GUI.
- **Save/discard prompt** — switching between editor tabs warns you if you have unsaved changes, so nothing gets lost.
- **TikTok Chatbot** — an optional bot that automatically posts in your TikTok live chat: it thanks viewers for gifts and follows and can reply to keywords. You enable it in the new Chatbot tab.
- **Extension permission system** — plugins and hooks must declare the API surface they use (`permissions` in `plugin.json` / `hook.json`); undeclared calls are denied by default. This protects your system from misbehaving or malicious extensions.
- **Plugin sandbox** — optional process sandboxing restricts the resources (memory, CPU time, child processes) of each plugin subprocess. Built-in profiles `light`, `moderate` and `strict` are configurable via `plugin_sandbox` in `config.yaml`.
- **Outbound webhooks** — forward live events to external HTTP endpoints (e.g. Discord webhooks) with per-channel event filters, message templates and circuit breakers (`outbound` section in `config.yaml`, editable in the Dashboard).
- **Minecraft plugin management** — upload, enable/disable, and delete server plugins (`.jar` files) directly from the Server Manager in the Dashboard.
- **Extended plugin/hook API** — extensions gain runtime reload, structured event context with subscriptions/publishing, hook-to-hook queries, persistent key-value storage, dashboard UI widgets, custom HTTP routes, veto support for hook actions, and versioned event payload contracts enforced by the API server.
- **Notification system** — a central dispatcher for user-facing notifications (overlay, sound, TTS, Discord) with exchangeable channels.
- **Application icons** — all binaries and the Windows installer now ship with proper icons.

### Changed

- **Comment commands centralized** — ALL comment commands (including plugin commands) are now configured in a single place: `comment_commands.yaml`. The old system where comment commands were spread across `config.yaml` is removed.
- **Documentation overhaul** — All documentation has been completely rewritten to reflect the v1.0.0 rewrite: `README.md`, `GUIDE.md`, and both `dev-book-de` / `dev-book-en` developer books are updated with the new GUI workflow and current architecture.
- **Timer, Win Counter, Death Counter** — these plugins no longer depend on each other. You can use any combination without one forcing settings on another.
- **Plugin updates are now verified** — downloads are checked for integrity before installation, preventing corrupted updates.
- **Port count reduced from 12 to 5** — each plugin (Timer, Death Counter, Win Counter, Spotify Control) previously ran its own web server on a dedicated port. All plugins are now served through the central API server (29185). Only three ports are bound today (API: 29185, webhook: 29188, MC Server API: 29187); RCON (25575) and the Minecraft server (25565) are only connected to.
- **Smaller Linux installer** — PyQt6 / QtWebEngine is bundled only into binaries that actually use the GUI (gui, overlay, plugins), and those share a single runtime under `core/runtime/` instead of each embedding a full WebEngine copy. `server`, `start`, `app`, `update` and `test_trigger` no longer carry any WebEngine code, cutting the installer size significantly.
- **Win Counter overlay label** — the overlay text was changed from `Wins:` to `Score:` to avoid TikTok's word blacklist filtering out the overlay messages.
- **Breaking: hooks receive a typed `HookContext`** — hook actions now get a structured context object and an always-string user parameter. Custom hooks may need small adjustments (see developer documentation).
- **Dump Java Version** – Update the default Java version to 25 for support of the latest Minecraft versions.

### Removed

- **ChannelPoints plugin** (economy and points system)
- **LikeGoal plugin** (like goal overlay)
- **`shell_actions.txt`** — replaced by the `&` prefix in `actions.mca`

### Fixed

> [!NOTE]
> Due to a full system rewrite, many legacy issues from previous versions were inherently resolved.

- **Documentation (GitHub Pages)** — Fixed admonitions (Note, Tip, Warning, Caution, Important) not rendering on the deployed GitHub Pages site. The mdBook workflow now uses v0.5.2 with native GFM alert support instead of v0.4.36 which required a separate preprocessor.
- **Config changes work reliably across processes** — the tool now properly coordinates when multiple parts read or write the configuration at the same time.
- **Starting and stopping the tool no longer causes race conditions** — fixed an issue where quickly starting and stopping could cause unexpected behavior.
- **Overlay rendering fixed** — the overlay HTML template no longer produces broken CSS.
- **Update failure now shown in the GUI** — when an update fails, you'll see a clear error message instead of a silent failure.
- **RCON command queue no longer gets stuck** — fixed a deadlock that could cause commands to stop being sent to the Minecraft server.
- **Updater handles temporary errors** — the update checker now retries on temporary GitHub API errors instead of failing immediately.
- **`{user}` placeholder in vanilla commands** — the `{user}` placeholder now works in vanilla Minecraft commands when using the `!rc` suffix. A warning is shown if you forget to add the suffix.
- **Security hardening** — cross-origin and DNS-rebinding requests are rejected, secrets are redacted in API responses, `{user}` is sanitized against RCON slash-command injection, and overlay/theme inputs are XSS-hardened.

---

## [v0.5.0] - 2026-05-26

> [!IMPORTANT]
> ### Looking Ahead: v1.0.0
>
> The next major release will be **v1.0.0** — and it's going to be a big one. Version **v0.5.0** lays the groundwork for this milestone by introducing structural changes, new subsystems, and foundational features that v1.0.0 will fully capitalize on.
>
> **What to expect from v1.0.0:**
> - A fully functional **Graphical User Interface (GUI)** that lets you manage every aspect of the tool — configuration, plugins, overlays, comment commands, triggers, and more — without ever needing to open a file directly. Everything will be configurable through the interface.
> - Many new features and quality-of-life improvements.
> - Significant internal restructuring and cleanup, which means some existing configurations and workflows may need to be updated or otherwise can break.
>
> **Timeline:**
> Because of the sheer scope of changes, the v1.0.0 release will take some time to complete. The goal is to get it right rather than rush it out. If any critical bugs are found in v0.5.0 in the meantime, a **v0.5.1 hotfix release** may be published to address them before the major release arrives.

### Added

- **Spotify Integration** — A brand new Spotify plugin! Connect your Spotify account and trigger playback controls (play, pause, skip, volume, shuffle, repeat, save) directly from stream events. Comment commands, gift events, follows — whatever works for you. Comes with a sleek overlay showing album art and track info.
- **Multiple Comment Command Groups** — You can now define several independent comment command groups, each with its own prefix, role restrictions, and command list. Handy if you want different permission levels for different commands — moderators get one set, everyone else another.
- **HTTP-based Command Handlers** — Comment commands can now forward to an HTTP endpoint instead of sending RCON commands. Useful for triggering external services (like the new Spotify plugin) directly from chat.
- **Per-group on/off switch** — Each comment command group can now be enabled or disabled individually via `enabled: true/false`. Disable the Spotify `$` group without touching the `#` group.
- **Spotify chat commands** — The `$` group for Spotify is now pre-configured in the default `config.yaml`. Viewers can type `$play`, `$pause`, `$skip` and more directly in chat.
- **Smart port resolution** — The Spotify URL in comment commands uses `{spotify_port}` and automatically picks up your configured port. No more hardcoded ports.
- **Cooldown system for comment commands** — Each group can have a global cooldown (`cooldown`) and a per-user cooldown (`user_cooldown`) in seconds. Set `cooldown: 3` to force a 3s wait between any commands, or `user_cooldown: 10` so the same viewer can't spam commands faster than every 10 seconds.
- **Test comment mode** — The test tool (`test/test_trigger.exe`) now supports simulating chat comments. Just enter `comment` as the trigger and you can test prefixes, role checks, cooldowns, and command dispatch — exactly as if a viewer typed it in chat.
- **Startup prompt for TikTok username** — If your config still has the default `your_tiktok_username`, the tool will ask you to enter your real username on startup. Press Enter to keep the default and continue.
- **Plugins register their port** — All overlay plugins now pass their port number during registration. The port is stored in `PLUGIN_REGISTRY.json` and displayed at startup as OBS Browser Source URLs.
- **Overlay URLs shown at startup** — When the tool starts, it now prints a list of all overlay URLs from the registry ready for OBS Browser Sources. No more guessing which port goes where.
- **Help command in console** — Type `help` in the start console to see available commands (`exit`, `stop`).
- **RCON timeout increased** — The RCON connection timeout was raised from 0.5s to 3.0s, making remote Minecraft servers more reliable.
- **Log files documentation** — A new "Log Files" section in GUIDE.md explains what each log file contains and how to clean them up.
- **tmux sessions shown before command loop** — On Linux, active tmux/screen sessions are now displayed right after startup, not after typing `exit`.
- **Channel Points plugin** — Brand new loyalty system! Viewers earn points automatically by doing stuff in chat — joining, commenting, liking, gifting, following, sharing. Comes with an OBS overlay showing the leaderboard.
- **Customizable overlay colors** — All overlays (Like Goal, Timer, Death Counter, Win Counter, Spotify, Channel Points, Overlay Text) now read their colors from the new `theme:` section in `config.yaml`. Change backgrounds, text colors, and accent colors for each plugin individually — no more hardcoded defaults.
- **Config variable resolution for comment groups** — Comment command URLs now support `{channel_points_port}` in addition to `{spotify_port}`, resolved at startup from their respective config sections.
- **`trigger_comment_event` option** — Each comment command group can now control whether the `comment` trigger in `actions.mca` also fires. Set `trigger_comment_event: false` to suppress the trigger for that group.
- **Spotify OAuth CSRF protection** — The Spotify authorization callback now verifies the state parameter to prevent cross-site request forgery attacks.
- **Event hooks included in updates** — The built-in event hooks (`random.py` and `spotify.py`) are now updated automatically. Any custom event hooks you may have created are not affected.

### Changed

- **Spotify tokens now stored safely** — Token data is protected during simultaneous access, preventing potential file corruption when multiple actions try to save at the same time.
- **Channel points viewer names cleaned up** — Viewer names in the leaderboard overlay are now displayed safely, preventing any display issues from unusual characters.
- **Gift-triggered file renamed** — The file that runs custom commands when receiving TikTok gifts has been renamed from `http_actions.txt` to `shell_actions.txt` to better reflect what it does. If you have your own entries in `data/shell_actions.txt`, rename it to `data/shell_actions.txt` manually.
- **Duplicate command detection in `commands` list** — If a command appears multiple times in a group's `commands` list, the tool now warns you. Max 5 warnings per group, then "N further" suppressed. No crash, the program keeps running.
- **Duplicate key detection in `commands_config`** — Duplicate entries in `commands_config` (e.g. two `op:` blocks) are now caught on startup and trigger an error with "Press Enter to exit". Detects 2+ duplicates, always reports the first occurrence's line number.
- **Per-command settings separated from command list** — Each command can now have its own `points_cost`, cooldown, and roles in a separate `commands_config` block. The `commands` list stays clean — just names, no clutter.
- **Channel points integrated into `$` commands** — No more confusing `!` prefix. Points costs are set directly on any command like `skip: { points_cost: 50 }`. Viewers earn points by simply interacting with the stream.
- **All interactions count toward points** — Liking, following, gifting, sharing, joining, and commenting all keep viewers in the active points window. Pure lurkers don't earn, but anyone who interacts does.
- **Follow spam protection** — Once someone follows, they're saved to a file and won't trigger the follow action again. Choose between `all_time` (never repeats) or `per_stream` (resets each stream) in config.
- **Smart config warnings** — If you accidentally put a command in `commands_config` that can never be used (wrong mode, not in the commands list), the tool will tell you. Stops after 5 warnings so your console doesn't flood.
- **Test plugin and example hook excluded from release** — The `plugins/test/` folder and `event_hooks/example_hook.py` are no longer included in the release build. These are development-only files and don't belong in the user package.
- **Spotify config banner only shows when needed** — Setup instructions are no longer printed every startup if you're already authenticated. First-time users still get the full guide.
- **Spotify no longer forces re-auth dialog** — Changed `show_dialog` from `"true"` to `"false"`. Existing users won't be prompted to re-authorize every time they log in.
- **Spotify overlay updates live** — The overlay now polls Spotify every 2 seconds, so track changes show up automatically without refreshing the page. The progress bar runs smoothly between updates.
- **Progress bar stops when paused** — No more jumping up and down. The bar stays still when the track is paused.
- **Overlay scales with window** — The overlay resizes smoothly whether you're using pywebview or OBS. Set your browser source to any size and it fits.
- **Track info stays after long pause** — If Spotify's been paused for a while, the last known track name, artist, and cover stay on screen instead of disappearing to "Unknown".
- **Revenue rounded to 2 decimals** — The daily revenue log no longer shows ugly floating-point artifacts like `0.22000000000000006`. Values are now cleanly rounded to two decimal places.
- **Revenue is gross** — The log entry `estimated_revenue_usd` is a gross estimate (diamonds × 0.005), not the net payout after TikTok's cut. A note has been added to the docs.
- **shell_actions.txt now supports variables** — Use `//define name = value` at the top of the file and reference it with `{name}` in commands. The default file now uses `{port}` instead of hardcoded `29191`.
- **Improved command execution safety** — Internal commands (HTTP actions and process management) no longer run through the system shell. This reduces the risk of injection and makes the tool more reliable across different platforms.
- **Console output switched to structured logging** — All console messages now use proper log levels (info, warning, error) instead of plain print statements. This makes it easier to filter and understand what's happening at a glance.
- **Datapack root validation** — The datapack generator now checks whether the target folder exists and is a directory before building. If the path is invalid, you get a clear error message instead of a silent failure.

### Fixed

- **Plugin overlays more stable under load** — Fixed rare crashes in Death Counter, Like Goal, Win Counter, and Spotify overlays when multiple browser tabs or OBS sources connected at the same time. SSE streams now handle concurrent connections reliably.
- **Spotify event hook now respects your configured port** — The Spotify hook no longer hardcodes port `29194`. It reads your actual port from `config.yaml`, so custom port setups work correctly again.
- **Comment command fixes** — HTTP-based comment commands now send the right data to external services instead of garbled parameters. Denied command logs also now show the correct command text instead of an empty placeholder.
- **Better updater reliability on Windows** — The updater now uses the correct process mechanism on Windows instead of a Unix-only approach that silently failed. Signal file errors during updates are also handled gracefully instead of crashing.
- **Validator error messages improved** — Bracket mismatch errors now point to the exact position of the problem instead of vaguely marking the whole line. Error messages are now consistently in English. Colons inside commands like `/say hello:world` are no longer falsely flagged.
- **Graceful fallbacks for edge cases** — Fixed cases where the tool could crash on plugin directory detection in certain Python environments, when a hook file fails to parse, or when `wait_time` wasn't properly initialized.
- **Like goal no longer skips or duplicates during like bursts** — Fixed a timing issue where rapid like events could interfere with each other, causing triggered actions to be missed or sent twice.
- **Gift revenue saving no longer slows everything down** — The bot now saves revenue data in the background without blocking chat, likes, or other live interactions.
- **Special characters no longer cause crashes** — Fixed missing text encoding in death counter, timer, and win counter plugins. Usernames and content with emojis or accented letters now save and load correctly.
- **Like goal config values with quotes handled correctly** — If the like goal settings contain numbers stored as text (e.g. `"100000"` instead of `100000`), the tool now handles them properly instead of throwing an error.
- **Timer plugin uses fewer system resources** — The countdown reset now manages its background tasks more efficiently when the timer repeatedly hits zero.
- **Build system exclusions now reliable** — The release build script correctly excludes files using all glob patterns, not just simple ones.
- **Validation results checked more robustly** — Fixed internal comparisons in validation checks to use proper type-safe comparisons instead of string matching.
- **GUI module no longer crashes on startup** — Fixed a missing import that prevented the configuration GUI from loading at all.
- **Upload script messages now visible** — The upload script's progress messages are now actually displayed in the console instead of being silently discarded.
- **Updater no longer crashes on config or permission errors** — Fixed a potential crash when the configuration fails to load or root permissions are missing during an update.
- **Death Counter handles empty save requests** — Fixed a rare crash in the Death Counter plugin when saving window dimensions with an empty request body.
- **Hook API internal naming cleaned up** — Fixed a naming conflict in the Hook API that could cause unexpected behavior when sending overlay text from event hooks.
- **Start script no longer crashes on launch** — Fixed a critical startup error that prevented the tool from running at all.
- **Download progress shown as a single line** — During updates, the download progress percentage now stays on one line instead of flooding the log with thousands of entries.
- **Webhook server starts only when bot is ready** — The internal webhook server no longer accepts requests before the bot is fully initialized, preventing random crashes during startup.
- **Webhook and overlay servers handle multiple requests** — Both the main webhook server and the overlay text server now handle concurrent connections reliably instead of blocking on each request.
- **Plugin scanning no longer stops at the first error** — If one plugin fails to scan, the remaining plugins are still registered correctly.
- **Shutdown now fully terminates all programs** — When the auto-shutdown timer runs out, the tool now properly stops the Minecraft server and all plugins before exiting. No more orphan processes left behind.
- **Graceful handling of no-terminal environments** — The tool no longer blocks waiting for keyboard input when running in non-interactive environments (Docker, CI, systemd). Validation errors simply show the message and exit cleanly.
- **Correct exit code on config errors** — If the configuration fails to load, the tool now reports a non-zero exit code so that monitoring systems and scripts can detect the failure.
- **Overlay text race condition fixed** — On rare occasion during rapid startup, multiple overlay messages could trigger a race condition. The overlay manager is now fully thread-safe.
- **Like goal protection against invalid configuration** — If `initial_goal` is accidentally set to 0 or a negative value, it is now automatically treated as 1, preventing an infinite loop.
- **Update system compatible with Python 3.10+** — The file installer now works correctly on Python versions older than 3.12. No more crashes when extracting update packages.
- **Hook API no longer exposes modifiable config** — Event hooks receive a read-only copy of the configuration. Accidental changes from within a hook no longer affect the running tool.
- **Empty config file no longer crashes on startup** — If your `config.yaml` is empty, the tool now loads it as an empty config instead of crashing with an error.
- **Overlay text config is now optional** — If your overlay settings section is missing or empty, the overlay manager handles it gracefully instead of crashing.
- **Comment command URL now correctly substituted** — When using `{user}` or `{text}` placeholders in HTTP comment command URLs, the substituted URL is now actually sent instead of the raw template.
- **Like goal queue full is now logged** — When the like goal queue is full and a delta is dropped, a message now appears in the console so you know it happened.
- **RCON inactive queue no longer loops forever** — If the RCON queue is paused, commands are now discarded after a maximum number of retries instead of being re-queued indefinitely.
- **Overlay names must be valid** — If an overlay in the config has no name, it is now skipped with a warning instead of being silently stored without one.
- **Overlay connection errors are properly logged** — Connection failures to overlay clients now appear in the log output instead of plain console prints.
- **Device block detection no longer triggers on false positives** — The TikTok reconnection logic no longer mistakes ordinary error messages containing words like "code" or "status" for a device block.
- **Update logs with negative values handled** — If `max_update_logs` is set to a negative value other than `-1`, it is now treated as `-1` (keep all logs) with a warning.
- **Downloads with missing file size handled** — Downloads (updates, etc.) no longer crash if the server doesn't send a `Content-Length` header or sends an empty one.
- **Timer now works as OBS Browser Source** — The countdown timer no longer requires the pywebview window. In `gui_hidden` mode, add it as an OBS Browser Source at `http://localhost:29189` and it responds to death/respawn events via webhook.
- **Linux start command now includes `sudo`** — All references to `./start.bin` in the docs now correctly show `sudo ./start.bin`, since the tool requires root privileges on Linux for updates and permission-sensitive paths.
- **`$random` deny-all mode** — If you use `deny-all` mode for your random trigger filter, it now correctly **excludes** the listed triggers instead of accidentally only allowing them. The `allow-all` mode was not affected.
- **Fixed outdated config path in actions.mca comment** — The `$random` comment now correctly points to `random_triggers > triggers` instead of the old `Gifts > random_exclude`.
- **Better error messages everywhere** — Errors that were previously swallowed without a trace (failed points lookups, connection issues, plugin problems) are now shown in the console. Makes debugging issues way easier — the tool tells you what went wrong instead of silently failing.
- **Timer webhook no longer crashes on bad input** — The countdown timer now properly handles POST requests with missing or malformed JSON data.
- **Queue overloads are now actually caught** — When the command queue overflows, the error is properly handled instead of crashing silently in the background.
- **Bracket validation skips strings** — The actions file validator no longer falsely reports unbalanced brackets when they appear inside text strings (e.g. JSON data or selectors in quotes).
- **Updater no longer crashes on startup** — Fixed a critical bug where the auto-updater could crash immediately with a startup error due to missing internal references.
- **Config loading errors are now properly reported** — If the configuration file cannot be loaded, the tool now shows a clear error message instead of silently closing. This applies to the main launcher, updater, and all plugin tools.
- **Validators no longer block on formatting preferences** — The actions file validator now treats spaces after the colon as a friendly warning instead of a blocking error. The preferred format is `trigger:command` (no space), but `trigger: command` will still work.
- **Test plugin builds no longer accidentally exclude similar-named folders** — The build system now only excludes the `test` plugin itself and no longer accidentally skips other plugins whose folder names happen to contain "test".
- **Overlay multiplier detection** — The actions file validator now shows an error if you try to use a multiplier (`xN`) on an overlay command (`>>` or `@Name>>`). Multipliers don't work for overlays, so the validator catches this early.
- **Comment commands no longer match wrong prefix** — Fixed a bug where a command with a shorter prefix (e.g. `!test`) could trigger when a longer one was typed (e.g. `!test123`). Commands are now correctly matched longest-first.
- **Like goal no longer starts duplicate web servers** — Fixed a potential issue where the like goal overlay could accidentally start two Flask instances.
- **Various plugins no longer crash on special characters** — Fixed missing UTF-8 encoding in file operations across death counter, timer, win counter, and the test tool. Player names or content with special characters no longer cause crashes.
- **Config loader no longer returns failure when datapacks folder is missing** — Fixed a bug where the configuration loader could report an error even though everything else was fine, just because the Minecraft datapacks directory didn't exist yet.
- **Follow tracking with special characters** — Fixed a crash on Windows when usernames containing emojis or accented letters were followed. The tracking file now handles all characters correctly.
- **Follow events safer under load** — Fixed a rare issue where multiple follow events arriving at the exact same moment could interfere with each other. The tool now keeps everything in order.
- **Update shutdown wait improved** — The updater no longer relies on a fixed timer when waiting for the application to close. It now actively checks whether everything has shut down before installing files, preventing file-lock errors on slower systems.
- **Update signal made more reliable** — Fixed a corner case where the start script could occasionally miss the shutdown signal during an update, potentially leaving the process running.
- **Overlay cleanup on disconnect** — When a browser source or OBS overlay disconnects, it is now properly cleaned up behind the scenes. Previously, these could pile up over long streams.
- **MinecraftServerAPI config preserved** — The tool no longer removes comments and custom formatting from the MinecraftServerAPI plugin's config file every time it starts.
- **Spotify overlay now shows for all successful commands** — Fixed an issue where some successful Spotify actions (like play or pause) didn't display the on-screen notification.
- **Slightly faster reconnection** — Cleaned up a repeated calculation that happened on every reconnect attempt, making reconnections a tiny bit snappier.
- **Like events no longer vanish silently** — If the command queue fills up during a burst of likes, the tool now logs a message instead of dropping events without telling you.
- **Window state save fixed for Timer and Win Counter** — Saving window dimensions with an empty or invalid request no longer corrupts the saved state file in these two plugins.
- **Role checks more reliable** — Fixed an edge case where moderator and superfan permission checks could behave unexpectedly when role information was missing from a viewer event.
- **Validator no longer complains about `!` in normal text** — The actions file validator sometimes flagged commands like `/say Hello!` as errors because it thought the `!` was a misplaced command prefix. This has been cleaned up – `!` is now only treated as a prefix when it's the very first character of a command, exactly as intended.
- **Validator no longer mistakes trailing whitespace for extra colons** — If a line in your actions file had a harmless trailing space after the command, the validator could show a confusing "trailing colons" error. That false alarm is gone.
- **Validator no longer flags colons inside commands** — If a command legitimately contained a colon (e.g. `/say hello:world`), the validator could wrongly report a trailing colon error. That's been cleaned up — colons inside commands are now ignored.
- **Better bracket mismatch detection** — When brackets don't match up, the validator now points to the exact position of the problem instead of vaguely marking the whole line. Makes it much easier to spot where a `]` or `}` is out of place.
- **Validator error messages now fully in English** — Removed a mixed-language error message that previously showed German text alongside English. All validator messages are now consistently in English.
- **Random trigger fallback more robust** — When the `$random` hook couldn't find a username, it could show a garbled internal representation instead of a clean fallback. Now it reliably falls back to `"Unknown"`.
- **Updater works with installation paths containing spaces on Windows** — Fixed an issue where the updater could fail to complete a self-update when the tool was installed in a directory with spaces (like `Program Files`).
- **More robust update cleanup** — The updater now handles locked temporary files and update signal errors gracefully instead of crashing during cleanup.

---

## [v0.4.0] - 2026-05-22

> [!WARNING]
> Due to significant changes to the configuration structure, errors may occur. Please review the **Changed** section below and ensure your config matches the latest template. If you are affected, simply download the latest release and replace your `config.yaml` with the new one from the release package.

### Added

- **Config Option: `max_update_logs`** — A new configuration option under the `Updater` section in `config.yaml` that allows users to specify how many update log files to keep in the `logs/update_logs` directory.
- **`AIPrompt.md`** — Added a system prompt template for AI-powered assistants. When loaded, the AI follows strict rules.
- **AI Prompt documentation** — The `AIPrompt.md` file is now referenced in the user guide (`docs/GUIDE.md`) under Additional Resources.
- **Each plugin gets its own `config.yaml`** – External plugins are now independent of the global configuration. Every plugin folder contains its own `config.yaml`, so settings no longer get mixed up. Built-in plugins continue to use the global config.
- **`create_plugin.py`** – The new script creates the complete plugin folder including `config.yaml` and `version.txt` with the new format. You will also be asked whether the plugin should be updatable via GitHub.
- **Automatic plugin updates** – The new `plugin_updater` checks on startup whether a newer version of a plugin is available on GitHub. If yes, the update is downloaded and installed. Your plugin `config.yaml` is never overwritten!
- **Sync of the English developer documentation** – The English dev book now has the same content and structure as the German version.

### Changed

- **Updater Logging (Linux)** — The updater now creates a new log file for each update attempt in the `logs/update_logs` directory, named with a timestamp in 24-hour format (e.g., `updater_2026-04-19_14-30.log`). This allows users to keep a history of update attempts and their outcomes without overwriting previous logs.
- **Documentation rewrite** — The user guide (`docs/GUIDE.md`) has been completely rewritten with improved structure, readability, and beginner-friendliness. All configuration explanations outside the Quick Start section have been replaced with references to `config.yaml`.
- **Improved config template** — Changed the annotated of the config file with enhanced inline comments and a quick-start checklist.
- **Default Port Change** — Changed the default ports for several internal services to less commonly used ports to avoid conflicts with other software (GUI: 29185, OverlayTxt: 29186, MinecraftServerAPI: 29187, Webhook: 29188, Timer: 29189, DeathCounter: 29190, WinCounter: 29191, LikeGoal: 29193). The Minecraft server (25565) and RCON (25575) ports remain unchanged.
- **Simplified allow/deny rules for Comment Commands** – Instead of two separate lists (Whitelist + Blacklist) with complex interaction rules, you now set a **Mode** (`deny-all` or `allow-all`) and a single **Commands** list. `deny-all` = only the listed commands work, `allow-all` = everything works except the listed commands.
- **Simplified `$random` trigger filter** – The settings for `$random` now live in their own `RandomTriggers` section (no longer hidden under `Gifts`). Same `deny-all` / `allow-all` mode as above.
- **`Shutdown` section** – The auto-shutdown settings (`Enabled`, `DelaySeconds`) are now grouped in their own `Shutdown` block instead of being individual top-level keys.
- **Sudo warning renamed** – `no_sudo_warning` is now `show_sudo_warning`. It is enabled by default; set it to `false` to hide the warning.
- **Config keys renamed to snake_case** – All block names and setting names in `config.yaml` now use consistent snake_case (e.g., `MinecraftServerAPI` → `minecraft_server_api`, `Overlaytxt` → `overlay_text`, `Enable` → `enabled`, `Port` → `port`, `StartTime` → `start_time`). Sections have also been reordered in a more logical user-friendly sequence.
- **`like_goal_port` moved to `like_goal` block** – The Like Goal port (`like_goal_port: 29193`) was moved from the `gifts` block into the `like_goal` block as `port: 29193` for consistency with other modules.
- **`like_triggers` moved from `gifts` to `like_goal`** – Like milestone triggers now live under `like_goal.triggers` (was `gifts.like_triggers`), grouping all like-related settings together.
- **`autosave_interval_seconds` moved to `tiktok`** – Gift revenue logging moved under `tiktok.autosave_interval_seconds` (was `gifts.autosave_interval_seconds`). The `gifts` block has been removed.
- **`win_counter.web_server_port` renamed to `win_counter.port`** – Consistent with other single-port modules.
- **Modules section reordered** – Modules are now grouped logically: infrastructure → overlays → game logic → system.
- **Ports moved to own modules** – `deathcounter_port` moved from `minecraft_server_api` to `death_counter.port`; `web_server_port_timer` moved to `timer.port`. Each module now owns its own port.
- **`version.txt` format** – The file now uses a key:value format (`version: v1.0.0`, `update_url: ...`) instead of a single version number. This allows the updater to know where to check for new versions.
- **Documentation overhaul** – Both the German and the English developer documentation have been extensively revised and adapted to the new plugin system. All chapters now reflect the current structure.

### Fixed

- **Revenue logging shows wrong daily values** — Fixed a bug where the daily revenue log (`revenue_log.jsonl`) showed the **cumulative** earnings since bot start instead of only the current day's revenue. The bot now correctly resets its baseline at the start of each calendar day.
- **Webhook endpoint returns 400 on invalid JSON** — The internal webhook endpoint no longer silently returns `200 OK` when it receives malformed JSON. It now correctly returns `400 Bad Request` and logs the error.
- **Timer now works as OBS Browser Source** — The countdown timer no longer requires the pywebview window. In `gui_hidden` mode, you can add it as an OBS Browser Source at `http://localhost:29189` and it will respond to death/respawn events via webhook.
- **Test tool works with more action types** — Fixed a bug where the test tool was unable to test actions that are stored separately from the main action list.
- **Like goal connection problems now visible** — Errors when connecting to the like goal overlay are now shown in the console instead of being silently ignored. This makes it easier to notice and fix connection issues.
- **Like trigger race condition on startup** — Fixed a race condition where the first like event could be silently dropped if two like events arrived simultaneously during initialization.
- **Webhook server ignored `server_host` setting** — The internal webhook server (for MinecraftServerAPI events) now respects the `server_host` configuration. Previously it always bound to `127.0.0.1`, even when `server_host` was set to `0.0.0.0`.
- **Startup crash when config is broken** — The bot now properly stops if the configuration file cannot be loaded, instead of continuing with invalid settings and failing silently later.
- **Updater EOFError** — Fixed an issue where the updater could raise an `EOFERROR` when no input is available (In most cases only on Linux) during the update process. The updater now catches this exception and prints an informational message instead of crashing.
- **Overlay `>>` command not working** — Fixed a bug where the `>>` overlay command (without `@Name`) used the wrong fallback name (`"defaults"` instead of `"default"`), causing overlay text to silently fail.
- **default overlay not available after removing from config** — Fixed a bug where removing the `default` overlay from `config.yaml` caused the `>>` command to stop working. A fallback `default` overlay is now always created internally.
- **Gift revenue counter not updating** — Fixed a bug where the gift revenue counter never actually ran. It now works and updates correctly.
- **Deathcounter port configuration ignored** — The deathcounter plugin now correctly reads the configured port from `config.yaml`. Previously a custom port setting was silently ignored.
- **Overlay text without overlay name** — Overlay text commands now work reliably even when no specific overlay name is provided.
- **Missing error messages in plugins** — Errors when loading or saving plugin data (window sizes, stats) are now shown in the console instead of being silently ignored.
- **Missing error messages for RCON connection** — Connection issues to the Minecraft server are now shown in the console, making it easier to spot problems.
- **Wrong Linux command in README** — Fixed the startup command in the quick-start guide (`./start` → `./start.bin`).
- **Outdated references** – All `create_plugin.ps1` references have been replaced with `create_plugin.py`. The import for `register_plugin` now points to the correct module (`python.registry`).
- **OverlayTxt plugin registration ignored `enabled` flag** — The overlay text plugin always registered as enabled regardless of the `enabled: false` setting in `config.yaml`, because it read from an uninitialized variable instead of the parsed config.
- **Death counter read wrong config key** — The death counter plugin read `minecraft_server_api.enabled` instead of `death_counter.enabled` to determine whether it should be active.
- **Update log retention off-by-one** — When `max_update_logs` was set, the updater kept one fewer log than configured (e.g., 19 instead of 20).
- **Like trigger rule `enable` key name mismatch** — The internal rule parser read `enable` (without *d*) while config.yaml uses `enabled`. Triggers with `enabled: false` were always treated as enabled.
- **Bare `except:` caught system interrupts** — A bare `except:` in overlay utilities could catch `KeyboardInterrupt` and `SystemExit`, making the tool harder to stop.

---

## [v0.3.0] - 2026-04-18

> [!WARNING]
> When updating your project to this version, errors may occur.
> If you encounter problems, please download the latest release and copy your `data` folder (and any other important files like `config.yaml`) into the new release directory.

### Added

- **Named Overlays (`@Name>>`)** — You can now run multiple overlay windows simultaneously and route messages to specific ones. Define names in `config.yaml` under `Overlaytxt > Overlays` and use `@Name>>` in `actions.mca` to target a window. Using `>>` without a name still targets the `default` overlay.
- **`random_included` configuration** — A new whitelist in `config.yaml` under `Gifts` that allows you to precisely control which triggers are eligible for selection by the `$random` command.
- **Release Documentation** — The entire `docs` folder is now included in the release, allowing you to access all documentation files and changelogs directly without visiting GitHub.
- **Trigger Names** — You can now use descriptive trigger names instead of just trigger numbers within the `actions.mca` file for better readability.
- **Share Trigger** — Added a new trigger type `share` that fires whenever a viewer shares the live stream.
- **Streaming Income Tracking** — The application now tracks income based on received gifts and their USD value. This data is stored in `revenue_log.jsonl` and can be used for analytics.
- **Autosave for Revenue Logs** — Added `autosave_interval_seconds` to the config to control how often revenue data is saved to disk (default is `60` seconds), ensuring data integrity in case of crashes.
- **Automatic Shutdown** — The application can now automatically shut down when the live stream ends.
- **Configurable Shutdown Behavior** — You can now define a custom shutdown delay or disable the automatic shutdown entirely via the configuration settings to allow for post-live processing.
- **Network Access (`server_host`)** — Web servers (GUI, plugins, overlays) can now be made accessible from other devices in your network by setting `server_host: "0.0.0.0"` in `config.yaml`. This is useful for using overlays on separate PCs or OBS instances.
- **Enhanced Configuration Info** — Added additional explanatory info to the `config.yaml` file to prevent errors caused by misinterpreting list key values.
- **New Guide Chapters** — Updated `GUIDE.md` with a new chapter on using trigger names/IDs, priority rules, and handling names that contain spaces.
- **Config Option: `no_sudo_warning`** — New config key to suppress the warning about missing sudo/root privileges on Linux systems.

### Changed

- **GoalMultiplier Default** — Updated the default `GoalMultiplier` from `2` to `1` to prevent overwhelming growth of goal-based triggers for new users.
- **Random Command Defaults** — Added `join` and `comment` to the default `random_exclude` list for the `$random` command to reduce spam.
- **Random List Logic** — Updated the logic of the `random_exclude` list to work more effectively alongside the new `random_included` whitelist.
- **Example Actions** — Commented out the `join` trigger in the `actions.mca` examples to prevent overlay spam. Rewrote various command examples to be more concise.
- **VS Code Extension** — Updated the `mca.vsix` extension to support the new `''` syntax for trigger names that contain spaces.
- **Updater Error Reporting** — The updater now provides more specific error messages for YAML parsing, including the exact filename and line number where the error occurred.
- **Recursive Random Protection** — Added a note in `GUIDE.md` about the automatic exclusion of triggers containing `$random` to prevent infinite loops.
- **sudo Requirement** — The updater and the start script now require sudo privileges on Linux.
- **Configuration Guide Improved** — The Configuration chapter in `GUIDE.md` has been revised and expanded for clarity.
- **Linux Suffixes** — All executable Files now use `.bin` suffix on Linux.

### Fixed

- **Early Comment Filtering** — Fixed an issue where chat messages sent before the connection was established were displayed immediately upon joining. The application now filters these out to ensure only new activity is shown.
- **Config Syntax** — Fixed a descriptive comment for the Prefix option in the `CommentCommands` section of the `config.yaml`.
- **Updater False Positives** — Resolved an issue where the updater falsely reported a critical 'NoneType' error during YAML parsing.
- **Config Loading** — Fixed a bug where the `random_included` list was not being read correctly, which previously caused unexpected behavior in the updater script.
- **UTF-8 Encoding** — Fixed a potential UTF-8 encoding error in the updater that occurred when printing emojis to the console. The updater now uses only ASCII output to ensure compatibility with all terminals.
- **Java (Windows)** — Fixed an issue where Java was missing from the project directory after download. The tool now automatically downloads and installs a portable Java runtime in the project directory on Windows if it is not already present.
- **Update handler** — Fixed a bug where the updater sometimes failed to detect the correct `version.txt` file in the release folder, which could cause the version to be set to `v0.0.0`. The updater now reliably locates and reads the correct version information after an update.
- **Permission Errors on Linux** — Fixed various permission-related issues on Linux by ensuring that all necessary files are created with appropriate permissions and that the updater and start script require sudo privileges to run.

---

## [v0.2.0] - 2026-04-13

### Added

- **Linux support** — the tool now runs on Linux in addition to Windows.
- **Terminal isolation** — each process runs in its own terminal session on Linux for better overview.
- **Interactive setup** — on first Linux launch, choose to install tmux/screen, continue without, or abort.
- **Configurable exclusions** — `$random` exclusion list is now configurable in `config.yaml` under `Gifts > random_exclude` instead of being fixed in the program.
- **`comment` trigger** — fires every time a viewer writes a comment in the live chat.
- **`join` trigger** — fires every time a viewer joins the live stream.
- **CommentCommands** — config option that lets viewers send Minecraft commands via chat comments. Configurable prefix, role restrictions (`all`, `moderator`, `superfan`, `fanclub`), whitelist, and blacklist.
- **VS Code extension** — `mca.vsix` adds syntax highlighting and error checking for `.mca` files in VS Code.
- **Overlay Validation** — give error if you use `{comment}` in overlay text for triggers other than `comment` (prevents mistakes).

### Changed

- **Documentation (`README` / `GUIDE.md`)** — updated to reflect Linux support, platform-specific start commands, and Java availability per OS.
- **`data/actions.mca`** — rewritten with fewer examples, clear comments explaining each line, and a compact header summarizing the format.
- **`GUIDE.md`** — documented `comment` and `join` triggers, `CommentCommands` config options, and updated `shell_actions.txt` section.

### Fixed

- **Overlay background** — now shows a transparent background when opened via browser URL instead of a green screen.
- **Auto-updater** — no longer falsely reports "Update has been installed" when no update was available.
- **Plugin releases** — now always include the plugin's `version.txt` and `README.md` if present, so users get all plugin info in the release folder.
