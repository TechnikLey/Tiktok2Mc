#!/usr/bin/env python3
# ==================================================
# start.py - TikTok2Mc lifecycle supervisor
# ==================================================
# Entry point that owns the lifecycle of all tool
# components: updater, API server, Minecraft server,
# GUI, overlay, bridge, and plugins.
#
# Architecture
# ------------
# - start.py runs a single asyncio event loop.
# - The FastAPI/uvicorn API server runs as an asyncio
#   task in that loop (not a daemon thread).
# - Child processes are managed by ProcessSupervisor.
# - The GUI is a "shell" process and survives backend
#   restart.
# - REST endpoints dispatch commands to the supervisor
#   directly; file-based signal files are still honoured
#   as a fallback.
# ==================================================

import sys
import os
import subprocess
import atexit
import time
import shutil
import threading
import json
import enum
import urllib.error
import urllib.parse
import urllib.request
import shlex
import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

# multiprocessing is not used by this module, but pre-importing it with
# freeze_support() keeps PyInstaller happy if a downstream dependency
# instantiates a ProcessPool.
import multiprocessing
multiprocessing.freeze_support()

# Pre-import uvicorn so the API server task does not trigger a late load of
# _multiprocessing from a non-main thread.
try:
    import uvicorn
    from core.api import create_app
except Exception as _exc:  # pragma: no cover
    import logging as _logging
    _pre_log = _logging.getLogger("start.preimport")
    _pre_log.warning("Failed to pre-import uvicorn/core.api: %s", _exc)

from core.models import AppConfig
from core.utils import load_config
from core.paths import get_base_dir, get_root_dir
from core.api.server import DEFAULT_PORT
from core.sandbox import PluginSandbox
from core.lifecycle import (
    ProcessSupervisor,
    get_supervisor,
    SupervisorState,
    ProcessState,
    shutdown_cancel_event,
)
from core.api.eventbus import event_bus
from core.api.models import API_VERSION
from core.port_scanner import (
    PortPolicy,
    scan_bind_ports,
    build_resolved_map,
    write_runtime_file,
    ports_to_env,
    persist_to_config,
)
from core.api.launcher import PluginLauncher
from core.logger import initialize_logging, install_global_exception_hook, start_heartbeat, handle_unhandled_exception
from core.health_monitor import get_health_monitor, HealthState, HealthMonitor
from core.crash_manager import CrashManager
from core.error_codes import LIFECYCLE_0001, CORE_0001
from core.diagnostics import generate_diagnostics_report, generate_diagnostics_markdown
from core.validation_framework import run_startup_validation, validate_runtime, validate_shutdown, ValidationSuite

log = initialize_logging(__name__)

IS_WINDOWS = sys.platform == "win32"


def _safe_input(prompt: str = "") -> str:
    """Wrapper around input() that handles EOFError (no TTY)."""
    try:
        return input(prompt)
    except EOFError:
        log.warning("No interactive terminal available — treating input as empty/cancel")
        return ""


def _input_confirm_exit(prompt: str = "") -> None:
    """Call input() and exit; handle EOFError gracefully."""
    try:
        input(prompt)
    except EOFError:
        pass
    sys.exit(1)

SUFFIX = ".exe" if IS_WINDOWS else ".bin"

# Global crash manager and health monitor
crash_mgr = CrashManager("start")
_health_mon = get_health_monitor()

# Runtime validation configuration
_RUNTIME_VALIDATION_INTERVAL = 30.0
_RUNTIME_HEARTBEAT_TIMEOUT = 120.0

# -----------------------------
# Base directory / config
# -----------------------------
BASE_DIR = get_base_dir()
ROOT_DIR = get_root_dir()
CONFIG_FILE = (ROOT_DIR / "config" / "config.yaml").resolve()

