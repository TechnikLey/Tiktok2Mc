#!/usr/bin/env python3
"""TikTok2Mc — Central GUI (pywebview shell).

Opens a local launcher dashboard that works without the API server.
Users can start the API server on-demand from within the GUI.
Supports --gui-hidden for headless mode.
"""

import argparse
import atexit
import base64
import os
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

# Ensure src/ is on the path for development runs.
_src = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _src not in sys.path:
    sys.path.insert(0, _src)

from core.api.server import DEFAULT_PORT  # noqa: E402
from core.api.shutdown_signature import make_headers  # noqa: E402
from core.crash_manager import get_crash_manager  # noqa: E402
from core.error_codes import CHATBOT_0004  # noqa: E402
from core.health_monitor import HealthState, get_health_monitor  # noqa: E402
from core.logger import (  # noqa: E402
    handle_unhandled_exception,
    initialize_logging,
    install_global_exception_hook,
    start_heartbeat,
)
from core.paths import get_base_dir, get_root_dir  # noqa: E402

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
SHUTDOWN_PENDING = (ROOT_DIR / "tmp" / "shutdown_pending").resolve()

# ── TikTok webview login (docs/CHATBOT.md §5, Variante B) ──
TIKTOK_LOGIN_URL = "https://www.tiktok.com/login"
TIKTOK_LOGIN_TIMEOUT_S = 300.0
_login_lock = threading.Lock()
_login_state: dict[str, Any] = {
    "state": "idle",  # idle | waiting | success | cancelled | timeout | error
    "masked_session_id": None,
    "error": "",
}


def _set_login_state(state: str, masked: str | None = None, error: str = "") -> None:
    with _login_lock:
        _login_state["state"] = state
        _login_state["masked_session_id"] = masked
        _login_state["error"] = error


def _tiktok_login_worker() -> None:
    """Open the TikTok login window and capture the session cookies.

    Runs on a supervised thread.  Polls ``Window.get_cookies()`` until a
    ``sessionid`` cookie appears (successful login), the user closes the
    window, or the timeout hits.  On success the credentials are stored
    encrypted via :mod:`core.chatbot_session` — the raw value never
    reaches JavaScript or the log.
    """
    try:
        import webview
    except ImportError as exc:
        _set_login_state("error", error=f"pywebview missing: {exc}")
        return

    from core.chatbot_session import (
        extract_session_cookies,
        request_bridge_reload,
        save_chatbot_session,
    )

    closed = threading.Event()

    def _on_closed() -> None:
        closed.set()

    try:
        login_window = webview.create_window(
            "TikTok Login",
            TIKTOK_LOGIN_URL,
            width=430,
            height=760,
            resizable=True,
            on_top=True,
        )
    except Exception as exc:  # backend may refuse extra windows
        log.warning("[TIKTOK-LOGIN] Could not open login window: %s", exc)
        _set_login_state("error", error=f"{type(exc).__name__}: {exc}")
        return
    if login_window is None:  # defensive: backend returned no window handle
        _set_login_state("error", error="window handle missing")
        return

    login_window.events.closed += _on_closed
    log.info("[TIKTOK-LOGIN] Login window opened")

    deadline = time.monotonic() + TIKTOK_LOGIN_TIMEOUT_S
    creds: tuple[str, str] | None = None
    while time.monotonic() < deadline:
        if closed.is_set():
            _set_login_state("cancelled")
            return
        try:
            creds = extract_session_cookies(login_window.get_cookies() or [])
        except Exception as exc:  # page not loaded yet / backend hiccup
            log.debug("[TIKTOK-LOGIN] Cookie poll failed: %s", exc)
        if creds:
            break
        time.sleep(1.0)

    try:
        login_window.destroy()
    except Exception:  # window may already be gone
        pass

    if not creds:
        _set_login_state("timeout")
        log.warning("[TIKTOK-LOGIN] Timed out without a session cookie")
        return

    session_id, tt_target_idc = creds
    try:
        info = save_chatbot_session(session_id, tt_target_idc)
    except Exception as exc:  # validation/storage errors surface to the GUI
        _set_login_state("error", error=f"{type(exc).__name__}: {exc}")
        get_crash_manager().report_error(
            CHATBOT_0004, detail=f"{type(exc).__name__}: {exc}"
        )
        return

    request_bridge_reload()
    masked = str(info.get("masked_session_id") or "")
    _set_login_state("success", masked=masked)
    log.info("[TIKTOK-LOGIN] Session stored (%s)", masked or "?")


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
        with urllib.request.urlopen(
            f"{API_URL}/api/v1/health", timeout=timeout
        ) as resp:
            return resp.status == 200
    except OSError:
        return False


def _api_reachable(timeout: float = 1.0) -> bool:
    """Raw HTTP check — returns True if the API health endpoint responds.

    Unlike :func:`_api_ready`, this ignores any in-progress shutdown state
    and is used by the atexit cleanup handler which *must* reach the API
    to request a graceful shutdown.
    """
    try:
        with urllib.request.urlopen(
            f"{API_URL}/api/v1/health", timeout=timeout
        ) as resp:
            return resp.status == 200
    except OSError:
        return False


