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
from core.models import AppConfig, validate_config_dict
from core.utils import load_config
from core.paths import get_base_dir

IS_WINDOWS = sys.platform == "win32"

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
        import os
        print()
        print("[WARN] Neither tmux nor screen found!")
        print("Without one of these, all processes will share this terminal.")
        print()
        print("  [1] Install tmux now (recommended)")
        print("  [2] Install screen now")
        print("  [3] Continue anyway (all in one terminal)")
        print("  [4] Abort")
        print()

        choice = input("Choice [1/2/3/4]: ").strip()
        tmux_cmd, screen_cmd = _detect_package_manager()

        if choice == "1":
            if tmux_cmd:
                print(f"\n=> {tmux_cmd}")
                ret = os.system(tmux_cmd)
                if ret == 0:
                    TMUX_PATH = shutil.which("tmux")
                    if TMUX_PATH:
                        SESSION_TOOL = "tmux"
                        print("[OK] tmux installed successfully.\n")
                    else:
                        print("[FAIL] tmux was installed but could not be found.")
                        sys.exit(1)
                else:
                    print("[FAIL] Installation failed. Please install manually.")
                    sys.exit(1)
            else:
                print("[FAIL] No package manager detected. Please install manually:")
                print("         Ubuntu/Debian : sudo apt install tmux")
                print("         Fedora/RHEL   : sudo dnf install tmux")
                print("         Arch Linux    : sudo pacman -S tmux")
                sys.exit(1)

        elif choice == "2":
            if screen_cmd:
                print(f"\n=> {screen_cmd}")
                ret = os.system(screen_cmd)
                if ret == 0:
                    SCREEN_PATH = shutil.which("screen")
                    if SCREEN_PATH:
                        SESSION_TOOL = "screen"
                        print("[OK] screen installed successfully.\n")
                    else:
                        print("[FAIL] screen was installed but could not be found.")
                        sys.exit(1)
                else:
                    print("[FAIL] Installation failed. Please install manually.")
                    sys.exit(1)
            else:
                print("[FAIL] No package manager detected. Please install manually:")
                print("         Ubuntu/Debian : sudo apt install screen")
                print("         Fedora/RHEL   : sudo dnf install screen")
                print("         Arch Linux    : sudo pacman -S screen")
                sys.exit(1)

        elif choice == "3":
            print("\n[OK] Continuing without tmux/screen...\n")

        else:
            print("\nAborted.")
            sys.exit(0)

# -----------------------------
# Base directory
# -----------------------------
BASE_DIR = get_base_dir()

CONFIG_FILE = (BASE_DIR / "config" / "config.yaml").resolve()

# -----------------------------
# Executable paths
# -----------------------------
EXE = ".exe" if sys.platform == "win32" else ""
BIN = ".exe" if sys.platform == "win32" else ".bin"

GUI_EXE_PATH = (BASE_DIR / "core" / f"gui{EXE}").resolve()
SERVER_EXE_PATH = (BASE_DIR / f"server{BIN}").resolve()
UPDATE_EXE_PATH = (BASE_DIR / f"update{EXE}").resolve()
APP_EXE_PATH = (BASE_DIR / "core" / f"app{EXE}").resolve()
PORTCHECKER_EXE_PATH = (BASE_DIR / "core" / f"PortChecker{EXE}").resolve()
PUBLISHER_EXE_PATH = (BASE_DIR / "core" / f"publisher{EXE}").resolve()
REGISTRY_EXE_PATH = (BASE_DIR / "plugins" / f"registry{EXE}").resolve()
APP_REGISTRY_FILE = (BASE_DIR / "plugins" / "PLUGIN_REGISTRY.json").resolve()
update_exe = (BASE_DIR / f"update{EXE}").resolve()
update_new = (BASE_DIR / f"update_new{EXE}").resolve()

# -----------------------------
# Load configuration
# -----------------------------
cfg = load_config(CONFIG_FILE)

# -----------------------------
# Settings
# -----------------------------
gui_cfg = cfg.get("GUI", {})
GUI_ENABLED = gui_cfg.get("Enable", False)
UPDATE_ENABLED = cfg.get("Update", {}).get("Enable", True)

console_cfg = cfg.get("Console", {})
CONSOLE_VISIBLE = console_cfg.get("visible", True)
ALLOW_CLOSE = console_cfg.get("allow_close", True)
LOG_LEVEL = console_cfg.get("log_level", 1)
CONTROL_METHOD = cfg.get("control_method", "DCS")
MINECRAFTSERVERAPI_ENABLED = cfg.get("MinecraftServerAPI", {}).get("Enable", True)

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