# -----------------------------
# Executable paths
# -----------------------------
APP_EXE_PATH = (BASE_DIR / "core" / f"app{SUFFIX}").resolve()
SERVER_EXE_PATH = (BASE_DIR / "core" / f"server{SUFFIX}").resolve()
UPDATE_EXE_PATH = (BASE_DIR / f"update{SUFFIX}").resolve()
GUI_EXE_PATH = (BASE_DIR / "core" / f"gui{SUFFIX}").resolve()
OVERLAY_EXE_PATH = (BASE_DIR / "core" / f"overlay{SUFFIX}").resolve()
update_new = (BASE_DIR / f"update_new{SUFFIX}").resolve()

# -----------------------------
# Load configuration
# -----------------------------
try:
    cfg = load_config(CONFIG_FILE)
except Exception as e:
    log.error("Failed to load config: %s", e)
    _input_confirm_exit("Press Enter to exit...")

if sys.platform != "win32" and cfg.get("show_sudo_warning", True):
    if os.geteuid() != 0:
        if sys.stdin.isatty():
            log.error("This script must be run as root on Linux to start the tool.")
            _input_confirm_exit("Press Enter to exit...")
        else:
            log.warning("Not running as root. Continuing anyway (no TTY). Some features may fail.")

# -----------------------------
# Plugin sandbox
# -----------------------------
_sandbox_cfg = cfg.get("plugin_sandbox", {})
_plugin_sandbox = PluginSandbox(
    max_memory_mb=_sandbox_cfg.get("max_memory_mb"),
    max_cpu_time=_sandbox_cfg.get("max_cpu_time"),
    max_files=_sandbox_cfg.get("max_files", 256),
    max_processes=_sandbox_cfg.get("max_processes", 32),
    priority_class=_sandbox_cfg.get("priority_class", "below_normal"),
) if _sandbox_cfg.get("enabled", False) else None

# -----------------------------
# Settings
# -----------------------------
UPDATE_ENABLED = cfg.get("update", {}).get("enabled", True)
console_cfg = cfg.get("console", {})
CONSOLE_VISIBLE = console_cfg.get("visible", True)
ALLOW_CLOSE = console_cfg.get("allow_close", True)
LOG_LEVEL = console_cfg.get("log_level", 1)
CONTROL_METHOD = cfg.get("control_method", "DCS")
AUTO_SHUTDOWN_ENABLED = cfg.get("shutdown", {}).get("enabled", True)
SHUTDOWN_DELAY_SECONDS = cfg.get("shutdown", {}).get("delay_seconds", 30)

GUI_ENABLED = cfg.get("gui", {}).get("enabled", False)
OVERLAY_ENABLED = cfg.get("overlay", {}).get("enabled", True)

os.environ["SERVER_HOST"] = cfg.get("server_host", "127.0.0.1")

# -----------------------------
# Linux session tool detection
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

        if not sys.stdin.isatty():
            log.info("No interactive terminal — continuing without tmux/screen.")
            SESSION_TOOL = None
        else:
            log.info("Without one of these, all processes will share this terminal.")
            log.info("  [1] Install tmux (recommended)")
            log.info("  [2] Install screen")
            log.info("  [3] Continue (all in one terminal)")
            log.info("  [4] Abort")

            choice = _safe_input("Choice [1/2/3/4]: ").strip()
            tmux_cmd, screen_cmd = _detect_package_manager()

            if choice == "1":
                if tmux_cmd:
                    log.info("\n=> %s", tmux_cmd)
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
                    log.info("\n=> %s", screen_cmd)
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
# Port scanner
# -----------------------------
_PORT_RUNTIME_DIR = (ROOT_DIR / "core" / "runtime").resolve()
_port_policy = PortPolicy.from_config(cfg)

_results = scan_bind_ports(cfg.get("server_host", "127.0.0.1"), _port_policy, config=cfg)
_unresolved = [r for r in _results if r.in_use and not _port_policy.auto_resolve]
if _unresolved:
    for r in _unresolved:
        log.error("Port %d (%s) is already in use.", r.port, r.description)
    log.error("Set port_policy.auto_resolve = true to automatically find a free port.")
    _input_confirm_exit("Press Enter to exit...")

_resolved = build_resolved_map(_results)
if any(r.in_use for r in _results):
    for r in _results:
        if r.in_use:
            log.info("Port %d (%s) in use -> resolved to %d", r.port, r.description, r.resolved_port)

