#!/usr/bin/env python3
"""TikTok2Mc — Central GUI (pywebview shell).

Opens a local launcher dashboard that works without the API server.
Users can start the API server on-demand from within the GUI.
Supports --gui-hidden for headless mode.
"""

import sys
import os
import argparse
import logging
import time
import urllib.request
import urllib.error
import subprocess
import threading
import atexit
from pathlib import Path

# Ensure src/ is on the path for development runs.
_src = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _src not in sys.path:
    sys.path.insert(0, _src)

from core.paths import get_base_dir, get_root_dir
from core.api.server import DEFAULT_PORT

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger(__name__)

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


def _api_ready(timeout: float = 1.0) -> bool:
    """Quick check if the API health endpoint responds."""
    try:
        with urllib.request.urlopen(f"{API_URL}/api/v1/health", timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
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
                    _full_system_proc = subprocess.Popen([str(START_EXE)], stdout=lf, stderr=lf)
            log.info("Full system process started (PID %s)", _full_system_proc.pid if _full_system_proc else "?")
            return "started"
        except Exception as e:
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
        except Exception:
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
        except Exception as e:
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
        return

    # Try graceful shutdown first.
    try:
        req = urllib.request.Request(
            f"{API_URL}/api/v1/shutdown/now",
            method="POST",
            headers={"Content-Type": "application/json"},
            data=b"{}",
        )
        urllib.request.urlopen(req, timeout=3.0)
        for _ in range(20):
            if _full_system_proc.poll() is not None:
                return
            time.sleep(0.25)
    except Exception:
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
    except Exception:
        pass


atexit.register(_cleanup_processes)


def _acquire_lock() -> None:
    """Write a lockfile so start.py can detect a running GUI."""
    try:
        GUI_LOCKFILE.parent.mkdir(parents=True, exist_ok=True)
        GUI_LOCKFILE.write_text(str(os.getpid()))
        atexit.register(_release_lock)
    except Exception as exc:
        log.warning("Could not acquire GUI lockfile: %s", exc)


def _release_lock() -> None:
    try:
        if GUI_LOCKFILE.exists():
            pid = int(GUI_LOCKFILE.read_text().strip())
            if pid == os.getpid():
                GUI_LOCKFILE.unlink()
    except Exception:
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
    except Exception:
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
        input("Press Enter to exit...")
        sys.exit(1)

    launcher_api = LauncherAPI()

    _window = webview.create_window(
        "TikTok2Mc",
        url,
        width=1280,
        height=800,
        min_size=(800, 600),
        js_api=launcher_api,
    )

    if is_launcher:
        def _poll_api():
            while True:
                time.sleep(2.0)
                try:
                    if _api_ready(timeout=1.0):
                        if _window is not None and hasattr(_window, "load_url"):
                            _window.load_url(GUI_URL)
                            log.info("API came online — switched to dashboard.")
                        break
                except Exception as exc:
                    log.debug("Poll error: %s", exc)
        t = threading.Thread(target=_poll_api, daemon=True)
        t.start()

    def _on_closing():
        # Allow window to close normally; process cleanup is handled by atexit
        return True

    _window.events.closing += _on_closing
    webview.start(debug=False)


if __name__ == "__main__":
    main()
