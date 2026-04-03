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
from core.models import AppConfig, validate_config_dict
from core.utils import load_config
from core.paths import get_base_dir

# -----------------------------
# Base directory
# -----------------------------
BASE_DIR = get_base_dir()

CONFIG_FILE = (BASE_DIR / "config" / "config.yaml").resolve()

# -----------------------------
# Executable paths
# -----------------------------
GUI_EXE_PATH = (BASE_DIR / "core" / "gui.exe").resolve()
SERVER_EXE_PATH = (BASE_DIR / "server.exe").resolve()
UPDATE_EXE_PATH = (BASE_DIR / "update.exe").resolve()
APP_EXE_PATH = (BASE_DIR / "core" / "app.exe").resolve()
PORTCHECKER_EXE_PATH = (BASE_DIR / "core" / "PortChecker.exe").resolve()
PUBLISHER_EXE_PATH = (BASE_DIR / "core" / "publisher.exe").resolve()
REGISTRY_EXE_PATH = (BASE_DIR / "plugins" / "registry.exe").resolve()
APP_REGISTRY_FILE = (BASE_DIR / "plugins" / "PLUGIN_REGISTRY.json").resolve()
update_exe = (BASE_DIR / "update.exe").resolve()
update_new = (BASE_DIR / "update_new.exe").resolve()

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

def start_exe(path, name, hidden=False, gui_hidden=None):
    """Starts an executable in its own window or hidden.
    Optionally passes a --gui-hidden flag to the started process.
    """
    if not path.exists():
        if ALLOW_CLOSE:
            print(f"[-] Houston, we have a problem: {path} is missing. Did it run away?")
        return
    try:
        flags = subprocess.CREATE_NO_WINDOW if hidden else subprocess.CREATE_NEW_CONSOLE
        # Base command
        cmd = [path]
        # Optional flag
        if gui_hidden is not None:
            cmd.append(f"--gui-hidden")  # bool -> 0/1
        proc = subprocess.Popen(cmd, creationflags=flags)
        processes[name] = proc
        if ALLOW_CLOSE:
            print(f"{name} started{' (hidden)' if hidden else ''}, gui_hidden={gui_hidden}.")
    except Exception as e:
        if ALLOW_CLOSE:
            print(f"Error starting {name}: {e}")

def stop_all_processes():
    """Terminates all started processes including child processes (only when allow_close=True)."""
    if not ALLOW_CLOSE:
        return  # In background mode, do not stop anything

    print("\nTerminating all started processes...")
    for name, proc in processes.items():
        if proc.poll() is None:
            try:
                if sys.platform == "win32":
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
            print("[FAIL] Error: update.exe is still locked.")

def start_update_exe():
    proc = subprocess.Popen(
        [UPDATE_EXE_PATH],
        creationflags=subprocess.CREATE_NEW_CONSOLE
    )

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
    try:
        while True:
            cmd = input("\nGib 'exit' ein, um alle Programme zu beenden: ").strip().lower()
            if cmd == "exit":
                sys.exit(0) # atexit calls stop_all_processes
    except KeyboardInterrupt:
        sys.exit(0)
else:
    # AllowClose=False -> script exits itself, EXEs continue running quietly in the background
    pass