write_runtime_file(_resolved, _PORT_RUNTIME_DIR)
os.environ.update(ports_to_env(_resolved))

if not _port_policy.session_only:
    persist_to_config(_resolved, CONFIG_FILE)

_API_PORT = _resolved.get("api_port", DEFAULT_PORT)
_API_BASE_URL = f"http://127.0.0.1:{_API_PORT}/api/v1"
_SERVER_HOST = cfg.get("server_host", "127.0.0.1")

# -----------------------------
# Updater
# -----------------------------
def replace_updater_if_exists() -> None:
    if update_new.exists():
        log.info("[..] New updater found. Installing...")
        try:
            update_new.replace(UPDATE_EXE_PATH)
            log.info("Updater successfully updated.")
            time.sleep(0.5)
        except PermissionError:
            log.info("[FAIL] Error: %s is still locked.", UPDATE_EXE_PATH.name)


def start_UPDATE_EXE_PATH():
    """Run updater synchronously — must wait for exit code."""
    cmd = [str(UPDATE_EXE_PATH), "--auto"]
    log_dir = ROOT_DIR / "logs" / "update_logs"
    if IS_WINDOWS:
        update_hidden = not CONSOLE_VISIBLE or not ALLOW_CLOSE or LOG_LEVEL < 2
        flags = subprocess.CREATE_NO_WINDOW if update_hidden else subprocess.CREATE_NEW_CONSOLE
        proc = subprocess.Popen(cmd, creationflags=flags)
    else:
        log.info("Starting updater. This may take a few minutes. Please do not close or interrupt the program...")
        log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
        log_file = log_dir / f"updater_{timestamp}.log"
        with open(log_file, "a", encoding="utf-8") as lf:
            proc = subprocess.Popen(cmd, stdout=lf, stderr=lf, preexec_fn=os.setsid)

    max_logs = cfg.get("update", {}).get("max_update_logs", 20)
    try:
        max_logs = int(max_logs)
    except Exception:
        max_logs = 20
    if max_logs >= 0:
        logs = sorted(log_dir.glob("updater_*.log"), key=lambda f: f.stat().st_mtime, reverse=True)
        for old_log in logs[max_logs:]:
            try:
                old_log.unlink()
            except Exception as e:
                log.warning("Failed to delete old log %s: %s", old_log, e)

    while proc.poll() is None:
        update_signal = ROOT_DIR / "update_signal.tmp"
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

        try:
            with urllib.request.urlopen(f"{_API_BASE_URL}/updater/signal", timeout=2) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    if data.get("signal") == "kill":
                        req = urllib.request.Request(f"{_API_BASE_URL}/updater/signal", method="DELETE")
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

        elif result == 0:
            log.info("\nUpdate has been installed. Restarting automatically...")
            _executable = sys.executable
            _args = [_executable] + sys.argv[1:]
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            # PyInstaller 6.9+ requires reset env for processes that outlive us.
            env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
            if IS_WINDOWS:
                restart_hidden = not CONSOLE_VISIBLE or not ALLOW_CLOSE or LOG_LEVEL < 2
                flags = subprocess.CREATE_NO_WINDOW if restart_hidden else subprocess.CREATE_NEW_CONSOLE
                subprocess.Popen(_args, creationflags=flags, close_fds=True, env=env)
            else:
                subprocess.Popen(_args, env=env, start_new_session=True, close_fds=True)
            sys.exit(0)

        else:
            log.error("Updater failed with exit code %s. Aborting update.", result)
            break
else:
    log.info("Automatic updates are disabled.")


# -----------------------------
# Supervisor setup
# -----------------------------
supervisor = get_supervisor()
supervisor.configure(session_tool=SESSION_TOOL, api_base_url=_API_BASE_URL)


