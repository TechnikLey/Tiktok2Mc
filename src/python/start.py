#!/usr/bin/env python3
# ==================================================
# start.py - Main launcher / process orchestrator
# ==================================================
# Entry point that manages the lifecycle of all tool
# components: updater, registry scan, Minecraft server,
# GUI, and registered plugins. Handles visibility
# levels, automatic updates, and graceful shutdown.
# ==================================================

import sys
import subprocess
import atexit
import time
import shutil
import threading
import os
import json
import enum
import urllib.error
import urllib.request
import shlex
import asyncio
from datetime import datetime
from core.models import AppConfig
from core.utils import load_config
from core.paths import get_base_dir
from core.api.server import DEFAULT_PORT
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S', stream=sys.stdout)
log = logging.getLogger(__name__)

IS_WINDOWS = sys.platform == "win32"

# -----------------------------
# Base directory
# -----------------------------
BASE_DIR = get_base_dir()

CONFIG_FILE = (BASE_DIR / "config" / "config.yaml").resolve()

# -----------------------------
# Executable paths
# -----------------------------
SUFFIX = ".exe" if IS_WINDOWS else ".bin"

SERVER_EXE_PATH = (BASE_DIR / f"server{SUFFIX}").resolve()
UPDATE_EXE_PATH = (BASE_DIR / f"update{SUFFIX}").resolve()
APP_EXE_PATH = (BASE_DIR / "core" / f"app{SUFFIX}").resolve()
GUI_EXE_PATH = (BASE_DIR / f"gui{SUFFIX}").resolve()
update_new = (BASE_DIR / f"update_new{SUFFIX}").resolve()

# -----------------------------
# Load configuration
# -----------------------------
try:
    cfg = load_config(CONFIG_FILE)
except Exception as e:
    log.error("Failed to load config: %s", e)
    input("Press Enter to exit...")
    sys.exit(1)

if sys.platform != "win32" and cfg.get("show_sudo_warning", True):
    if os.geteuid() != 0:
        log.error("This script must be run as root on Linux to start the tool.")
        input("Press Enter to exit...")
        sys.exit(1)

# -----------------------------
# Security warnings
# -----------------------------

# Warn if RCON password is not set
rcon_cfg = cfg.get("rcon", {})
if rcon_cfg.get("enabled", False) and not rcon_cfg.get("password", ""):
    log.warning(
        "RCON password is not set — "
        "the setup wizard will open so you can configure one. "
        "Without a password the tool cannot control your Minecraft server."
    )

# Warn if server_host exposes services to the network
if cfg.get("server_host") == "0.0.0.0":
    log.warning(
        "server_host is set to 0.0.0.0 — all services bind to all "
        "network interfaces and are accessible from other devices. "
        "Use 127.0.0.1 to restrict to localhost."
    )

# -----------------------------
# Linux: Detect tmux/screen
# -----------------------------
TMUX_PATH = None if IS_WINDOWS else shutil.which("tmux")
SCREEN_PATH = None if IS_WINDOWS else shutil.which("screen")
SESSION_TOOL = None

def _detect_package_manager():
    """Returns (install_cmd_tmux, install_cmd_screen) or (None, None)."""
    for pm, flag in [("apt", "install -y"), ("dnf", "install -y"), ("pacman", "-S --noconfirm"), ("zypper", "install -y")]:
        if shutil.which(pm):
            return (f"sudo {pm} {flag} tmux", f"sudo {pm} {flag} screen")
    return (None, None)

