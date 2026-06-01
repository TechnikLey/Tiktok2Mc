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
                    creationflags=subprocess.CREATE_NEW_CONSOLE,
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
        """Stop the system process."""
        global _full_system_proc
        if _full_system_proc is not None and _full_system_proc.poll() is None:
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
        return "not_running"

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
    if _full_system_proc is not None and _full_system_proc.poll() is None:
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


def main() -> None:
    parser = argparse.ArgumentParser(description="TikTok2Mc GUI")
    parser.add_argument("--gui-hidden", action="store_true", help="Run without window")
    args = parser.parse_args()

    if args.gui_hidden:
        log.info("GUI hidden mode — exiting.")
        sys.exit(0)

    log.info("Starting GUI launcher...")

    # If API is already running, go straight to the full dashboard
    if _api_ready(timeout=2.0):
        log.info("API server already running — opening dashboard at %s", GUI_URL)
        _open_window(GUI_URL)
        return

    # Otherwise show the launcher page
    if not LAUNCHER_HTML.exists():
        log.error("Launcher HTML not found at %s", LAUNCHER_HTML)
        # Fallback: try to open API URL anyway
        _open_window(GUI_URL)
        return

    log.info("API offline — showing launcher at %s", LAUNCHER_HTML)
    _open_window(str(LAUNCHER_HTML))


def _open_window(url: str) -> None:
    """Open pywebview window with the given URL."""
    try:
        import webview
    except ImportError as exc:
        log.error("pywebview is required for the GUI: %s", exc)
        input("Press Enter to exit...")
        sys.exit(1)

    launcher_api = LauncherAPI()

    window = webview.create_window(
        "TikTok2Mc",
        url,
        width=1280,
        height=800,
        min_size=(800, 600),
        js_api=launcher_api,
    )

    def _on_closing():
        # Allow window to close normally; process cleanup is handled by atexit
        return True

    window.events.closing += _on_closing
    webview.start(debug=False)


if __name__ == "__main__":
    main()
