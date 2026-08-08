#!/usr/bin/env python3
"""TikTok2Mc — Central GUI (pywebview shell).

Opens a local launcher dashboard that works without the API server.
Users can start the API server on-demand from within the GUI.
Supports --gui-hidden for headless mode.
"""

import argparse
import atexit
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# Ensure src/ is on the path for development runs.
_src = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _src not in sys.path:
    sys.path.insert(0, _src)

from core.api.server import DEFAULT_PORT
from core.crash_manager import get_crash_manager
from core.health_monitor import HealthState, get_health_monitor
from core.logger import (
    handle_unhandled_exception,
    initialize_logging,
    install_global_exception_hook,
    start_heartbeat,
)
from core.paths import get_base_dir, get_root_dir

log = initialize_logging(__name__)

BASE_DIR = get_base_dir()
ROOT_DIR = get_root_dir()
API_URL = f"http://127.0.0.1:{DEFAULT_PORT}"
GUI_URL = f"{API_URL}/gui/index.html"
# Release layout: core/templates/gui/  |  Dev layout: templates/gui/
LAUNCHER_HTML = ROOT_DIR / "core" / "templates" / "gui" / "launcher.html"
if not LAUNCHER_HTML.exists():
    LAUNCHER_HTML = ROOT_DIR / "templates" / "gui" / "launcher.html"

IS_WINDOWS = sys.platform == "win32"
SUFFIX = ".exe" if IS_WINDOWS else ".bin"
# gui.exe lives in build/release/core/ (release) or src/python/ (dev)
# start.exe lives one directory above gui.exe (build/release/)
START_EXE = (BASE_DIR.parent / f"start{SUFFIX}").resolve()

_full_system_proc = None
_window = None

GUI_LOCKFILE = (ROOT_DIR / "tmp" / "gui.lock").resolve()


def _linux_install_hint() -> str:
    """Return platform-appropriate Qt6 install instructions for Linux."""
    if sys.platform != "linux":
        return ""
    try:
        with open("/etc/os-release") as f:
            os_release = f.read()
    except FileNotFoundError:
        return "Install Qt6 system libraries for your distribution."
    if "Debian" in os_release or "Ubuntu" in os_release:
        return "sudo apt install libqt6webenginecore6 qt6-wayland"
    elif "Fedora" in os_release:
        return "sudo dnf install qt6-qtwebengine qt6-qtwayland"
    elif "Arch" in os_release or "Manjaro" in os_release:
        return "sudo pacman -S qt6-webengine qt6-wayland"
    return "Install Qt6 system libraries for your distribution."


def _api_ready(timeout: float = 1.0) -> bool:
    """Quick check if the API health endpoint responds."""
    try:
        with urllib.request.urlopen(f"{API_URL}/api/v1/health", timeout=timeout) as resp:
            return resp.status == 200
    except OSError:
        return False


