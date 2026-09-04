#!/usr/bin/env python3
"""TikTok2Mc — Overlay Window Process (core subsystem).

Opens one or more pywebview windows for the built-in overlay subsystem.
Each window loads its rendered HTML from the central API server.

This replaces the former ``plugins/overlaytxt/main.py`` plugin process.
"""

import argparse
import os
import sys
import time
import urllib.error
import urllib.request

# Ensure src/ is on the path for development runs.
_src = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _src not in sys.path:
    sys.path.insert(0, _src)

from ruamel.yaml.error import YAMLError  # noqa: E402

from core.api.server import DEFAULT_PORT  # noqa: E402
from core.crash_manager import get_crash_manager  # noqa: E402
from core.health_monitor import HealthState, get_health_monitor  # noqa: E402
from core.logger import (  # noqa: E402
    handle_unhandled_exception,
    initialize_logging,
    install_global_exception_hook,
    start_heartbeat,
)
from core.paths import get_base_dir, get_root_dir  # noqa: E402
from core.yaml_utils import load_yaml  # noqa: E402

log = initialize_logging(__name__)

BASE_DIR = get_base_dir()
# The supervisor exports RESOLVED_PORT_API_PORT when port_policy.auto_resolve
# relocated the API port; fall back to the default when unset (standalone runs).
API_PORT = os.environ.get("RESOLVED_PORT_API_PORT", str(DEFAULT_PORT))
API_URL = f"http://127.0.0.1:{API_PORT}"


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
        return "sudo apt install libqt6webenginecore6 qt6-wayland libxcb-cursor0"
    elif "Fedora" in os_release:
        return "sudo dnf install qt6-qtwebengine qt6-qtwayland libxcb-cursor"
    elif "Arch" in os_release or "Manjaro" in os_release:
        return "sudo pacman -S qt6-webengine qt6-wayland"
    return "Install Qt6 system libraries for your distribution."


def _api_ready(timeout: float = 20.0) -> bool:
    """Poll the API health endpoint until it responds or timeout expires."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{API_URL}/api/v1/health", timeout=1) as resp:
                if resp.status == 200:
                    return True
        except Exception:  # readiness polling must keep retrying on any error
            pass
        time.sleep(0.5)
    return False


def _load_overlay_names() -> list[str]:
    """Read overlay names from the global config file."""
    config_path = (get_root_dir() / "config" / "config.yaml").resolve()
    try:
        cfg = load_yaml(config_path)
    except (OSError, ValueError, YAMLError) as exc:
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
    parser.add_argument(
        "--gui-hidden", action="store_true", help="Hide GUI windows (headless mode)"
    )
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
        # The supervisor handles shutdown via process termination —
        # do NOT poll signal files here (that would race with check_and_run
        # in start.py and potentially consume the signal before the supervisor
        # sees it). Simply block until the process is killed by the supervisor.
        import threading

        _shutdown_event = threading.Event()

        def _on_signal(sig: int, frame: object) -> None:
            log.info("Signal %d received — overlay process exiting.", sig)
            _shutdown_event.set()

        import signal as _signal_mod

        _signal_mod.signal(_signal_mod.SIGTERM, _on_signal)
        _signal_mod.signal(_signal_mod.SIGINT, _on_signal)
        # Block until killed by supervisor or signal
        _shutdown_event.wait()
        sys.exit(0)

    try:
        import webview
    except ImportError as exc:
        log.error("pywebview not installed: %s", exc)
        sys.exit(1)
    except Exception as exc:  # process exits with hints on any GUI backend failure
        hint = _linux_install_hint()
        log.error("GUI backend failed to load: %s", exc)
        if hint:
            log.error("Install Qt6: %s", hint)
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

    log.info(
        "Starting webview event loop for %d overlay window(s)...", len(overlay_names)
    )
    try:
        if sys.platform == "linux":
            webview.start(gui="qt")
        else:
            webview.start()
    except Exception as exc:  # process exits with hints on any GUI backend error
        hint = _linux_install_hint()
        log.error("GUI backend error: %s", exc)
        if hint:
            log.error("Install Qt6: %s", hint)
        sys.exit(1)
    log.info("Overlay process exited.")


if __name__ == "__main__":
    install_global_exception_hook("overlay")
    heartbeat = start_heartbeat(log, interval=60.0)
    crash_mgr = get_crash_manager()
    health = get_health_monitor()
    health.register("overlay", HealthState.STARTING)
    try:
        health.set_state("overlay", HealthState.RUNNING)
        main()
    except KeyboardInterrupt:
        log.info("Overlay interrupted by user.")
        health.set_state("overlay", HealthState.STOPPED)
    except Exception:  # top-level boundary: report and exit non-zero
        handle_unhandled_exception("overlay")
        health.set_state("overlay", HealthState.FAILED)
        sys.exit(1)
    finally:
        health.set_state("overlay", HealthState.STOPPED)
        heartbeat.stop()