def _signed_shutdown_headers(identity: str) -> dict[str, str] | None:
    """Build the signed headers for a shutdown request (or None on failure).

    A valid HMAC signature is appended for every shutdown call so the API
    can verify — and later audit — exactly who requested the shutdown.
    """
    headers = make_headers(identity)
    if not headers:
        log.warning(
            "[SHUTDOWN-AUTH] Cannot sign shutdown request — no shared secret "
            "available yet (identity=%s). The API will reject the request.",
            identity,
        )
        return None
    log.debug("[SHUTDOWN-AUTH] Signed shutdown request (identity=%s)", identity)
    return headers


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
        log.warning("close_app() called — destroying window")
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

    def download_file_b64(self, data: str, filename: str) -> str:
        """Save base64-encoded binary content to Downloads and return the path."""
        downloads = Path.home() / "Downloads"
        try:
            downloads.mkdir(parents=True, exist_ok=True)
        except OSError:
            downloads = Path.home()
        path = downloads / filename
        try:
            path.write_bytes(base64.b64decode(data))
            return str(path)
        except (OSError, ValueError) as e:
            log.warning("Failed to save file: %s", e)
            return f"error:{e}"

    # ---- Server control ----
    def start_system(self) -> str:
        """Start the full system (start.exe)."""
        global _full_system_proc
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
                    _full_system_proc = subprocess.Popen(
                        [str(START_EXE)], stdout=lf, stderr=lf, stdin=subprocess.DEVNULL
                    )
            log.info(
                "Full system process started (PID %s)",
                _full_system_proc.pid if _full_system_proc else "?",
            )
            return "started"
        except OSError as e:
            log.error("Failed to start full system: %s", e)
            return f"error:{e}"

    def stop_system(self) -> str:
        """Stop the system process gracefully via API, then force-kill if needed."""
        global _full_system_proc
        log.warning(
            "stop_system() called — _full_system_proc=%s, poll=%s",
            _full_system_proc,
            _full_system_proc.poll() if _full_system_proc is not None else "N/A",
        )
        if _full_system_proc is None or _full_system_proc.poll() is not None:
            return "not_running"

        # Write marker FIRST so a new GUI can detect the shutdown
        _write_shutdown_marker()

        # Prefer graceful shutdown through the API.
        headers = _signed_shutdown_headers("gui.py:stop_system")
        if headers is not None:
            headers["Content-Type"] = "application/json"
            try:
                req = urllib.request.Request(
                    f"{API_URL}/api/v1/shutdown/now",
                    method="POST",
                    headers=headers,
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

    def get_shutdown_status(self) -> dict[str, Any]:
        """Return whether a previous supervisor shutdown is still in progress.

        The launcher calls this to decide whether to enable the Start button.
        Returns ``{"shutting_down": True/False}``.
        """
        return {"shutting_down": _shutdown_pending()}

    # ---- TikTok webview login ----
    def open_tiktok_login(self) -> str:
        """Open a TikTok login window; cookies are captured automatically.

        Non-blocking: starts a supervised worker and returns immediately.
        The dashboard polls :meth:`get_tiktok_login_state` for the result.
        """
        with _login_lock:
            if _login_state["state"] == "waiting":
                return "already_running"
            # NOTE: _set_login_state() must NOT be called here — it would
            # re-acquire this non-reentrant lock and deadlock the bridge
            # call (the button would silently do nothing).
            _login_state["state"] = "waiting"
            _login_state["masked_session_id"] = None
            _login_state["error"] = ""
        t = get_crash_manager().supervised_thread(
            target=_tiktok_login_worker, name="tiktok-login", daemon=True
        )
        t.start()
        return "started"

    def get_tiktok_login_state(self) -> dict[str, Any]:
        """Current webview-login state (secret-free, poll from JS)."""
        with _login_lock:
            return dict(_login_state)

    def connect_remote(self, host: str, port: str = "29185", api_key: str = "") -> str:
        """Verify a remote TikTok2Mc instance and navigate to its dashboard.

        Returns "ok" on success, or "error:<message>" on failure.
        """
        host = (host or "").strip()
        port = (port or "29185").strip()
        if not host:
            return "error:empty host"

        base = f"http://{host}:{port}"
        health_url = f"{base}/api/v1/health"
        headers: dict[str, str] = {}
        if api_key:
            headers["X-API-Key"] = api_key.strip()

        try:
            req = urllib.request.Request(health_url, headers=headers)
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                if resp.status not in (200, 401):
                    return f"error:unexpected status {resp.status}"
        except urllib.error.HTTPError as exc:
            # 401 means the server is reachable but requires auth — that's fine.
            if exc.code != 401:
                return f"error:HTTP {exc.code}"
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            return f"error:{exc}"

        dashboard_url = f"{base}/gui/index.html"
        if api_key:
            dashboard_url += f"?key={urllib.parse.quote(api_key.strip())}"

        if _window is not None and hasattr(_window, "load_url"):
            try:
                _window.load_url(dashboard_url)
                return "ok"
            except Exception as exc:
                return f"error:{exc}"
        return "error:no window"


def _cleanup_processes():
    """Terminate any spawned processes on GUI exit."""
    log.warning(
        "atexit _cleanup_processes() called — PID=%s, _full_system_proc=%s, poll=%s",
        os.getpid(),
        _full_system_proc,
        _full_system_proc.poll() if _full_system_proc is not None else "N/A",
    )
    if _full_system_proc is None or _full_system_proc.poll() is not None:
        log.debug("Cleanup: no managed process to stop, skipping.")
        return

    # Write marker FIRST — before any async shutdown request.
    # A new GUI checks this file to know a shutdown is in progress.
    _write_shutdown_marker()

    log.info(
        "Cleanup: managed process (PID %s) still running, attempting graceful shutdown.",
        _full_system_proc.pid,
    )

    # Only send shutdown request if the API is actually reachable.
    # If the API is already down, skip the request and force-kill directly.
    api_was_running = _api_reachable(timeout=1.0)
    if api_was_running:
        headers = _signed_shutdown_headers("gui.py:_cleanup_processes")
        if headers is not None:
            headers["Content-Type"] = "application/json"
            try:
                req = urllib.request.Request(
                    f"{API_URL}/api/v1/shutdown/now",
                    method="POST",
                    headers=headers,
                    data=b"{}",
                )
                urllib.request.urlopen(req, timeout=3.0)
                log.info("Cleanup: shutdown request sent, waiting for process to exit.")
                for _ in range(20):
                    if _full_system_proc.poll() is not None:
                        log.info("Cleanup: process exited cleanly.")
                        return
                    time.sleep(0.25)
                log.warning(
                    "Cleanup: process did not exit within 5s after API shutdown request."
                )
            except urllib.error.HTTPError as exc:
                log.warning("Cleanup: API shutdown request rejected: %s", exc)
            except OSError as exc:
                log.warning("Cleanup: API shutdown request failed: %s", exc)
        else:
            log.warning("Cleanup: cannot sign shutdown request, force-killing.")
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


def _write_shutdown_marker() -> None:
    """Write a marker file BEFORE initiating shutdown.

    This is called from stop_system() and _cleanup_processes() to signal
    to a future GUI instance that a shutdown is about to happen.  The
    marker is written synchronously BEFORE any asynchronous shutdown
    request, so there is no race condition.
    """
    try:
        SHUTDOWN_PENDING.parent.mkdir(parents=True, exist_ok=True)
        SHUTDOWN_PENDING.write_text(str(os.getpid()), encoding="utf-8")
    except OSError as exc:
        log.warning("Failed to write shutdown marker: %s", exc)


def _clear_shutdown_marker() -> None:
    """Remove the shutdown marker file."""
    try:
        if SHUTDOWN_PENDING.exists():
            SHUTDOWN_PENDING.unlink()
    except OSError:
        pass


def _shutdown_pending() -> bool:
    """Return True if a shutdown marker exists and the PID that wrote it
    is still alive (meaning the old GUI's cleanup is still running).

    If the PID is dead, the marker is stale and gets cleaned up.
    """
    if not SHUTDOWN_PENDING.exists():
        return False
    try:
        pid = int(SHUTDOWN_PENDING.read_text().strip())
        if IS_WINDOWS:
            import ctypes

            handle = ctypes.windll.kernel32.OpenProcess(0x0400, False, pid)
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
                return True
            # PID dead → stale marker, clean it up
            _clear_shutdown_marker()
            return False
        else:
            os.kill(pid, 0)
            return True
    except (OSError, ValueError):
        _clear_shutdown_marker()
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

    # If a previous supervisor is still shutting down, skip the API check
    # entirely and go straight to the launcher — the JS side will detect
    # the shutdown state, disable the Start button, and wait.
    if _shutdown_pending():
        log.info("Shutdown marker found — showing launcher")
    elif _api_ready(timeout=1.0):
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
                                        log.info(
                                            "API came online — switched to dashboard."
                                        )
                                    except (
                                        Exception
                                    ) as nav_err:  # best-effort navigation
                                        log.warning(
                                            "Navigation to dashboard failed: %s",
                                            nav_err,
                                        )
                        break
                except Exception as exc:  # poll loop must never die
                    log.debug("Poll error: %s", exc)

        t = get_crash_manager().supervised_thread(
            target=_poll_api, name="gui-api-poll", daemon=True
        )
        t.start()

    def _on_closing():
        log.warning(
            "GUI WINDOW CLOSING — _on_closing() called. Stack trace:\n%s",
            "".join(traceback.format_stack()),
        )
        return True

    _window.events.closing += _on_closing
    try:
        if sys.platform == "linux":
            webview.start(gui="qt", debug=False)
        else:
            webview.start(debug=False)
        log.warning("webview.start() returned — window closed or destroyed")
        log.warning("main() returning — atexit handlers will fire next")
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
    log.info("GUI process starting — PID=%s", os.getpid())
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
