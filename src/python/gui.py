#!/usr/bin/env python3
"""TikTok2Mc — Central GUI (pywebview shell).

Opens the dashboard served by the central API server at /gui.
Supports --gui-hidden for headless / DCS mode.
"""

import sys
import os
import argparse
import logging
import time
import urllib.request
import urllib.error

# Ensure src/ is on the path for development runs.
_src = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _src not in sys.path:
    sys.path.insert(0, _src)

from core.paths import get_base_dir
from core.api.server import DEFAULT_PORT

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger(__name__)

BASE_DIR = get_base_dir()
API_URL = f"http://127.0.0.1:{DEFAULT_PORT}"
GUI_URL = f"{API_URL}/gui/index.html"


def _api_ready(timeout: float = 20.0) -> bool:
    """Poll the API health endpoint until it responds or timeout expires."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{API_URL}/api/v1/health", timeout=1) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="TikTok2Mc GUI")
    parser.add_argument("--gui-hidden", action="store_true", help="Run without window")
    args = parser.parse_args()

    if args.gui_hidden:
        log.info("GUI hidden mode — exiting.")
        sys.exit(0)

    log.info("Waiting for API server (%s) ...", API_URL)
    if not _api_ready():
        log.error("API server not reachable within timeout. GUI cannot start.")
        input("Press Enter to exit...")
        sys.exit(1)

    log.info("Starting GUI at %s", GUI_URL)
    try:
        import webview
    except ImportError as exc:
        log.error("pywebview is required for the GUI: %s", exc)
        input("Press Enter to exit...")
        sys.exit(1)

    class _CloseApi:
        """JS-accessible API for the unsaved-changes close flow.

        Methods are callable from JavaScript via pywebview.api.*().
        All methods must be synchronous (no I/O, no evaluate_js).
        """

        def __init__(self):
            self._approved = False
            self._close_requested = False

        def approve_close(self):
            self._approved = True

        def close_requested(self) -> bool:
            return self._close_requested

        def reset_close_request(self):
            self._close_requested = False

    close_api = _CloseApi()

    window = webview.create_window(
        "TikTok2Mc",
        GUI_URL,
        width=1280,
        height=800,
        min_size=(800, 600),
        js_api=close_api,
    )

    def _on_closing():
        if close_api._approved:
            return True
        close_api._close_requested = True
        return False

    window.events.closing += _on_closing
    webview.start(debug=False)


if __name__ == "__main__":
    main()
