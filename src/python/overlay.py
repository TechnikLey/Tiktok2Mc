#!/usr/bin/env python3
"""TikTok2Mc — Overlay Window Process (core subsystem).

Opens one or more pywebview windows for the built-in overlay subsystem.
Each window loads its rendered HTML from the central API server.

This replaces the former ``plugins/overlaytxt/main.py`` plugin process.
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
from core.yaml_utils import load_yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger(__name__)

BASE_DIR = get_base_dir()
API_URL = f"http://127.0.0.1:{DEFAULT_PORT}"


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


def _load_overlay_names() -> list[str]:
    """Read overlay names from the global config file."""
    config_path = (BASE_DIR.parent / "config" / "config.yaml").resolve()
    try:
        cfg = load_yaml(config_path)
    except Exception as exc:
        log.warning("Failed to load global config: %s", exc)
        return ["default"]

    overlay_cfg = cfg.get("overlay", {})
    overlays = overlay_cfg.get("overlays", [{"name": "default"}])
    names = [o.get("name") for o in overlays if o.get("name")]
    if not names:
        names = ["default"]
    return names


def main() -> None:
    parser = argparse.ArgumentParser(description="TikTok2Mc Overlay Process")
    parser.add_argument("--gui-hidden", action="store_true", help="Hide GUI windows (headless mode)")
    args = parser.parse_args()

    log.info("Overlay process starting...")

    if not _api_ready():
        log.error("API server not reachable — exiting.")
        sys.exit(1)

    overlay_names = _load_overlay_names()
    log.info("Overlay windows configured: %s", overlay_names)

    if args.gui_hidden:
        log.info("GUI hidden mode — overlay HTML served by API only.")
        # Keep the process alive so the API knows overlay is managed.
        # Check for a shutdown signal so we don't have to be killed.
        shutdown_signal = BASE_DIR / "core" / "runtime" / "shutdown"
        shutdown_now_signal = BASE_DIR / "core" / "runtime" / "shutdown_now"
        while True:
            if shutdown_signal.exists() or shutdown_now_signal.exists():
                log.info("Shutdown signal detected — overlay process exiting.")
                try:
                    shutdown_signal.unlink(missing_ok=True)
                    shutdown_now_signal.unlink(missing_ok=True)
                except Exception:
                    pass
                sys.exit(0)
            time.sleep(1)
        return

    try:
        import webview
    except ImportError as exc:
        log.error("pywebview not installed: %s", exc)
        sys.exit(1)

    for idx, name in enumerate(overlay_names):
        url = f"{API_URL}/api/v1/overlay?overlay={name}&chroma=1"
        webview.create_window(
            f"Overlay: {name.upper()}",
            url,
            transparent=False,
            frameless=False,
            on_top=True,
            width=800,
            height=300,
            x=100 + (idx * 50),
            y=100 + (idx * 50),
        )

    log.info("Starting webview event loop for %d overlay window(s)...", len(overlay_names))
    webview.start()
    log.info("Overlay process exited.")


if __name__ == "__main__":
    main()