class LauncherAPI:
    """JS-accessible API for the launcher page.

    Methods are callable from JavaScript via pywebview.api.*().
    All methods must be synchronous (no I/O, no evaluate_js).
    """

    def __init__(self):
        self._approved = False
        self._close_requested = False

    # ---- Close flow ----
    def approve_close(self):
        self._approved = True

    def close_requested(self) -> bool:
        return self._close_requested

    def reset_close_request(self):
        self._close_requested = False

    def close_app(self) -> str:
        """Destroy the GUI window immediately so the process exits."""
        global _window
        if _window is not None:
            try:
                _window.destroy()
            except Exception as e:  # webview teardown errors are best-effort
                log.warning("Failed to destroy window: %s", e)
        return "closing"

    def download_file(self, content: str, filename: str) -> str:
        """Save content to the user's Downloads folder and return the path."""
        downloads = Path.home() / "Downloads"
        try:
            downloads.mkdir(parents=True, exist_ok=True)
        except OSError:
            downloads = Path.home()
        path = downloads / filename
        try:
            path.write_text(content, encoding="utf-8")
            return str(path)
        except OSError as e:
            log.warning("Failed to save file: %s", e)
            return f"error:{e}"

    # ---- Server control ----
    def start_system(self) -> str:
        """Start the full system (start.exe)."""
        global _full_system_proc, _api_proc
        if _full_system_proc is not None:
            return "already_running"

        if not START_EXE.exists():
            return f"missing:{START_EXE}"

        try:
            if IS_WINDOWS:
                _full_system_proc = subprocess.Popen(
                    [str(START_EXE)],
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            else:
                log_file = BASE_DIR / "logs" / "full_system.log"
                log_file.parent.mkdir(parents=True, exist_ok=True)
                with open(log_file, "w", encoding="utf-8") as lf:
                    _full_system_proc = subprocess.Popen([str(START_EXE)], stdout=lf, stderr=lf, stdin=subprocess.DEVNULL)
            log.info("Full system process started (PID %s)", _full_system_proc.pid if _full_system_proc else "?")
            return "started"
        except OSError as e:
            log.error("Failed to start full system: %s", e)
            return f"error:{e}"

    def stop_system(self) -> str:
        """Stop the system process gracefully via API, then force-kill if needed."""
        global _full_system_proc
        if _full_system_proc is None or _full_system_proc.poll() is not None:
            return "not_running"

        # Prefer graceful shutdown through the API.
        try:
            req = urllib.request.Request(
                f"{API_URL}/api/v1/shutdown/now",
                method="POST",
                headers={"Content-Type": "application/json"},
                data=b"{}",
            )
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                if resp.status == 200:
                    # Give the supervisor a few seconds to shut down cleanly.
                    for _ in range(40):
                        if _full_system_proc.poll() is not None:
                            _full_system_proc = None
                            return "stopped"
                        time.sleep(0.25)
        except OSError:
            pass

        # Force kill if still running.
        try:
            if IS_WINDOWS:
                subprocess.run(
                    ["taskkill", "/F", "/PID", str(_full_system_proc.pid), "/T"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
            else:
                _full_system_proc.terminate()
            _full_system_proc = None
            return "stopped"
        except OSError as e:
            log.warning("Failed to terminate system process: %s", e)
            return "error"

    def get_api_status(self) -> str:
        """Return current API server status."""
        if _api_ready(timeout=1.0):
            return "running"
        if _full_system_proc is not None and _full_system_proc.poll() is None:
            return "starting"
        return "offline"


def _cleanup_processes():
    """Terminate any spawned processes on GUI exit."""
    global _full_system_proc
    if _full_system_proc is None or _full_system_proc.poll() is not None:
        log.debug("Cleanup: no managed process to stop, skipping.")
        return

    log.info("Cleanup: managed process (PID %s) still running, attempting graceful shutdown.", _full_system_proc.pid)

    # Only send shutdown request if the API is actually reachable.
    # If the API is already down, skip the request and force-kill directly.
    api_was_running = _api_ready(timeout=1.0)
    if api_was_running:
        try:
            req = urllib.request.Request(
                f"{API_URL}/api/v1/shutdown/now",
                method="POST",
                headers={"Content-Type": "application/json"},
                data=b"{}",
            )
            urllib.request.urlopen(req, timeout=3.0)
            log.info("Cleanup: shutdown request sent, waiting for process to exit.")
            for _ in range(20):
                if _full_system_proc.poll() is not None:
                    log.info("Cleanup: process exited cleanly.")
                    return
                time.sleep(0.25)
            log.warning("Cleanup: process did not exit within 5s after API shutdown request.")
        except OSError as exc:
            log.warning("Cleanup: API shutdown request failed: %s", exc)
    else:
        log.info("Cleanup: API not reachable, skipping shutdown request.")

    # Force kill if still running.
    try:
        if IS_WINDOWS:
            subprocess.run(
                ["taskkill", "/F", "/PID", str(_full_system_proc.pid), "/T"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        else:
            _full_system_proc.terminate()
        log.info("Cleanup: process force-killed.")
    except OSError as exc:
        log.warning("Cleanup: force-kill failed: %s", exc)


atexit.register(_cleanup_processes)


def _acquire_lock() -> None:
    """Write a lockfile so start.py can detect a running GUI."""
    try:
        GUI_LOCKFILE.parent.mkdir(parents=True, exist_ok=True)
        GUI_LOCKFILE.write_text(str(os.getpid()))
        atexit.register(_release_lock)
    except (OSError, TypeError) as exc:
        log.warning("Could not acquire GUI lockfile: %s", exc)


def _release_lock() -> None:
    try:
        if GUI_LOCKFILE.exists():
            pid = int(GUI_LOCKFILE.read_text().strip())
            if pid == os.getpid():
                GUI_LOCKFILE.unlink()
    except (OSError, ValueError):
        pass


def _gui_already_running() -> bool:
    """Return True if another GUI instance is already running."""
    if not GUI_LOCKFILE.exists():
        return False
    try:
        pid = int(GUI_LOCKFILE.read_text().strip())
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
    except Exception:  # lock check is best-effort; false is safe
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="TikTok2Mc GUI")
    parser.add_argument("--gui-hidden", action="store_true", help="Run without window")
    args = parser.parse_args()

    if args.gui_hidden:
        log.info("GUI hidden mode — exiting.")
        sys.exit(0)

    if _gui_already_running():
        log.info("Another GUI instance is already running — exiting.")
        sys.exit(0)

    _acquire_lock()

    log.info("Starting GUI launcher...")

    # If API is already running, go straight to the full dashboard
    if _api_ready(timeout=2.0):
        log.info("API server already running — opening dashboard at %s", GUI_URL)
        _open_window(GUI_URL, is_launcher=False)
        return

    # Otherwise show the launcher page
    if not LAUNCHER_HTML.exists():
        log.error("Launcher HTML not found at %s", LAUNCHER_HTML)
        # Fallback: try to open API URL anyway
        _open_window(GUI_URL, is_launcher=False)
        return

    log.info("API offline — showing launcher at %s", LAUNCHER_HTML)
    _open_window(str(LAUNCHER_HTML), is_launcher=True)


def _open_window(url: str, is_launcher: bool = False) -> None:
    """Open pywebview window with the given URL."""
    global _window
    try:
        import webview
    except ImportError as exc:
        log.error("pywebview is required for the GUI: %s", exc)
        try:
            input("Press Enter to exit...")
        except EOFError:
            pass
        sys.exit(1)
    except Exception as exc:  # process exits with hints on any GUI backend failure
        hint = _linux_install_hint()
        log.error("GUI backend failed to load: %s", exc)
        if hint:
            log.error("Install Qt6: %s", hint)
        try:
            input("Press Enter to exit...")
        except EOFError:
            pass
        sys.exit(1)

    launcher_api = LauncherAPI()

    _window = webview.create_window(
        "TikTok2Mc",
        url,
        width=1280,
        height=800,
        min_size=(800, 600),
        js_api=launcher_api,
        text_select=True,
    )

    if is_launcher:
        import threading as _threading
        _nav_lock = _threading.Lock()

        def _poll_api():
            while True:
                time.sleep(2.0)
                try:
                    if _api_ready(timeout=1.0):
                        with _nav_lock:
                            if _window is not None and hasattr(_window, "load_url"):
                                # Short extra wait so JS-based navigation in the launcher can
                                # fire first if it also detected the API.
                                time.sleep(0.5)
                                if _window is not None and hasattr(_window, "load_url"):
                                    try:
                                        _window.load_url(GUI_URL)
                                        log.info("API came online — switched to dashboard.")
                                    except Exception as nav_err:  # best-effort navigation
                                        log.warning("Navigation to dashboard failed: %s", nav_err)
                        break
                except Exception as exc:  # poll loop must never die
                    log.debug("Poll error: %s", exc)
        t = get_crash_manager().supervised_thread(target=_poll_api, name="gui-api-poll", daemon=True)
        t.start()

    def _on_closing():
        # Allow window to close normally; process cleanup is handled by atexit
        return True

    _window.events.closing += _on_closing
    try:
        if sys.platform == "linux":
            webview.start(gui='qt', debug=False)
        else:
            webview.start(debug=False)
    except Exception as exc:  # process exits with hints on any GUI backend error
        hint = _linux_install_hint()
        log.error("GUI backend error: %s", exc)
        if hint:
            log.error("Install Qt6: %s", hint)
        sys.exit(1)


if __name__ == "__main__":
    install_global_exception_hook("gui")
    heartbeat = start_heartbeat(log, interval=60.0)
    health = get_health_monitor()
    health.register("gui", HealthState.STARTING)
    try:
        health.set_state("gui", HealthState.RUNNING)
        main()
    except KeyboardInterrupt:
        log.info("GUI interrupted by user.")
        health.set_state("gui", HealthState.STOPPED)
    except Exception:  # top-level boundary: report and exit non-zero
        handle_unhandled_exception("gui")
        health.set_state("gui", HealthState.FAILED)
        sys.exit(1)
    finally:
        if health.get_state("gui") == HealthState.RUNNING:
            health.set_state("gui", HealthState.STOPPING)
        health.set_state("gui", HealthState.STOPPED)
        heartbeat.stop()