if not IS_WINDOWS:
    if TMUX_PATH:
        SESSION_TOOL = "tmux"
    elif SCREEN_PATH:
        SESSION_TOOL = "screen"
    else:
        log.warning("Neither tmux or screen found!")
        log.info("Without one of these, all processes will share this terminal.")
        log.info("  [1] Install tmux (recommended)")
        log.info("  [2] Install screen")
        log.info("  [3] Continue (all in one terminal)")
        log.info("  [4] Abort")

        choice = input("Choice [1/2/3/4]: ").strip()
        tmux_cmd, screen_cmd = _detect_package_manager()

        if choice == "1":
            if tmux_cmd:
                log.info(f"\n=> {tmux_cmd}")
                ret = subprocess.run(shlex.split(tmux_cmd)).returncode
                if ret == 0:
                    TMUX_PATH = shutil.which("tmux")
                    if TMUX_PATH:
                        SESSION_TOOL = "tmux"
                        log.info("tmux installed successfully.\n")
                    else:
                        log.info("[FAIL] tmux was installed but could not be found.")
                        sys.exit(1)
                else:
                    log.info("[FAIL] Installation failed. Please install manually.")
                    sys.exit(1)
            else:
                log.info("[FAIL] No package manager detected. Please install manually:")
                log.info("         Ubuntu/Debian : sudo apt install tmux")
                log.info("         Fedora/RHEL   : sudo dnf install tmux")
                log.info("         Arch Linux    : sudo pacman -S tmux")
                sys.exit(1)

        elif choice == "2":
            if screen_cmd:
                log.info(f"\n=> {screen_cmd}")
                ret = subprocess.run(shlex.split(screen_cmd)).returncode
                if ret == 0:
                    SCREEN_PATH = shutil.which("screen")
                    if SCREEN_PATH:
                        SESSION_TOOL = "screen"
                        log.info("screen installed successfully.\n")
                    else:
                        log.info("[FAIL] screen was installed but could not be found.")
                        sys.exit(1)
                else:
                    log.info("[FAIL] Installation failed. Please install manually.")
                    sys.exit(1)
            else:
                log.info("[FAIL] No package manager detected. Please install manually:")
                log.info("         Ubuntu/Debian : sudo apt install screen")
                log.info("         Fedora/RHEL   : sudo dnf install screen")
                log.info("         Arch Linux    : sudo pacman -S screen")
                sys.exit(1)

        elif choice == "3":
            log.info("\n[OK] Continuing without tmux/screen...\n")

        else:
            log.info("\nAborted.")
            sys.exit(0)

# -----------------------------
# Settings
# -----------------------------
UPDATE_ENABLED = cfg.get("update", {}).get("enabled", True)

console_cfg = cfg.get("console", {})
CONSOLE_VISIBLE = console_cfg.get("visible", True)
ALLOW_CLOSE = console_cfg.get("allow_close", True)
LOG_LEVEL = console_cfg.get("log_level", 1)
CONTROL_METHOD = cfg.get("control_method", "DCS")
MINECRAFTSERVERAPI_ENABLED = cfg.get("minecraft_server_api", {}).get("enabled", True)

AUTO_SHUTDOWN_ENABLED = cfg.get("shutdown", {}).get("enabled", True)
SHUTDOWN_DELAY_SECONDS = cfg.get("shutdown", {}).get("delay_seconds", 30)

# Forward core system settings to child processes so plugins do not
# need to read the global config for basic networking values.
os.environ["SERVER_HOST"] = cfg.get("server_host", "127.0.0.1")

# -----------------------------
# Process dictionary
# -----------------------------
processes = {}
linux_sessions = []  # Track tmux/screen session names
_restart_in_progress = False

# -----------------------------
# Process management (start, stop, visibility)
# -----------------------------
def get_visibility(required_level):
    """
    Determines whether a window should be hidden based on config settings.
    Returns True if the window should be hidden.
    """
    if not CONSOLE_VISIBLE or not ALLOW_CLOSE:
        return True  # Always hide when master switches are off
    
    return LOG_LEVEL < required_level

def _sanitize_session_name(name):
    return name.replace(" ", "-").replace("/", "-").lower()