def _stop_all_atexit():
    """Best-effort cleanup if the interpreter exits normally."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            return
        loop.run_until_complete(supervisor.stop_all())
    except Exception as exc:
        log.debug("atexit cleanup skipped: %s", exc)


atexit.register(_stop_all_atexit)


def _gui_already_running() -> bool:
    """Return True if another GUI instance is already running."""
    lockfile = (ROOT_DIR / "tmp" / "gui.lock").resolve()
    if not lockfile.exists():
        return False
    try:
        pid = int(lockfile.read_text().strip())
        if pid == os.getpid():
            return False
        if IS_WINDOWS:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(0x0400, False, pid)
            if handle:
                kernel32.CloseHandle(handle)
                return True
            return False
        else:
            try:
                os.kill(pid, 0)
            except OSError:
                return False
            else:
                return True
    except Exception:
        return False


# -----------------------------
# Visibility helpers
# -----------------------------
def get_visibility(required_level: int) -> bool:
    """Return True if the window should be hidden."""
    if not CONSOLE_VISIBLE or not ALLOW_CLOSE:
        return True
    return LOG_LEVEL < required_level


def _get_popen_kwargs(hidden: bool) -> dict[str, Any]:
    """Build subprocess kwargs for a child executable."""
    kwargs: dict[str, Any] = {}
    if IS_WINDOWS:
        flags = subprocess.CREATE_NO_WINDOW if hidden else subprocess.CREATE_NEW_CONSOLE
        if _plugin_sandbox:
            sandbox_kwargs = _plugin_sandbox.get_popen_kwargs()
            kwargs["creationflags"] = flags | sandbox_kwargs.get("creationflags", 0)
        else:
            kwargs["creationflags"] = flags
    elif _plugin_sandbox:
        kwargs.update(_plugin_sandbox.get_popen_kwargs())
    return kwargs


# -----------------------------
# Process registration
# -----------------------------
def _register_builtin_processes() -> None:
    """Register the built-in application processes with the supervisor."""
    if APP_EXE_PATH.exists():
        supervisor.register(
            "App",
            [str(APP_EXE_PATH)],
            hidden=get_visibility(2),
        )

    if SERVER_EXE_PATH.exists():
        server_default_dir = (ROOT_DIR / "server" / "default").resolve()
        server_default_dir.mkdir(parents=True, exist_ok=True)
        default_port = cfg.get("java", {}).get("port", 25565)
        from core.minecraft_readiness import make_minecraft_readiness_check
        supervisor.register(
            "Minecraft Server",
            [str(SERVER_EXE_PATH), "--instance-dir", str(server_default_dir), "--port", str(default_port)],
            cwd=server_default_dir,
            hidden=get_visibility(2),
            readiness_check=make_minecraft_readiness_check(server_default_dir),
            readiness_timeout=120.0,
        )

    if GUI_EXE_PATH.exists() and GUI_ENABLED and not _gui_already_running():
        supervisor.register(
            "GUI",
            [str(GUI_EXE_PATH)],
            shell=True,
            hidden=get_visibility(2),
        )

    if OVERLAY_EXE_PATH.exists() and OVERLAY_ENABLED:
        gui_hidden = True if CONTROL_METHOD == "DCS" else None
        supervisor.register(
            "Overlay",
            [str(OVERLAY_EXE_PATH)] + (["--gui-hidden"] if gui_hidden else []),
            hidden=get_visibility(2),
        )


def _register_plugins(plugins: list[AppConfig]) -> None:
    """Register discovered plugins with the supervisor."""
    for app in plugins:
        path = Path(app.path)
        if not path.exists():
            log.warning("Plugin executable not found: %s", path)
            continue

        hidden = get_visibility(app.level)
        cmd = [str(path)]
        if app.ics and CONTROL_METHOD == "DCS":
            cmd.append("--gui-hidden")

        post_spawn = None
        if _plugin_sandbox and IS_WINDOWS:
            def make_post_spawn(sb):
                def _post_spawn(proc):
                    sb.apply_post_spawn(proc)
                return _post_spawn
            post_spawn = make_post_spawn(_plugin_sandbox)

        supervisor.register(
            app.name,
            cmd,
            hidden=hidden,
            post_spawn=post_spawn,
            enabled=app.enable,
        )
        if app.enable:
            log.info("Registered plugin: %s", app.name)
        else:
            log.info("Plugin %s is disabled — skipping process registration", app.name)


_register_builtin_processes()

_launcher = PluginLauncher()


# -----------------------------
# API server lifecycle
# -----------------------------
async def start_api_server() -> None:
    """Start the FastAPI/uvicorn server as an asyncio task."""
    import uvicorn
    from core.api import create_app

    api_key = cfg.get("api_key", "")
    app = create_app(api_key=api_key)
    config = uvicorn.Config(
        app,
        host=_SERVER_HOST,
        port=_API_PORT,
        log_level="warning",
    )
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve(), name="api-server")
    supervisor.set_api_server_task(task, server, _API_BASE_URL)
    log.info("API server starting on %s:%d ...", _SERVER_HOST, _API_PORT)

    # Wait for API to become reachable.
    from core.lifecycle import _wait_for_api_ready
    ready = await _wait_for_api_ready(_API_BASE_URL, timeout=15.0)
    if ready:
        log.info("API server ready.")
        await _check_plugin_updates()
    else:
        log.warning("API server not reachable within 15 s — continuing without plugin support")


async def _check_plugin_updates() -> None:
    """Query the API for available plugin updates without blocking the loop."""
    def _fetch():
        try:
            with urllib.request.urlopen(f"{_API_BASE_URL}/plugins/updates", timeout=5) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode("utf-8"))
        except Exception:
            return None
        return None

    data = await asyncio.to_thread(_fetch)
    if data and data.get("updates_available", 0) > 0:
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


async def _fetch_plugin_path(plugin_name: str) -> str:
    """Ask the API for a plugin's executable path without blocking the loop."""
    def _fetch():
        try:
            encoded = urllib.parse.quote(plugin_name, safe="")
            with urllib.request.urlopen(f"{_API_BASE_URL}/plugins/{encoded}", timeout=3) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    return data.get("path", "")
        except Exception:
            return ""
        return ""

    return await asyncio.to_thread(_fetch)