def start_exe(path, name, hidden=False, gui_hidden=None):
    """Starts an executable in its own window (Windows) or tmux/screen session (Linux)."""
    if not path.exists():
        if ALLOW_CLOSE:
            print(f"[-] Houston, we have a problem: {path} is missing. Did it run away?")
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
                ["tmux", "new-session", "-d", "-s", session_name] + cmd
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
                ["screen", "-dmS", session_name] + cmd
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
                print(f"{name} started in {SESSION_TOOL} session: {_sanitize_session_name(f'mc-{name}')}")
            else:
                print(f"{name} started{' (hidden)' if hidden else ''}, gui_hidden={gui_hidden}.")
    except Exception as e:
        if ALLOW_CLOSE:
            print(f"Error starting {name}: {e}")

def stop_all_processes():
    """Terminates all started processes including child processes (only when allow_close=True)."""
    if not ALLOW_CLOSE:
        return  # In background mode, do not stop anything

    print("\nTerminating all started processes...")

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
                print(f"{session_name} session terminated.")
            except Exception:
                pass
        linux_sessions.clear()

    # Kill Windows processes / fallback Linux processes
    for name, proc in processes.items():
        if proc is not None and proc.poll() is None:
            try:
                if IS_WINDOWS:
                    subprocess.run(f"taskkill /F /PID {proc.pid} /T", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    proc.terminate()
                print(f"{name} terminated.")
            except Exception:
                pass
    processes.clear()
    print("\nSnap! All processes have been dusted... (Thanos style).")

# -----------------------------
# Register cleanup on exit
# -----------------------------
atexit.register(stop_all_processes)

# =============================================================================
# UPDATE LOGIC
# =============================================================================
def replace_updater_if_exists():
    if update_new.exists():
        print("[..] New updater found. Installing...")
        try:
            update_new.replace(update_exe)
            print("[OK] Updater successfully updated.")
            time.sleep(0.5)
        except PermissionError:
            print(f"[FAIL] Error: {update_exe.name} is still locked.")

def start_update_exe():
    if IS_WINDOWS:
        proc = subprocess.Popen([UPDATE_EXE_PATH], creationflags=subprocess.CREATE_NEW_CONSOLE)
    elif SESSION_TOOL == "tmux":
        session_name = "mc-updater"
        subprocess.run(["tmux", "kill-session", "-t", session_name],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        proc = subprocess.Popen(
            ["tmux", "new-session", "-d", "-s", session_name, str(UPDATE_EXE_PATH)]
        )
        linux_sessions.append(session_name)
    elif SESSION_TOOL == "screen":
        session_name = "mc-updater"
        subprocess.run(["screen", "-X", "-S", session_name, "quit"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        proc = subprocess.Popen(
            ["screen", "-dmS", session_name, str(UPDATE_EXE_PATH)]
        )
        linux_sessions.append(session_name)
    else:
        proc = subprocess.Popen([str(UPDATE_EXE_PATH)])

    while proc.poll() is None:
        update_signal = BASE_DIR / "update_signal.tmp"
        if update_signal.exists():
            update_signal.unlink()
            return "kill"
        time.sleep(0.5)

    return proc.returncode

replace_updater_if_exists()

if UPDATE_ENABLED:
    time.sleep(0.5)
    print("Automatic updates are enabled.")

    while True:
        result = start_update_exe()

        if result is None:
            break

        if result == "kill":
            sys.exit(0)

        if result == 5:
            print("Continuing...")
            break

        else:
            print("\nUpdate has been installed.")
            print("Please restart the program now to apply the changes.")
            input("Press Enter to exit...")
            sys.exit(0)

else:
    print("Automatic updates are disabled.")

# =============================================================================
# REGISTRY LOGIC — scan and register all plugins
# =============================================================================
try:
    result = subprocess.run([REGISTRY_EXE_PATH])
    if result.returncode == 0:
        print("All apps registered.")
    else:
        print("Error")
except FileNotFoundError:
    print("File not found")
# =============================================================================

# -----------------------------
# Startup notice
# -----------------------------
if ALLOW_CLOSE:
    print("\nStarting programs... (start script visible)")

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

if APP_REGISTRY_FILE.exists():
    with APP_REGISTRY_FILE.open("r", encoding="utf-8") as f:
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

# -----------------------------
# Interactive control loop
# -----------------------------
if ALLOW_CLOSE:
    print("\nAll programs have been started.")

    # Show active sessions on Linux
    if not IS_WINDOWS and SESSION_TOOL and linux_sessions:
        print(f"\n--- Active {SESSION_TOOL} sessions ---")
        for s in linux_sessions:
            if SESSION_TOOL == "tmux":
                print(f"  tmux attach -t {s}")
            elif SESSION_TOOL == "screen":
                print(f"  screen -r {s}")
        print("-----------------------------------")

    try:
        while True:
            cmd = input("\nType 'exit' to stop all programs: ").strip().lower()
            if cmd == "exit":
                sys.exit(0) # atexit calls stop_all_processes
    except KeyboardInterrupt:
        sys.exit(0)
else:
    # AllowClose=False -> script exits itself, EXEs continue running quietly in the background
    pass