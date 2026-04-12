# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased]

### User

#### Added
- Linux support — the tool now runs on Linux in addition to Windows.
- Each process runs in its own terminal session on Linux for better overview.

#### Fixed
- overlay now shows a transparent background when opened via browser URL instead of a green screen.

### Developer

#### Added
- `build.py` — cross-platform build script replacing `build.ps1`, with parallel compilation via `ThreadPoolExecutor` and hash-based build caching.
- `create_plugin.py` — cross-platform plugin scaffolding replacing `create_plugin.ps1`.
- `upload.py` — git tag & push script to trigger CI/CD releases.
- `.github/workflows/build.yml` — dual-platform CI/CD workflow (Windows + Linux), triggered by `v*` tags, produces `.zip` and `.tar.gz` release artifacts.
- Shebang lines (`#!/usr/bin/env python3`) added to all Python source files.

#### Changed
- `start.py` — tmux/screen session management on Linux with interactive installer prompt if neither is found. Processes tracked by session name, listed with attach commands after startup.
- `start.py` — `subprocess.CREATE_NEW_CONSOLE` and `taskkill` calls guarded by `sys.platform == "win32"` checks.
- `server.py` — Java auto-discovery via bundled path, then system `PATH`, then automatic install through detected package manager (apt/dnf/pacman/zypper).
- `registry.py` — plugin discovery uses execute-permission checks on Linux instead of `.exe` file extension matching.
- `paths.py` — `EXE_SUFFIX` variable replaces all hardcoded `.exe` references.
- `update.py` — whitelist and binary paths use dynamic `EXE`/`BIN` suffixes per platform.
- Server binary uses `.bin` suffix on Linux to avoid name collision with system commands.

#### Fixed
- PyInstaller build errors (stdout + stderr) are now captured and displayed on failure instead of being silenced.