async def _mark_plugin_dead(plugin_name: str) -> None:
    """Update the plugin registry to mark a plugin as dead/non-enabled."""
    def _put():
        try:
            encoded = urllib.parse.quote(plugin_name, safe="")
            data = json.dumps({"health_status": "dead", "enabled": False}).encode("utf-8")
            req = urllib.request.Request(
                f"{_API_BASE_URL}/plugins/{encoded}",
                data=data,
                headers={"Content-Type": "application/json"},
                method="PUT",
            )
            with urllib.request.urlopen(req, timeout=5):
                pass
        except Exception:
            raise

    await asyncio.to_thread(_put)


# -----------------------------
# File watcher
# -----------------------------
RUNTIME_DIR = (ROOT_DIR / "core" / "runtime").resolve()


async def _restart_server_process() -> None:
    """Stop and restart the Minecraft Server child process."""
    try:
        await supervisor.stop("Minecraft Server")
        await supervisor.start("Minecraft Server")
        log.info("Minecraft Server restarted")
    except Exception as exc:
        log.exception("Failed to restart Minecraft Server: %s", exc)


async def check_and_run() -> None:
    """Poll runtime signal files and dispatch commands to the supervisor."""
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    while True:
        if supervisor.state == SupervisorState.COMPLETE:
            return

        for file in list(RUNTIME_DIR.iterdir()):
            if not file.is_file():
                continue
            name = file.stem.lower()

            if name == "shutdown":
                file.unlink(missing_ok=True)
                if not AUTO_SHUTDOWN_ENABLED:
                    log.info("Shutdown signal detected, but Auto shutdown is disabled.")
                    continue
                if supervisor.state != SupervisorState.COUNTDOWN:
                    log.info("\nShutdown detected. System will shut down in %s seconds.", SHUTDOWN_DELAY_SECONDS)
                    asyncio.create_task(supervisor.shutdown_countdown(SHUTDOWN_DELAY_SECONDS))

            elif name == "shutdown_now":
                file.unlink(missing_ok=True)
                log.info("\nImmediate shutdown signal detected.")
                supervisor.clear_shutdown_status()
                shutdown_cancel_event.set()
                await supervisor.shutdown()
                return

            elif name == "restart":
                file.unlink(missing_ok=True)
                log.info("\nRestart signal detected. Requesting clean restart...")
                if supervisor.state in (SupervisorState.RUNNING, SupervisorState.IDLE):
                    asyncio.create_task(event_bus.publish("server.restarting", {"version": API_VERSION}))
                    asyncio.create_task(supervisor.restart())

            elif name == "restart_server":
                file.unlink(missing_ok=True)
                log.info("\nRestart server signal detected. Restarting Minecraft Server...")
                if supervisor.state in (SupervisorState.RUNNING, SupervisorState.IDLE, SupervisorState.STARTING):
                    asyncio.create_task(_restart_server_process())

            elif name == "shutdown_cancel":
                shutdown_cancel_event.set()
                file.unlink(missing_ok=True)
                log.info("\nShutdown cancel signal detected.")

            elif name.startswith("plugin_start_"):
                file.unlink(missing_ok=True)
                plugin_name = name[len("plugin_start_"):]
                log.info("\nPlugin start signal detected for '%s'.", plugin_name)
                proc = supervisor.get(plugin_name)
                if proc is None:
                    # New plugin discovered via API? Try to fetch details.
                    path = await _fetch_plugin_path(plugin_name)
                    if path and Path(path).exists():
                        supervisor.register(plugin_name, [path])
                        await supervisor.start(plugin_name)
                    else:
                        log.warning("Failed to start plugin '%s': could not resolve path", plugin_name)
                else:
                    await supervisor.start(plugin_name)

            elif name.startswith("plugin_stop_"):
                file.unlink(missing_ok=True)
                plugin_name = name[len("plugin_stop_"):]
                log.info("\nPlugin stop signal detected for '%s'.", plugin_name)
                await supervisor.stop(plugin_name)

            else:
                file.unlink(missing_ok=True)

        await asyncio.sleep(1)


