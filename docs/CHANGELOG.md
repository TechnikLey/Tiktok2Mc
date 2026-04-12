# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

Each version is split into two sections:

- **User** — changes relevant to end users (new features, bug fixes, behavior changes).
- **Developer** — internal/technical changes relevant to contributors and developers (build system, code structure, tooling).

---

## [0.2.0] - 2026-04-12

### User

#### Added
- Linux support — the tool now runs on Linux in addition to Windows.
- Each process runs in its own terminal session on Linux for better overview.
- Interactive setup on first Linux launch — choose to install tmux/screen, continue without, or abort.
	- `$random` exclusion list is now configurable in `config.yaml` under `Gifts > random_exclude` instead of being fixed in the program.

#### Fixed
- Overlay now shows a transparent background when opened via browser URL instead of a green screen.
- Auto-update no longer falsely reports "Update has been installed" when no update was available.
- Plugin releases now always include the plugin's version.txt and README.md if present, so users get all plugin info in the release folder.

#### Changed
- README and User Guide updated to reflect Linux support, platform-specific start commands, and Java availability per OS.
- `data/actions.mca` — rewritten with fewer examples, clear comments explaining each line, and a compact header summarizing the format.

### Developer

#### Added
- `build.py` — cross-platform build script replacing `build.ps1`, with parallel compilation via `ThreadPoolExecutor` and hash-based build caching.
- `create_plugin.py` — cross-platform plugin scaffolding replacing `create_plugin.ps1`.
- `upload.py` — git tag & push script to trigger CI/CD releases.
- `.github/workflows/build.yml` — dual-platform CI/CD workflow (Windows + Linux), triggered by `v*` tags, produces `.zip` and `.tar.gz` release artifacts.
- Shebang lines (`#!/usr/bin/env python3`) added to all Python source files.
- `requirements.txt` — added PyQt6, PyQt6-WebEngine, and qtpy to support the pywebview Qt backend.

#### Changed
- `README.md` — updated OS requirements (Linux now supported), platform-specific start command, Java availability note for Linux.
- `GUIDE.md` — updated Java section (not bundled on Linux), platform-specific paths for `start` and `test_trigger` executables.
- `start.py` — tmux/screen session management on Linux with interactive installer prompt if neither is found. Processes tracked by session name, listed with attach commands after startup.
- `start.py` — `subprocess.CREATE_NEW_CONSOLE` and `taskkill` calls guarded by `sys.platform == "win32"` checks.
- `start.py` — display environment variables (`DISPLAY`, `WAYLAND_DISPLAY`, `XDG_RUNTIME_DIR`) forwarded to tmux/screen sessions so GUI apps (pywebview) work.
- `start.py` — updater runs synchronously without tmux/screen to preserve exit code handling.
- `server.py` — Java auto-discovery via bundled path, then system `PATH`, then automatic install through detected package manager (apt/dnf/pacman/zypper).
- `registry.py` — plugin discovery uses execute-permission checks on Linux instead of `.exe` file extension matching.
- `paths.py` — `EXE_SUFFIX` variable replaces all hardcoded `.exe` references.
- `update.py` — whitelist and binary paths use dynamic `EXE`/`BIN` suffixes per platform.
- `update.py` — `--auto` flag for non-interactive mode when launched by `start.py` (skips all `input()` prompts).
- Server binary uses `.bin` suffix on Linux to avoid name collision with system commands.

#### Fixed
- PyInstaller build errors (stdout + stderr) are now captured and displayed on failure instead of being silenced.
- Updater exit code `0` (no update) was not handled, causing false "Update installed" message in `start.py`.
- The build script now copies version.txt and README.md from each plugin folder (if present) into the release, so plugin metadata and documentation are always included.

#### Docs
- Dev-Book (DE + EN) `ch03` — documentation across all ch03 chapters rewritten to be generic; prefixes are no longer hardcoded in multiple places but reference one authoritative list in `ch03-02`.
- Dev-Book (DE + EN) `ch03-02` — added missing `>>` (Overlay) type to the "Command Types Explained" section.
- Dev-Book (DE + EN) `ch03-05` — updated `$random` documentation to reflect configurable exclusion list via `config.yaml`.
- `defaults/actions.mca` — reduced from 23 to 8 representative examples covering all prefixes (`/`, `!`, `$`, `>>`), with inline comments explaining each action.
- `GUIDE.md` — `$random` section updated with `random_exclude` config example.