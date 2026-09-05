"""Standalone update-progress splash window.

Spawned by the GUI launcher right before it closes (so the updater can
replace ``core/gui.exe``). The always-on-top window bridges the gap between
the launcher disappearing and the freshly updated app coming back up, so the
user always sees what is going on.

- Renders the status that ``update.exe`` publishes to
  ``core/runtime/update_status.json`` (checking / downloading % / installing /
  done / error).
- Retires itself when the restarted app is up (a fresh GUI lock PID, or the
  control-plane port answering) and stays open with the failure text when the
  update failed.
- Runs from a throwaway copy under ``data/cache`` so the updater replacing
  ``core/update_progress.exe`` never hits a running binary.

The window uses ``tkinter`` (stdlib) on purpose: the update path must stay
free of heavyweight GUI dependencies (PyQt6/webview), so the splash runs in
any Python environment and PyInstaller bundles it without the Qt runtime.
The GUI toolkit is imported lazily in :func:`main` so the decision logic stays
importable without a display backend (used by tests).
"""

import argparse
import json
import os
import socket
import sys
import time
from pathlib import Path

# Ensure src/ is on the path for development runs (same as gui.py).
_src = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _src not in sys.path:
    sys.path.insert(0, _src)

from core.paths import get_root_dir, get_runtime_dir  # noqa: E402

API_PORT = 29185

TEXTS_EN: dict[str, str] = {
    "title": "TikTok2Mc – Update",
    "preparing": "Preparing update...",
    "checking": "Checking for updates...",
    "downloading": "Downloading update... {p}%",
    "installing": "Installing update...",
    "restarting": "Restarting the program...",
    "error": "The update failed.\nPlease start the program manually.",
    "close": "Close",
}

TEXTS_DE: dict[str, str] = {
    "title": "TikTok2Mc – Update",
    "preparing": "Update wird vorbereitet...",
    "checking": "Prüfe auf Updates...",
    "downloading": "Lade Update herunter... {p}%",
    "installing": "Installiere Update...",
    "restarting": "Programm wird neu gestartet...",
    "error": "Das Update ist fehlgeschlagen.\nBitte starte das Programm manuell.",
    "close": "Schließen",
}


def status_file() -> Path:
    """Path of the update progress file written by ``update.exe``."""
    return (get_runtime_dir() / "update_status.json").resolve()


def gui_lock_file() -> Path:
    """Path of the running-GUI lock file."""
    return (get_root_dir() / "tmp" / "gui.lock").resolve()


def read_status() -> dict | None:
    """Return the current updater status, or ``None`` when unavailable."""
    try:
        path = status_file()
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def read_gui_pid() -> int | None:
    """Return the PID in the GUI lock file, or ``None`` when absent/corrupt."""
    try:
        path = gui_lock_file()
        if not path.exists():
            return None
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        if sys.platform == "win32":
            import ctypes

            handle = ctypes.windll.kernel32.OpenProcess(0x0400, False, pid)
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
                return True
            return False
        import os

        os.kill(pid, 0)
        return True
    except OSError:
        return False


def port_open(port: int = API_PORT) -> bool:
    """Return True when something answers on the control-plane port."""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def new_gui_started(initial_pid: int | None) -> bool:
    """True when a GUI instance different from ``initial_pid`` is alive."""
    for _ in range(20):
        pid = read_gui_pid()
        if pid is not None and pid != initial_pid and _pid_alive(pid):
            return True
        time.sleep(0.1)
    return False


def classify(status: dict | None, *, new_gui: bool, port: bool, done_elapsed: float):
    """Decide what the splash should show.

    Returns a tuple ``(text_key, progress, should_close, is_failure)``:
    - ``text_key`` is one of the translation keys in :data:`TEXTS_EN`
    - ``progress`` is the download percentage or ``None``
    - ``should_close`` retires the window
    - ``is_failure`` switches to the persistent error view

    The splash retires itself only once a *fresh* GUI instance is detected
    (``new_gui`` — a new PID in the GUI lock file, written by the relaunched
    ``gui.exe`` right as it opens its window). A bare answering ``port`` is
    deliberately *not* enough to close: after an update ``start.exe`` relaunches
    and its control-plane API comes up several seconds before the GUI window is
    rendered, so closing on the port alone would leave the user staring at a
    black screen for many seconds. Waiting for the relaunched GUI avoids that
    gap and hands over cleanly to the freshly opened dashboard/launcher window.
    Only an explicit ``error`` phase keeps the failure view up regardless.
    """
    if not status:
        if new_gui:
            return "restarting", None, True, False
        return "preparing", None, False, False
    phase = status.get("phase")
    progress = status.get("progress")
    if phase == "checking":
        return "checking", None, False, False
    if phase == "downloading":
        return "downloading", progress, False, False
    if phase == "installing":
        return "installing", None, False, False
    if phase == "done":
        if done_elapsed > 180:
            return "error", None, False, True
        if new_gui:
            return "restarting", None, True, False
        return "restarting", None, False, False
    if phase == "error":
        return "error", None, False, True
    if new_gui:
        return "restarting", None, True, False
    return "preparing", None, False, False