# -----------------------------
# Console command loop
# -----------------------------
async def command_loop() -> None:
    """Read console commands and dispatch them."""
    while True:
        if supervisor.state == SupervisorState.COMPLETE:
            break
        try:
            cmd = await asyncio.to_thread(
                input,
                "\nType 'exit' to stop all programs ('help' for commands): ",
            )
        except EOFError:
            # stdin closed (e.g. started headless or without a TTY). This must
            # NOT shut down the whole application — console commands are just
            # unavailable, the API and all services keep running.
            log.info(
                "Console input unavailable (no TTY); interactive commands are disabled. "
                "The application continues to run."
            )
            return
        cmd = cmd.strip().lower()
        if cmd == "help":
            log.info("\nAvailable commands:")
            log.info("  exit  - Stop all programs and close")
            log.info("  stop  - Cancel active shutdown countdown")
        elif cmd == "exit":
            break
        elif cmd == "stop":
            shutdown_cancel_event.set()
        else:
            log.info("Unknown command: %s", cmd)

    if supervisor.state != SupervisorState.COMPLETE:
        await supervisor.shutdown()


# -----------------------------
# Plugin health checker
# -----------------------------
_PLUGIN_HEALTH_INTERVAL = 15.0
_AUTO_RESTART_PLUGINS = True
_BUILTIN_NAMES = {"App", "Minecraft Server", "GUI", "Overlay"}