_FORWARDED_ENV_VARS = ("DISPLAY", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR", "SERVER_HOST")


def _build_display_env_tmux():
    """Build -e flags for tmux new-session to forward display vars."""
    args = []
    for var in _FORWARDED_ENV_VARS:
        val = os.environ.get(var)
        if val:
            args.extend(["-e", f"{var}={val}"])
    return args


def _build_display_env_screen():
    """Build env prefix for screen sessions to forward display vars."""
    env_args = []
    for var in _FORWARDED_ENV_VARS:
        val = os.environ.get(var)
        if val:
            env_args.append(f"{var}={val}")
    if env_args:
        return ["env"] + env_args
    return []

def start_exe(path, name, hidden=False, gui_hidden=None):
    """Starts an executable in its own window (Windows) or tmux/screen session (Linux)."""
    if not path.exists():
        if ALLOW_CLOSE:
            log.info(f"[-] Houston, we have a problem: {path} is missing. Did it run away?")
        return
    try:
        cmd = [str(path)]
        if gui_hidden is not None:
            cmd.append("--gui-hidden")

        if IS_WINDOWS:
            kwargs = {}
            flags = subprocess.CREATE_NO_WINDOW if hidden else subprocess.CREATE_NEW_CONSOLE
            kwargs["creationflags"] = flags
            proc = subprocess.Popen(cmd, **kwargs)
            processes[name] = proc
        elif SESSION_TOOL == "tmux":
            session_name = _sanitize_session_name(f"mc-{name}")
            # Kill stale session with same name if it exists
            subprocess.run(
                ["tmux", "kill-session", "-t", session_name],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            subprocess.Popen(
                ["tmux", "new-session", "-d", "-s", session_name] + _build_display_env_tmux() + cmd
            )
            linux_sessions.append(session_name)
            processes[name] = None  # tracked by session name
        elif SESSION_TOOL == "screen":
            session_name = _sanitize_session_name(f"mc-{name}")
            subprocess.run(
                ["screen", "-X", "-S", session_name, "quit"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            subprocess.Popen(
                ["screen", "-dmS", session_name] + _build_display_env_screen() + cmd
            )
            linux_sessions.append(session_name)
            processes[name] = None
        else:
            # Fallback: run in background, redirect to log file
            log_dir = BASE_DIR / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / f"{_sanitize_session_name(name)}.log"
            with open(log_file, "w", encoding="utf-8") as lf:
                proc = subprocess.Popen(cmd, stdout=lf, stderr=lf)
            processes[name] = proc

        if ALLOW_CLOSE:
            if SESSION_TOOL and not IS_WINDOWS:
                log.info(f"{name} started in {SESSION_TOOL} session: {_sanitize_session_name(f'mc-{name}')}")
            else:
                log.info(f"{name} started{' (hidden)' if hidden else ''}, gui_hidden={gui_hidden}.")
    except Exception as e:
        if ALLOW_CLOSE:
            log.info(f"Error starting {name}: {e}")

def stop_process(name):
    """Stop a single process or session by name."""
    proc = processes.get(name)
    session_name = _sanitize_session_name(f"mc-{name}")

    # Try Linux session first
    if not IS_WINDOWS and SESSION_TOOL:
        try:
            if SESSION_TOOL == "tmux":
                subprocess.run(
                    ["tmux", "kill-session", "-t", session_name],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
            elif SESSION_TOOL == "screen":
                subprocess.run(
                    ["screen", "-X", "-S", session_name, "quit"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
            if session_name in linux_sessions:
                linux_sessions.remove(session_name)
            log.info(f"{name} session terminated.")
            if name in processes:
                del processes[name]
            return True
        except Exception:
            pass

    # Fallback: direct process
    if proc is not None and proc.poll() is None:
        try:
            if IS_WINDOWS:
                subprocess.run(["taskkill", "/F", "/PID", str(proc.pid), "/T"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                proc.terminate()
            log.info(f"{name} terminated.")
            if name in processes:
                del processes[name]
            return True
        except Exception as e:
            log.info(f"Failed to terminate process {name}: {e}")
    elif name in processes:
        del processes[name]
    return False


def start_plugin_process(name, path_str, level=2, ics=False, gui_hidden=None):
    """Start a single plugin process by name, mirroring the startup logic."""
    from pathlib import Path
    p = Path(path_str)
    if not p.exists():
        log.warning(f"Plugin executable not found: {p}")
        return False

    hidden = get_visibility(level)
    try:
        cmd = [str(p)]
        if gui_hidden is not None:
            cmd.append("--gui-hidden")

        if IS_WINDOWS:
            kwargs = {}
            flags = subprocess.CREATE_NO_WINDOW if hidden else subprocess.CREATE_NEW_CONSOLE
            kwargs["creationflags"] = flags
            proc = subprocess.Popen(cmd, **kwargs)
            processes[name] = proc
        elif SESSION_TOOL == "tmux":
            session_name = _sanitize_session_name(f"mc-{name}")
            subprocess.run(
                ["tmux", "kill-session", "-t", session_name],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            subprocess.Popen(
                ["tmux", "new-session", "-d", "-s", session_name] + _build_display_env_tmux() + cmd
            )
            linux_sessions.append(session_name)
            processes[name] = None
        elif SESSION_TOOL == "screen":
            session_name = _sanitize_session_name(f"mc-{name}")
            subprocess.run(
                ["screen", "-X", "-S", session_name, "quit"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            subprocess.Popen(
                ["screen", "-dmS", session_name] + _build_display_env_screen() + cmd
            )
            linux_sessions.append(session_name)
            processes[name] = None
        else:
            log_dir = BASE_DIR / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / f"{_sanitize_session_name(name)}.log"
            with open(log_file, "w", encoding="utf-8") as lf:
                proc = subprocess.Popen(cmd, stdout=lf, stderr=lf)
            processes[name] = proc

        log.info(f"Plugin {name} started{' (hidden)' if hidden else ''}.")
        return True
    except Exception as e:
        log.error(f"Failed to start plugin {name}: {e}")
        return False


def stop_all_processes():
    """Terminates all started processes including child processes (only when allow_close=True)."""
    if not ALLOW_CLOSE:
        return  # In background mode, do not stop anything

    log.info("\nTerminating all started processes...")

    # Kill tmux/screen sessions on Linux
    if not IS_WINDOWS and SESSION_TOOL and linux_sessions:
        for session_name in linux_sessions:
            try:
                if SESSION_TOOL == "tmux":
                    subprocess.run(
                        ["tmux", "kill-session", "-t", session_name],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )
                elif SESSION_TOOL == "screen":
                    subprocess.run(
                        ["screen", "-X", "-S", session_name, "quit"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )
                log.info(f"{session_name} session terminated.")
            except Exception as e:
                log.info(f"Failed to terminate session {session_name}: {e}")
        linux_sessions.clear()

    # Kill Windows processes / fallback Linux processes
    for name, proc in list(processes.items()):
        if proc is not None and proc.poll() is None:
            try:
                if IS_WINDOWS:
                    subprocess.run(["taskkill", "/F", "/PID", str(proc.pid), "/T"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    proc.terminate()
                log.info(f"{name} terminated.")
            except Exception as e:
                log.info(f"Failed to terminate process {name}: {e}")
    processes.clear()
    log.info("\nSnap! All processes have been dusted... (Thanos style).")

# -----------------------------
# Register cleanup on exit
# -----------------------------
atexit.register(stop_all_processes)

# =============================================================================
# UPDATE LOGIC
# =============================================================================
def replace_updater_if_exists():
    if update_new.exists():
        log.info("[..] New updater found. Installing...")
        try:
            update_new.replace(UPDATE_EXE_PATH)
            log.info("Updater successfully updated.")
            time.sleep(0.5)
        except PermissionError:
            log.info(f"[FAIL] Error: {UPDATE_EXE_PATH.name} is still locked.")

def start_UPDATE_EXE_PATH():
    """Run updater synchronously — must wait for exit code, so no tmux/screen here."""
    cmd = [str(UPDATE_EXE_PATH), "--auto"]
    log_dir = BASE_DIR / "logs" / "update_logs"
    if IS_WINDOWS:
        proc = subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_CONSOLE)
    else:
        log.info("Starting updater. This may take a few minutes. Please do not close or interrupt the program...")
        log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
        log_file = log_dir / f"updater_{timestamp}.log"
        with open(log_file, "a", encoding="utf-8") as lf:
            proc = subprocess.Popen(
                cmd,
                stdout=lf,
                stderr=lf,
                preexec_fn=os.setsid
            )
    update_cfg = cfg.get("update", {})
    max_logs = update_cfg.get("max_update_logs", 20)
    try:
        max_logs = int(max_logs)
    except Exception as e:
        log.warning(f"Invalid max_update_logs value: {e}. Using default 20.")
        max_logs = 20
    if max_logs < 0:
        if max_logs != -1:
            log.warning(f"Negative max_update_logs ({max_logs}), treating as -1 (keep all).")
        max_logs = -1

    if max_logs >= 0:
        logs = sorted(log_dir.glob("updater_*.log"), key=lambda f: f.stat().st_mtime, reverse=True)
        for old_log in logs[max_logs:]:
            try:
                old_log.unlink()
            except Exception as e:
                log.warning(f"Failed to delete old log {old_log}: {e}")

    while proc.poll() is None:
        update_signal = BASE_DIR / "update_signal.tmp"
        if update_signal.exists():
            try:
                content = update_signal.read_text().strip()
                if content == "kill":
                    update_signal.unlink()
                    log.info("Please restart the application.")
                    time.sleep(2)
                    return "kill"
            except (OSError, IOError):
                pass

        # Also check API-based kill signal
        try:
            with urllib.request.urlopen(
                f"{_API_BASE_URL}/updater/signal", timeout=2
            ) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    if data.get("signal") == "kill":
                        # Acknowledge by clearing the signal
                        req = urllib.request.Request(
                            f"{_API_BASE_URL}/updater/signal",
                            method="DELETE",
                        )
                        urllib.request.urlopen(req, timeout=2)
                        log.info("Please restart the application.")
                        time.sleep(2)
                        return "kill"
        except Exception:
            pass

        time.sleep(1)

    return proc.returncode

replace_updater_if_exists()

if UPDATE_ENABLED:
    time.sleep(0.5)
    log.info("Automatic updates are enabled.")

    while True:
        result = start_UPDATE_EXE_PATH()

        if result is None:
            break

        if result == "kill":
            sys.exit(0)

        if result == 5:
            log.info("Continuing...")
            break

        else:
            log.info("\nUpdate has been installed.")
            log.info("Please restart the program now to apply the changes.")
            input("Press Enter to exit...")
            sys.exit(0)

else:
    log.info("Automatic updates are disabled.")

# =============================================================================
# API SERVER — start in background before anything needs it
# =============================================================================

_API_PORT = DEFAULT_PORT
_API_BASE_URL = f"http://127.0.0.1:{_API_PORT}/api/v1"

_uvicorn_server = None


def _start_api_server():
    """Run the FastAPI server in a background daemon thread."""
    global _uvicorn_server
    import uvicorn
    from core.api import create_app

    try:
        app = create_app()
        config = uvicorn.Config(app, host="127.0.0.1", port=_API_PORT, log_level="warning")
        _uvicorn_server = uvicorn.Server(config)
        _uvicorn_server.run()
    except Exception:
        log.exception("API server failed to start")


def _stop_api_server():
    """Stop the API server gracefully."""
    global _uvicorn_server
    if _uvicorn_server:
        _uvicorn_server.should_exit = True
        time.sleep(1)


_api_thread = threading.Thread(target=_start_api_server, daemon=True)
_api_thread.start()
log.info("API server starting on 127.0.0.1:%d ...", _API_PORT)

# Wait for the API to become reachable (poll health endpoint, max ~10 s)
_api_ready = False
for _ in range(20):
    try:
        with urllib.request.urlopen(
            f"{_API_BASE_URL}/health", timeout=1
        ) as resp:
            if resp.status == 200:
                _api_ready = True
                break
    except (urllib.error.URLError, urllib.error.HTTPError, OSError):
        pass
    time.sleep(0.5)

if _api_ready:
    log.info("API server ready.")

    # Check for plugin updates
    try:
        with urllib.request.urlopen(
            f"{_API_BASE_URL}/plugins/updates", timeout=5
        ) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("updates_available", 0) > 0:
                    log.info(
                        "[UPDATES] %d plugin update(s) available:",
                        data["updates_available"],
                    )
                    for p in data.get("plugins", []):
                        if p.get("update_available") and p.get("display_name"):
                            log.info(
                                "  - %s: %s -> %s",
                                p["display_name"],
                                p.get("current_version", "?"),
                                p.get("latest_version", "?"),
                            )
    except Exception:
        pass
else:
    log.warning(
        "API server not reachable within 10 s — "
        "continuing without plugin support"
    )

# =============================================================================
# Plugin discovery via PluginLauncher
# =============================================================================

# -----------------------------
# Startup notice
# -----------------------------
if ALLOW_CLOSE:
    log.info("\nStarting programs... (start script visible)")

# -----------------------------
# Launch programs (modular system with visibility levels)
# -----------------------------
# Level 0: Disables everything, including all GUI elements.
# Level 1: Visible from log_level 1 (nothing visible) — GUI elements still active
# Level 2: Visible from log_level 2 (main programs)
# Level 3: Visible from log_level 3 (background services)
# Level 4: Visible from log_level 4 (debug / dev)
# Level 5: Overrides all log_level and enable values with 4 / True
# ICS = Interface Control System
# DCS = Direct Control System

from core.api.launcher import PluginLauncher

_launcher = PluginLauncher()
PLUGIN_REGISTRY: list[AppConfig] = _launcher.get_plugins()

GUI_ENABLED = cfg.get("gui", {}).get("enabled", False)

BUILTIN_REGISTRY: list[AppConfig] = [
    AppConfig(name="App", path=APP_EXE_PATH, enable=True, level=2, ics=False),
    AppConfig(name="Minecraft Server", path=SERVER_EXE_PATH, enable=True, level=2, ics=False),
    AppConfig(name="GUI", path=GUI_EXE_PATH, enable=GUI_ENABLED, level=2, ics=False),
]

for registry in (BUILTIN_REGISTRY, PLUGIN_REGISTRY):
    for app in registry:
        if LOG_LEVEL == 0:
            start_exe(
                path=app.path,
                name=app.name,
                hidden=True,
                gui_hidden=True
            )
        elif LOG_LEVEL == 5:
            start_exe(
                path=app.path,
                name=app.name,
                hidden=False
            )
        else:
            if app.ics and CONTROL_METHOD == "DCS" and app.enable:
                start_exe(
                    path=app.path,
                    name=app.name,
                    hidden=get_visibility(app.level),
                    gui_hidden=True
                )
            elif app.enable:
                start_exe(
                    path=app.path,
                    name=app.name,
                    hidden=get_visibility(app.level)
                )

# Show overlay URLs for OBS browser sources
overlay_ports = []
for app in PLUGIN_REGISTRY:
    if app.port > 0:
        overlay_ports.append((app.name, app.port))
if overlay_ports:
    log.info("\n[OVERLAYS] Add these URLs as OBS Browser Sources:")
    for name, port in sorted(overlay_ports, key=lambda x: x[1]):
        log.info(f"  {name}: http://localhost:{port}")

# =============================================================================
# STATE
# =============================================================================

class ShutdownState(str, enum.Enum):
    IDLE = "idle"
    COUNTDOWN = "countdown"
    SHUTTING_DOWN = "shutting_down"
    COMPLETE = "complete"

RUNTIME_DIR = (BASE_DIR / "core" / "runtime").resolve()

shutdown_pending = False
_shutdown_state = ShutdownState.IDLE
_shutdown_countdown_task: asyncio.Task | None = None
shutdown_cancel_event = asyncio.Event()
shutdown_complete_event: asyncio.Event | None = None


def _write_shutdown_status(remaining: int | None) -> None:
    """Write current countdown state to a file the API can serve."""
    try:
        status_file = RUNTIME_DIR / "shutdown_status"
        data = {"remaining": remaining, "state": _shutdown_state.value}
        status_file.write_text(json.dumps(data), encoding="utf-8")
    except Exception:
        pass


def _clear_shutdown_status() -> None:
    try:
        status_file = RUNTIME_DIR / "shutdown_status"
        status_file.unlink(missing_ok=True)
    except Exception:
        pass


# =============================================================================
# SHUTDOWN COUNTDOWN
# =============================================================================

async def shutdown_countdown():
    global shutdown_pending, _shutdown_state

    delay = SHUTDOWN_DELAY_SECONDS
    _shutdown_state = ShutdownState.COUNTDOWN

    for remaining in range(delay, 0, -1):
        if _shutdown_state != ShutdownState.COUNTDOWN:
            # State changed externally (e.g. shutdown_now was triggered)
            return
        if shutdown_cancel_event.is_set():
            shutdown_cancel_event.clear()
            shutdown_pending = False
            _shutdown_state = ShutdownState.IDLE
            _clear_shutdown_status()
            log.info("\nCancelled shutdown.")
            return
        log.info(
            f"\rShutdown in {remaining} seconds... Press 'stop' to cancel."
        )
        _write_shutdown_status(remaining)
        await asyncio.sleep(1)
    log.info("\nShutting down now!")
    _shutdown_state = ShutdownState.SHUTTING_DOWN
    _write_shutdown_status(0)
    stop_all_processes()
    _stop_api_server()
    _shutdown_state = ShutdownState.COMPLETE
    _clear_shutdown_status()
    sys.stdin.close()
    os._exit(0)

# =============================================================================
# FILE WATCHER
# =============================================================================

async def check_and_run():
    global shutdown_pending, _shutdown_state, _shutdown_countdown_task
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    while True:
        if shutdown_complete_event is not None and shutdown_complete_event.is_set():
            return
        for file in list(RUNTIME_DIR.iterdir()):
            if not file.is_file():
                continue
            name = file.stem.lower()
            file.unlink(missing_ok=True)
            if name == "shutdown":
                if not AUTO_SHUTDOWN_ENABLED:
                    log.info("Shutdown signal detected, but Auto shutdown is disabled.")
                    continue
                if not shutdown_pending:
                    shutdown_pending = True
                    log.info(f"\nShutdown detected. System will shut down in {SHUTDOWN_DELAY_SECONDS} seconds.")
                    _shutdown_countdown_task = asyncio.create_task(shutdown_countdown())
            elif name == "shutdown_now":
                log.info("\nImmediate shutdown signal detected.")
                _shutdown_state = ShutdownState.SHUTTING_DOWN
                if _shutdown_countdown_task is not None:
                    _shutdown_countdown_task.cancel()
                    _shutdown_countdown_task = None
                _write_shutdown_status(0)
                stop_all_processes()
                _stop_api_server()
                _shutdown_state = ShutdownState.COMPLETE
                _clear_shutdown_status()
                sys.stdin.close()
                os._exit(0)
            elif name == "restart":
                log.info("\nRestart signal detected. Requesting clean restart...")
                restart_app()
                return
            elif name.startswith("plugin_start_"):
                plugin_name = name[len("plugin_start_"):]
                log.info(f"\nPlugin start signal detected for '{plugin_name}'.")
                try:
                    # Re-fetch plugin details from API
                    with urllib.request.urlopen(
                        f"{_API_BASE_URL}/plugins/{plugin_name}", timeout=3
                    ) as resp:
                        if resp.status == 200:
                            data = json.loads(resp.read().decode("utf-8"))
                            path = data.get("path", "")
                            level = data.get("level", 2)
                            ics = data.get("ics", False)
                            gui_h = True if ics and CONTROL_METHOD == "DCS" else None
                            start_plugin_process(plugin_name, path, level=level, ics=ics, gui_hidden=gui_h)
                        else:
                            log.warning(f"API returned {resp.status} for plugin '{plugin_name}'.")
                except Exception as exc:
                    log.warning(f"Failed to start plugin '{plugin_name}' from signal: {exc}")
            elif name == "shutdown_cancel":
                log.info("\nShutdown cancel signal detected.")
                shutdown_cancel_event.set()
            elif name.startswith("plugin_stop_"):
                plugin_name = name[len("plugin_stop_"):]
                log.info(f"\nPlugin stop signal detected for '{plugin_name}'.")
                stop_process(plugin_name)
        await asyncio.sleep(5)

# =============================================================================
# USER INPUT LOOP
# =============================================================================

async def command_loop():
    while True:
        if shutdown_complete_event is not None and shutdown_complete_event.is_set():
            break
        cmd = await asyncio.to_thread(
            input,
            "\nType 'exit' to stop all programs ('help' for commands): "
        )
        cmd = cmd.strip().lower()
        if cmd == "help":
            log.info("\nAvailable commands:")
            log.info("  exit  - Stop all programs and close")
            log.info("  stop  - Cancel active shutdown countdown")
        elif cmd == "exit":
            break
        elif cmd == "stop":
            shutdown_cancel_event.set()

# =============================================================================
# MAIN
# =============================================================================

def restart_app():
    """Restart the application — cross-platform.

    This implementation follows PyInstaller best practices and Python
    standard patterns for process restart:

    - Windows: Uses subprocess.Popen with CREATE_NEW_CONSOLE to spawn
      a fully independent new process, then exits the current process.
      This ensures the PyInstaller bootloader initializes correctly in
      the new process.

    - Linux: Uses os.execv to replace the current process image in-place,
      which is the standard Unix pattern for process restart.

    Both platforms preserve sys.argv and working directory.
    """
    global _restart_in_progress
    if _restart_in_progress:
        return
    _restart_in_progress = True

    log.info("\nPerforming restart...")
    _stop_api_server()
    stop_all_processes()
    time.sleep(3)

    if getattr(sys, "frozen", False):
        executable = sys.executable
        args = [executable] + sys.argv[1:]
    else:
        executable = sys.executable
        args = [executable, os.path.abspath(__file__)] + sys.argv[1:]

    if IS_WINDOWS:
        try:
            proc = subprocess.Popen(
                args,
                cwd=str(BASE_DIR),
                creationflags=subprocess.CREATE_NEW_CONSOLE,
                close_fds=True,
            )
            time.sleep(3)
            if proc.poll() is None:
                os._exit(0)
            else:
                log.error(f"New process exited immediately with code: {proc.returncode}")
                _restart_in_progress = False
                sys.exit(1)
        except Exception as exc:
            log.error("Restart failed: %s", exc)
            _restart_in_progress = False
            sys.exit(1)
    else:
        try:
            os.chdir(str(BASE_DIR))
            os.execv(executable, args)
        except OSError:
            try:
                subprocess.Popen(
                    args,
                    cwd=str(BASE_DIR),
                    start_new_session=True,
                    close_fds=True,
                )
                os._exit(0)
            except Exception as exc:
                log.error("Restart failed: %s", exc)
                _restart_in_progress = False
                sys.exit(1)


async def main():
    global shutdown_complete_event
    shutdown_complete_event = asyncio.Event()

    watcher = asyncio.create_task(check_and_run())
    cmd_task = asyncio.create_task(command_loop())
    shutdown_wait = asyncio.create_task(shutdown_complete_event.wait())

    done, pending = await asyncio.wait(
        [cmd_task, shutdown_wait],
        return_when=asyncio.FIRST_COMPLETED,
    )

    for task in pending:
        task.cancel()
    watcher.cancel()

    await asyncio.sleep(0.1)
    sys.stdin.close()


# =============================================================================
# EVENT DEFINITIONS (ENTRY POINT)
# =============================================================================

if ALLOW_CLOSE:
    log.info("\nAll programs have been started.")

    # Show active sessions on Linux immediately (not after exit)
    if not IS_WINDOWS and SESSION_TOOL and linux_sessions:
        log.info(f"\n--- Active {SESSION_TOOL} sessions ---")
        for s in linux_sessions:
            if SESSION_TOOL == "tmux":
                log.info(f"  tmux attach -t {s}")
            elif SESSION_TOOL == "screen":
                log.info(f"  screen -r {s}")
        log.info("-----------------------------------")

    asyncio.run(main())

    # Clean up all child processes (atexit handlers are skipped by os._exit)
    stop_all_processes()
    _stop_api_server()

    # Force exit — asyncio.to_thread(input) leaves a non-daemon thread
    # pool thread that keeps the process alive after the event loop finishes.
    sys.stdin.close()
    os._exit(0)

else:
    # AllowClose=False -> script exits itself, EXEs continue running quietly
    pass