def main() -> None:
    parser = argparse.ArgumentParser(description="TikTok2Mc update splash")
    parser.add_argument("--lang", default="en", choices=["en", "de"])
    args = parser.parse_args()

    from core.logger import initialize_logging

    log = initialize_logging(__name__)
    texts = TEXTS_DE if args.lang == "de" else TEXTS_EN
    log.info("Update splash starting (lang=%s)", args.lang)

    import tkinter as tk
    from tkinter import ttk

    root = tk.Tk()
    root.title(texts["title"])
    root.geometry("400x165")
    root.resizable(False, False)
    root.attributes("-topmost", True)
    root.configure(bg="#1e1e2e")
    root.protocol("WM_DELETE_WINDOW", lambda: close_window("window closed"))

    status_var = tk.StringVar(root, texts["preparing"])
    tk.Label(
        root,
        textvariable=status_var,
        bg="#1e1e2e",
        fg="#e4e4f0",
        font=("Segoe UI", 11),
    ).pack(pady=(26, 10))

    bar = ttk.Progressbar(root, length=340, maximum=100)
    bar.pack(pady=(0, 14))

    close_btn = tk.Button(
        root,
        text=texts["close"],
        command=lambda: close_window("user closed"),
        bg="#45475a",
        fg="#e4e4f0",
        activebackground="#585b70",
        activeforeground="#e4e4f0",
        relief="flat",
        padx=18,
        pady=4,
    )
    close_btn.place_forget()

    initial_pid = read_gui_pid()
    done_since: float | None = None
    port_streak = 0
    failed = False
    closing = False
    bar_indeterminate = False

    def apply(key: str, percent: int | float | None) -> None:
        """Update the label and progress bar.

        The bar is always shown so the user always sees the splash is alive:
        - during ``downloading`` it fills with the real percentage
        - during checking/installing/restarting it runs as an indeterminate
          (animated) bar instead of disappearing or standing still.
        """
        nonlocal bar_indeterminate
        text = texts[key]
        if key == "downloading":
            if bar_indeterminate:
                bar.stop()
                bar.configure(mode="determinate")
                bar_indeterminate = False
            p = 0.0 if percent is None else round(float(percent), 1)
            text = text.format(p=p)
            bar.config(value=max(0, min(100, int(p))))
        else:
            if not bar_indeterminate:
                bar.stop()
                bar.configure(mode="indeterminate")
                bar_indeterminate = True
                bar.start(10)
        status_var.set(text)

    def close_window(reason: str) -> None:
        nonlocal closing
        if closing:
            return
        closing = True
        log.info("Update splash closing: %s", reason)
        root.after(0, root.destroy)

    def on_timer() -> None:
        nonlocal done_since, port_streak, failed
        if closing:
            return
        status = read_status()
        if status and status.get("phase") == "done":
            done_since = done_since if done_since is not None else time.monotonic()
        else:
            done_since = None
        if port_open():
            port_streak += 1
        else:
            port_streak = 0
        done_phase = bool(status and status.get("phase") == "done")
        # Watch for the restarted GUI whenever the updater is installing or
        # done — the splash must not close on the bare API port (which comes
        # up before the GUI window), only when the relaunched GUI registers.
        new_gui = new_gui_started(initial_pid) if (done_phase or not status) else False
        key, percent, should_close, is_failure = classify(
            status,
            new_gui=new_gui,
            port=port_streak >= 3,
            done_elapsed=time.monotonic() - done_since
            if done_since is not None
            else 0.0,
        )
        if is_failure:
            failed = True
            status_var.set(texts["error"])
            close_btn.place(relx=0.5, rely=0.72, anchor="center")
            bar.place_forget()
        else:
            apply(key, percent)
            if should_close:
                close_window("restarted app is up")
                return
        root.after(500, on_timer)

    # A fresh app may already be up when the splash boots (very fast update).
    # Only close immediately when the relaunched GUI is detected; otherwise
    # fall through to the polling loop which waits for it.
    status = read_status()
    if status and status.get("phase") == "done" and new_gui_started(initial_pid):
        log.info("Update splash closing: already up")
        root.destroy()
    else:
        root.after(500, on_timer)
        root.mainloop()

    log.info("Update splash exited.")


if __name__ == "__main__":
    main()