async def _plugin_health_check_loop() -> None:
    """Periodically check plugin processes and update registry."""
    while True:
        await asyncio.sleep(_PLUGIN_HEALTH_INTERVAL)
        if supervisor.state != SupervisorState.RUNNING:
            continue

        for proc in supervisor.list_processes():
            if proc.shell:
                continue
            if proc.state != ProcessState.RUNNING:
                continue
            # Direct Popen children are polled; tmux/screen children are checked
            # via session liveness (proc.proc is None there).
            if await supervisor._process_is_alive(proc):
                # Process is alive — record heartbeat
                _health_mon.record_heartbeat(f"process.{proc.name}")
                continue

            if proc.name in _BUILTIN_NAMES:
                # Built-in processes are handled by dedicated workers
                continue

            exit_code = proc.proc.returncode if proc.proc is not None else "?"
            log.warning("Plugin '%s' process died (exit code %s) — updating registry", proc.name, exit_code)
            proc.state = ProcessState.FAILED
            proc.restart_count += 1
            _health_mon.set_state(f"process.{proc.name}", HealthState.FAILED)
            _health_mon.record_error(f"process.{proc.name}", f"Process died with exit code {exit_code}")

            try:
                await _mark_plugin_dead(proc.name)
                log.info("Plugin '%s' marked as dead in registry", proc.name)
            except Exception as exc:
                log.warning("Failed to update health for plugin '%s': %s", proc.name, exc)

            if _AUTO_RESTART_PLUGINS:
                log.info("Auto-restarting plugin '%s' ...", proc.name)
                signal_file = RUNTIME_DIR / f"plugin_start_{proc.name}"
                try:
                    signal_file.write_text(proc.name, encoding="utf-8")
                except Exception as exc:
                    log.warning("Failed to write restart signal for '%s': %s", proc.name, exc)


async def _runtime_validation_loop() -> None:
    """Periodic runtime validation of all registered components."""
    while True:
        await asyncio.sleep(_RUNTIME_VALIDATION_INTERVAL)
        if supervisor.state != SupervisorState.RUNNING:
            continue

        # Record heartbeats for supervisor and api_server (they can't report their own)
        _health_mon.record_heartbeat("supervisor")
        _health_mon.record_heartbeat("api_server")

        # Only monitor running processes — disabled/stopped ones don't report heartbeats
        monitored_components = [
            f"process.{p.name}" for p in supervisor.list_processes()
            if p.state == ProcessState.RUNNING
        ]
        monitored_components.extend(["supervisor", "api_server"])

        suite = validate_runtime(
            health_monitor=_health_mon,
            components=monitored_components,
            heartbeat_timeout=_RUNTIME_HEARTBEAT_TIMEOUT,
        )

        critical = suite.critical_failures()
        if critical:
            for fail in critical:
                log.warning("[RUNTIME-VALIDATION] %s", fail.format())


# -----------------------------
# Diagnostics command
# -----------------------------
def _log_diagnostics_report() -> None:
    """Generate and log a diagnostics report."""
    report = generate_diagnostics_report(crash_mgr)
    log.info("[DIAGNOSTICS] Health: %d/%d running, %d degraded, %d failed",
             report["health"]["running"], report["health"]["total_components"],
             report["health"]["degraded"], report["health"]["failed"])
    if report["health"]["failed_components"]:
        log.warning("[DIAGNOSTICS] Failed components: %s", ", ".join(report["health"]["failed_components"]))
    if report["health"]["degraded_components"]:
        log.warning("[DIAGNOSTICS] Degraded components: %s", ", ".join(report["health"]["degraded_components"]))


