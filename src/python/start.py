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
import json
import shutil
import os
import asyncio
from datetime import datetime
from core.models import AppConfig, validate_config_dict
from core.utils import load_config
from core.paths import get_base_dir
import logging
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
SUFFIX = ".exe" if sys.platform == "win32" else ".bin"

GUI_EXE_PATH = (BASE_DIR / "core" / f"gui{SUFFIX}").resolve()
SERVER_EXE_PATH = (BASE_DIR / f"server{SUFFIX}").resolve()
UPDATE_EXE_PATH = (BASE_DIR / f"update{SUFFIX}").resolve()
APP_EXE_PATH = (BASE_DIR / "core" / f"app{SUFFIX}").resolve()
REGISTRY_EXE_PATH = (BASE_DIR / "plugins" / f"registry{SUFFIX}").resolve()
PLUGIN_UPDATER_EXE_PATH = (BASE_DIR / "plugins" / f"plugin_updater{SUFFIX}").resolve()
PLUGIN_REGISTRY_FILE = (BASE_DIR / "plugins" / "PLUGIN_REGISTRY.json").resolve()
update_new = (BASE_DIR / f"update_new{SUFFIX}").resolve()

# -----------------------------
# Load configuration
# -----------------------------
cfg = load_config(CONFIG_FILE)

if sys.platform != "win32" and cfg.get("show_sudo_warning", True):
    if os.geteuid() != 0:
        log.error("This script must be run as root on Linux to start the tool.")
        input("Press Enter to exit...")
        sys.exit(1)

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
                ret = os.system(tmux_cmd)
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
                ret = os.system(screen_cmd)
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
gui_cfg = cfg.get("gui", {})
GUI_ENABLED = gui_cfg.get("enabled", False)
UPDATE_ENABLED = cfg.get("update", {}).get("enabled", True)

console_cfg = cfg.get("console", {})
CONSOLE_VISIBLE = console_cfg.get("visible", True)
ALLOW_CLOSE = console_cfg.get("allow_close", True)
LOG_LEVEL = console_cfg.get("log_level", 1)
CONTROL_METHOD = cfg.get("control_method", "DCS")
MINECRAFTSERVERAPI_ENABLED = cfg.get("minecraft_server_api", {}).get("enabled", True)

AUTO_SHUTDOWN_ENABLED = cfg.get("shutdown", {}).get("enabled", True)
SHUTDOWN_DELAY_SECONDS = cfg.get("shutdown", {}).get("delay_seconds", 30)

# -----------------------------
# Process dictionary
# -----------------------------
processes = {}
linux_sessions = []  # Track tmux/screen session names

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

def _build_display_env_tmux():
    """Build -e flags for tmux new-session to forward display vars."""
    args = []
    for var in ("DISPLAY", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR"):
        val = os.environ.get(var)
        if val:
            args.extend(["-e", f"{var}={val}"])
    return args

def _build_display_env_screen():
    """Build env prefix for screen sessions to forward display vars."""
    env_args = []
    for var in ("DISPLAY", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR"):
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
            with open(log_file, "w") as lf:
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
    for name, proc in processes.items():
        if proc is not None and proc.poll() is None:
            try:
                if IS_WINDOWS:
                    subprocess.run(f"taskkill /F /PID {proc.pid} /T", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
        with open(log_file, "a") as lf:
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
            update_signal.unlink()
            log.info("Please restart the application.")
            time.sleep(2)
            return "kill"
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
# REGISTRY LOGIC — scan and register all plugins
# =============================================================================
try:
    result = subprocess.run([REGISTRY_EXE_PATH])
    if result.returncode == 0:
        log.info("All apps registered.")
    else:
        log.info("Error")
except FileNotFoundError:
    log.info("File not found")

# -------------------------------------------------------------------------
# Plugin Update Check (optional — skips if plugin_updater exe is missing)
# -------------------------------------------------------------------------
if PLUGIN_UPDATER_EXE_PATH.exists():
    try:
        subprocess.run([PLUGIN_UPDATER_EXE_PATH])
    except Exception as e:
        log.warning(f"Plugin updater failed: {e}")
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

PLUGIN_REGISTRY: list[AppConfig] = []

if PLUGIN_REGISTRY_FILE.exists():
    with PLUGIN_REGISTRY_FILE.open("r", encoding="utf-8") as f:
        data = json.load(f) 

    for item in data:
        if not isinstance(item, dict):
            raise ValueError("Each element in the registry must be a dict.")
        validate_config_dict(item)    
        PLUGIN_REGISTRY.append(AppConfig.from_dict(item))

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

RUNTIME_DIR = (BASE_DIR / "core" / "runtime").resolve()

shutdown_pending = False
shutdown_cancel_event = asyncio.Event()

# =============================================================================
# SHUTDOWN COUNTDOWN
# =============================================================================

async def shutdown_countdown():
    global shutdown_pending

    delay = SHUTDOWN_DELAY_SECONDS

    for remaining in range(delay, 0, -1):
        if shutdown_cancel_event.is_set():
            shutdown_cancel_event.clear()
            shutdown_pending = False
            log.info("\nCancelled shutdown.")
            return
        log.info(
            f"\rShutdown in {remaining} seconds... Press 'stop' to cancel."
        )
        await asyncio.sleep(1)
    log.info("\nShutting down now!")
    stop_all_processes()
    sys.exit(0)

# =============================================================================
# FILE WATCHER
# =============================================================================

async def check_and_run():
    global shutdown_pending
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    while True:
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
                    asyncio.create_task(shutdown_countdown())
        await asyncio.sleep(5)

# =============================================================================
# USER INPUT LOOP
# =============================================================================

async def command_loop():
    while True:
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

async def main():
    watcher = asyncio.create_task(check_and_run())
    try:
        await command_loop()
    finally:
        watcher.cancel()

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

else:
    # AllowClose=False -> script exits itself, EXEs continue running quietly
    pass