# -----------------------------
# Main
# -----------------------------
async def main() -> None:
    """Run the supervisor event loop."""
    supervisor._loop = asyncio.get_running_loop()

    # Install asyncio exception handler via crash manager
    crash_mgr.install_asyncio(supervisor._loop)

    # Register core components with health monitor
    _health_mon.register("startup", HealthState.STARTING)

    supervisor.state = SupervisorState.STARTING
    supervisor.shutdown_delay = float(SHUTDOWN_DELAY_SECONDS)

    # Run startup validation
    startup_suite = run_startup_validation(
        config_path=CONFIG_FILE,
        required_dirs=[
            (ROOT_DIR / "config", "config", False),
            (ROOT_DIR / "logs", "logs", True),
            (ROOT_DIR / "data", "data", True),
            (ROOT_DIR / "core" / "runtime", "runtime", True),
        ],
    )
    critical_failures = startup_suite.critical_failures()
    if critical_failures:
        for fail in critical_failures:
            log.error("[STARTUP-VALIDATION] %s", fail.format())
        log.error("[STARTUP-VALIDATION] %d critical failure(s) — aborting", len(critical_failures))
        _health_mon.set_state("startup", HealthState.FAILED)
        _input_confirm_exit("Press Enter to exit...")
    _health_mon.set_state("startup", HealthState.RUNNING)

    await start_api_server()
    _health_mon.set_state("api_server", HealthState.RUNNING)

    # Discover plugins now that the API is available.
    try:
        plugin_registry: list[AppConfig] = await asyncio.to_thread(_launcher.get_plugins)
        _register_plugins(plugin_registry)
    except Exception as exc:
        crash_mgr.report_error(
            LIFECYCLE_0001,
            detail=f"Plugin discovery failed: {exc}",
            context_info={"phase": "startup"},
        )

    if ALLOW_CLOSE:
        log.info("\nStarting programs... (start script visible)")

    # Start backend services.
    await supervisor.start_all()
    # Start GUI shell (if registered).
    await supervisor.start_shell()

    if ALLOW_CLOSE and not IS_WINDOWS and SESSION_TOOL and supervisor._linux_sessions:
        log.info("\n--- Active %s sessions ---", SESSION_TOOL)
        for s in supervisor._linux_sessions:
            if SESSION_TOOL == "tmux":
                log.info("  tmux attach -t %s", s)
            elif SESSION_TOOL == "screen":
                log.info("  screen -r %s", s)
        log.info("-----------------------------------")

    supervisor.state = SupervisorState.RUNNING
    log.info("\nAll programs have been started.")

    # Log initial diagnostics
    _log_diagnostics_report()

    # Background tasks.
    watcher = asyncio.create_task(check_and_run(), name="signal-watcher")
    health = asyncio.create_task(_plugin_health_check_loop(), name="plugin-health")
    runtime_val = asyncio.create_task(_runtime_validation_loop(), name="runtime-validation")
    cmd_task = asyncio.create_task(command_loop(), name="command-loop")

    # Wait for shutdown to complete.
    supervisor._shutdown_complete_event = asyncio.Event()
    await supervisor._shutdown_complete_event.wait()

    # Cancel background tasks.
    for task in (watcher, health, runtime_val, cmd_task):
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    # Run shutdown validation
    shutdown_suite = validate_shutdown(timeout=5.0)
    if not shutdown_suite.all_passed():
        for fail in shutdown_suite.failures():
            log.warning("[SHUTDOWN-VALIDATION] %s", fail.format())

    # Stop the API server if still running.
    await supervisor.stop_api_server(timeout=5.0)

    # Log final diagnostics
    _log_diagnostics_report()

    log.info("Shutdown complete.")


if __name__ == "__main__":
    crash_mgr.install()
    install_global_exception_hook("start")
    heartbeat = start_heartbeat(log, interval=60.0)

    # Register the start process itself
    _health_mon.register("start_process", HealthState.STARTING)

    # Windows: use the selector event loop. The default ProactorEventLoop can
    # raise ConnectionResetError from its internal _call_connection_lost when a
    # remote host closes a connection abruptly (CPython gh-79813), which escaped
    # asyncio.run() and terminated the whole supervisor as a fatal CORE-0001 crash.
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    try:
        asyncio.run(main())
        _health_mon.set_state("start_process", HealthState.STOPPED)
    except KeyboardInterrupt:
        log.info("\nInterrupted by user.")
        _health_mon.set_state("start_process", HealthState.STOPPED)
    except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError) as exc:
        # A client (overlay, GUI, browser) abruptly closed its connection.
        # This is normal network behavior and must not crash the supervisor.
        log.warning("[NET] Connection reset by remote host: %s", exc)
        _health_mon.set_state("start_process", HealthState.STOPPED)
    except Exception:
        crash_mgr.report_exception(
            CORE_0001,
            exc=sys.exc_info()[1],
            exc_type=sys.exc_info()[0],
            exc_tb=sys.exc_info()[2],
            context_info={"source": "start.main"},
        )
        _health_mon.set_state("start_process", HealthState.FAILED)
        sys.exit(1)
    finally:
        heartbeat.stop()
        # Final cleanup if asyncio.run() exited without setting COMPLETE.
        if supervisor.state != SupervisorState.COMPLETE:
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(supervisor.stop_all())
                loop.close()
            except Exception:
                pass
