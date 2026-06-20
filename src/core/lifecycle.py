#!/usr/bin/env python3
"""Lifecycle supervisor for TikTok2Mc.

This module provides the central process-management architecture for the
application.  It is intentionally small and focused: it starts, monitors,
and stops child processes, and it exposes a deterministic state machine for
startup, shutdown, and restart.

Design goals
------------
1. **No daemon threads for critical services.**
   The API server runs as an asyncio task in the supervisor's event loop,
   not in a daemon thread.  This gives us real graceful shutdown via task
   cancellation and proper lifespan hook execution.

2. **GUI survives backend restart.**
   The GUI process is classified as a *shell* process.  During a normal
   restart the supervisor stops all backend services but leaves the GUI
   alive.  The GUI detects the restart through the API health endpoint / SSE
   and reloads the dashboard when the backend comes back.

3. **Explicit state machine.**
   ``SupervisorState`` makes the lifecycle explicit: idle, starting,
   running, restarting, shutting_down, complete.  Every command checks the
   state and refuses illegal transitions.

4. **Wait for processes and ports.**
   Stopping a child waits (with a timeout) for the process to actually exit.
   Restarting waits for the API port to become free before binding it again.

5. **Direct command dispatch.**
   REST endpoints and the console command loop call supervisor methods
   directly.  File-based signal files are still supported as a fallback for
   external scripts / CLI tools.

6. **PyInstaller-safe restart.**
   When the supervisor itself must be restarted (e.g. after an update) it
   spawns a fresh, independent process using ``PYINSTALLER_RESET_ENVIRONMENT``
   as required by PyInstaller 6.9+.
"""

from __future__ import annotations

import asyncio
import enum
import json
import logging
import os
import shlex
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from core.paths import get_base_dir, get_root_dir

log = logging.getLogger(__name__)

IS_WINDOWS = sys.platform == "win32"


class _ProcessStartupError(Exception):
    """Raised when a child process fails to start.

    *intentional* is True when the process exited with code 0, which usually
    means it chose not to run (e.g. a single-instance guard).
    """

    def __init__(self, message: str, intentional: bool = False) -> None:
        super().__init__(message)
        self.intentional = intentional
SUFFIX = ".exe" if IS_WINDOWS else ".bin"


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------


class SupervisorState(str, enum.Enum):
    """Lifecycle states of the supervisor."""

    IDLE = "idle"
    STARTING = "starting"
    RUNNING = "running"
    COUNTDOWN = "countdown"
    RESTARTING = "restarting"
    SHUTTING_DOWN = "shutting_down"
    COMPLETE = "complete"


class ProcessState(str, enum.Enum):
    """Lifecycle states of a managed child process."""

    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class ManagedProcess:
    """A child process known to the supervisor."""

    name: str
    cmd: list[str]
    # If True, this process is a UI shell and survives backend restart.
    shell: bool = False
    # If True, hide the console window on Windows.
    hidden: bool = False
    # Optional working directory.
    cwd: Path | None = None
    # Optional environment overrides.
    env: dict[str, str] | None = None
    # Optional post-spawn callback (e.g. sandbox limits).
    post_spawn: Callable[[subprocess.Popen], None] | None = None
    # Runtime state
    state: ProcessState = field(default=ProcessState.STOPPED)
    proc: subprocess.Popen | None = field(default=None, repr=False)
    session_name: str | None = field(default=None)
    start_time: float = field(default=0.0)
    restart_count: int = field(default=0)


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def _sanitize_session_name(name: str) -> str:
    return name.replace(" ", "-").replace("/", "-").lower()


def _build_display_env_tmux() -> list[str]:
    """Build -e flags for tmux new-session to forward display vars."""
    args: list[str] = []
    for var in ("DISPLAY", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR", "SERVER_HOST"):
        val = os.environ.get(var)
        if val:
            args.extend(["-e", f"{var}={val}"])
    return args


def _build_display_env_screen() -> list[str]:
    """Build env prefix for screen sessions to forward display vars."""
    env_args: list[str] = []
    for var in ("DISPLAY", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR", "SERVER_HOST"):
        val = os.environ.get(var)
        if val:
            env_args.append(f"{var}={val}")
    if env_args:
        return ["env"] + env_args
    return []


def _port_is_free(host: str, port: int) -> bool:
    """Return True if *port* on *host* is available to bind."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((host, port))
            return True
    except OSError:
        return False


async def _wait_for_port_free(
    host: str,
    port: int,
    timeout: float = 10.0,
    interval: float = 0.25,
) -> bool:
    """Wait until *port* is free or *timeout* expires."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _port_is_free(host, port):
            return True
        await asyncio.sleep(interval)
    return _port_is_free(host, port)


def _health_check(base_url: str) -> bool:
    """Synchronous health check helper for asyncio.to_thread."""
    try:
        # Cache-bust to avoid reusing a stale connection.
        url = f"{base_url}/health?_={time.time()}"
        req = urllib.request.Request(url, headers={"Connection": "close"})
        with urllib.request.urlopen(req, timeout=1) as resp:
            return resp.status == 200
    except (urllib.error.URLError, urllib.error.HTTPError, OSError):
        return False


async def _wait_for_api_ready(
    base_url: str,
    timeout: float = 15.0,
    interval: float = 0.25,
) -> bool:
    """Poll the health endpoint until it responds or *timeout* expires."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        # Run the blocking urllib call in a thread so the API server task
        # in the same event loop can make progress.
        if await asyncio.to_thread(_health_check, base_url):
            return True
        await asyncio.sleep(interval)
    return False


# ---------------------------------------------------------------------------
# Supervisor
# ---------------------------------------------------------------------------


class ProcessSupervisor:
    """Owns the lifecycle of the application and its child processes.

    The supervisor is a singleton-like object created once in ``start.py``.
    It is safe to import from other modules in the same process to dispatch
    lifecycle commands directly.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._state = SupervisorState.IDLE
        self._processes: dict[str, ManagedProcess] = {}
        self._api_server_task: asyncio.Task | None = None
        self._api_server: Any | None = None
        self._api_base_url: str = ""
        self._shutdown_complete_event: asyncio.Event | None = None
        self._state_listeners: list[Callable[[SupervisorState], None]] = []
        self._loop: asyncio.AbstractEventLoop | None = None
        self._session_tool: str | None = None
        self._linux_sessions: list[str] = []
        self._runtime_dir = (get_root_dir() / "core" / "runtime").resolve()
        self._runtime_dir.mkdir(parents=True, exist_ok=True)
        self.shutdown_delay = 30.0

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------

    @property
    def state(self) -> SupervisorState:
        with self._lock:
            return self._state

    @state.setter
    def state(self, value: SupervisorState) -> None:
        with self._lock:
            old = self._state
            self._state = value
        if old != value:
            log.info("[SUPERVISOR] State: %s -> %s", old.value, value.value)
            for listener in self._state_listeners:
                try:
                    listener(value)
                except Exception as exc:
                    log.warning("State listener failed: %s", exc)

    def add_state_listener(self, callback: Callable[[SupervisorState], None]) -> None:
        self._state_listeners.append(callback)

    def remove_state_listener(
        self, callback: Callable[[SupervisorState], None]
    ) -> None:
        try:
            self._state_listeners.remove(callback)
        except ValueError:
            pass

    def _assert_state(self, allowed: set[SupervisorState], action: str) -> None:
        if self.state not in allowed:
            raise RuntimeError(
                f"Cannot {action} while supervisor is in state {self.state.value}"
            )

    # ------------------------------------------------------------------
    # Configuration / session detection
    # ------------------------------------------------------------------

    def configure(
        self,
        *,
        session_tool: str | None = None,
        api_base_url: str = "",
    ) -> None:
        self._session_tool = session_tool
        self._api_base_url = api_base_url

    # ------------------------------------------------------------------
    # Process registration
    # ------------------------------------------------------------------

    def register(
        self,
        name: str,
        cmd: list[str],
        *,
        shell: bool = False,
        hidden: bool = False,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
        post_spawn: Callable[[subprocess.Popen], None] | None = None,
    ) -> ManagedProcess:
        """Register a process to be managed.

        Registration does not start the process; call ``start`` or
        ``start_all`` afterwards.
        """
        with self._lock:
            if name in self._processes:
                raise ValueError(f"Process '{name}' is already registered")
            proc = ManagedProcess(
                name=name,
                cmd=cmd,
                shell=shell,
                hidden=hidden,
                cwd=cwd,
                env=env,
                post_spawn=post_spawn,
            )
            self._processes[name] = proc
            return proc

    def unregister(self, name: str) -> bool:
        """Remove a registered process.  Stops it first if running."""
        with self._lock:
            proc = self._processes.get(name)
            if proc is None:
                return False
        # Stop outside the lock because stop() may need to await.
        if proc.state in (ProcessState.STARTING, ProcessState.RUNNING):
            asyncio.create_task(self.stop(name))
        with self._lock:
            del self._processes[name]
        return True

    def get(self, name: str) -> ManagedProcess | None:
        with self._lock:
            return self._processes.get(name)

    def list_processes(self) -> list[ManagedProcess]:
        with self._lock:
            return list(self._processes.values())

    # ------------------------------------------------------------------
    # Starting processes
    # ------------------------------------------------------------------

    async def start(self, name: str) -> bool:
        """Start a single registered process."""
        proc = self.get(name)
        if proc is None:
            log.error("[SUPERVISOR] Unknown process: %s", name)
            return False

        with self._lock:
            if proc.state in (ProcessState.STARTING, ProcessState.RUNNING):
                log.info("[SUPERVISOR] %s is already %s", name, proc.state.value)
                return True
            proc.state = ProcessState.STARTING

        try:
            await self._do_start(proc)
            proc.state = ProcessState.RUNNING
            proc.start_time = time.time()
            log.info("[SUPERVISOR] %s started (PID %s)", name, proc.proc.pid if proc.proc else "?")
            return True
        except _ProcessStartupError as exc:
            if exc.intentional:
                log.warning("[SUPERVISOR] %s", exc)
                proc.state = ProcessState.STOPPED
            else:
                log.exception("[SUPERVISOR] Failed to start %s: %s", name, exc)
                proc.state = ProcessState.FAILED
            return False
        except Exception as exc:
            log.exception("[SUPERVISOR] Failed to start %s: %s", name, exc)
            proc.state = ProcessState.FAILED
            return False

    async def _do_start(self, proc: ManagedProcess) -> None:
        """Low-level process start with cross-platform window/session handling."""
        cmd = list(proc.cmd)
        cwd = str(proc.cwd) if proc.cwd else str(get_base_dir())
        env = os.environ.copy()
        if proc.env:
            env.update(proc.env)
        env["PYTHONIOENCODING"] = "utf-8"

        if not shutil.which(cmd[0]) and not Path(cmd[0]).exists():
            raise FileNotFoundError(f"Executable not found: {cmd[0]}")

        if IS_WINDOWS:
            kwargs: dict[str, Any] = {
                "cwd": cwd,
                "env": env,
                "close_fds": True,
            }
            flags = subprocess.CREATE_NO_WINDOW if proc.hidden else subprocess.CREATE_NEW_CONSOLE
            kwargs["creationflags"] = flags
            proc.proc = subprocess.Popen(cmd, **kwargs)
        elif self._session_tool == "tmux":
            session_name = _sanitize_session_name(f"mc-{proc.name}")
            await asyncio.to_thread(
                subprocess.run,
                ["tmux", "kill-session", "-t", session_name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            subprocess.Popen(
                ["tmux", "new-session", "-d", "-s", session_name]
                + _build_display_env_tmux()
                + cmd,
                cwd=cwd,
                env=env,
            )
            proc.session_name = session_name
            self._linux_sessions.append(session_name)
            proc.proc = None
        elif self._session_tool == "screen":
            session_name = _sanitize_session_name(f"mc-{proc.name}")
            await asyncio.to_thread(
                subprocess.run,
                ["screen", "-X", "-S", session_name, "quit"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            subprocess.Popen(
                ["screen", "-dmS", session_name]
                + _build_display_env_screen()
                + cmd,
                cwd=cwd,
                env=env,
            )
            proc.session_name = session_name
            self._linux_sessions.append(session_name)
            proc.proc = None
        else:
            log_dir = get_root_dir() / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / f"{_sanitize_session_name(proc.name)}.log"
            kwargs = {"cwd": cwd, "env": env}
            with open(log_file, "w", encoding="utf-8") as lf:
                proc.proc = subprocess.Popen(cmd, stdout=lf, stderr=lf, **kwargs)

        if proc.proc and proc.post_spawn:
            try:
                proc.post_spawn(proc.proc)
            except Exception as exc:
                log.warning("[SUPERVISOR] post_spawn failed for %s: %s", proc.name, exc)

        # Brief wait to catch immediate startup failures.
        if proc.proc is not None:
            for _ in range(20):
                await asyncio.sleep(0.05)
                if proc.proc.poll() is not None:
                    code = proc.proc.returncode
                    raise _ProcessStartupError(
                        f"{proc.name} exited immediately with code {code}",
                        intentional=(code == 0),
                    )

    async def start_all(self) -> dict[str, bool]:
        """Start all registered non-shell backend processes in parallel."""
        names = [proc.name for proc in self.list_processes() if not proc.shell]
        results_list = await asyncio.gather(
            *(self.start(name) for name in names),
            return_exceptions=True,
        )
        results: dict[str, bool] = {}
        for name, res in zip(names, results_list):
            if isinstance(res, Exception):
                log.warning("[SUPERVISOR] start_all: %s raised %s", name, res)
                results[name] = False
            else:
                results[name] = res
        return results

    async def start_shell(self) -> dict[str, bool]:
        """Start registered shell processes (e.g. the GUI) in parallel."""
        names = [proc.name for proc in self.list_processes() if proc.shell]
        results_list = await asyncio.gather(
            *(self.start(name) for name in names),
            return_exceptions=True,
        )
        results: dict[str, bool] = {}
        for name, res in zip(names, results_list):
            if isinstance(res, Exception):
                log.warning("[SUPERVISOR] start_shell: %s raised %s", name, res)
                results[name] = False
            else:
                results[name] = res
        return results

    # ------------------------------------------------------------------
    # Stopping processes
    # ------------------------------------------------------------------

    async def stop(
        self,
        name: str,
        *,
        graceful_timeout: float = 5.0,
        force_timeout: float = 5.0,
    ) -> bool:
        """Stop a single process gracefully, then forcefully if needed."""
        proc = self.get(name)
        if proc is None:
            log.warning("[SUPERVISOR] stop() unknown process: %s", name)
            return False

        with self._lock:
            if proc.state in (ProcessState.STOPPED, ProcessState.STOPPING, ProcessState.FAILED):
                if proc.state == ProcessState.STOPPED:
                    return True
            proc.state = ProcessState.STOPPING

        try:
            await self._do_stop(proc, graceful_timeout=graceful_timeout, force_timeout=force_timeout)
            proc.state = ProcessState.STOPPED
            proc.proc = None
            proc.session_name = None
            log.info("[SUPERVISOR] %s stopped", name)
            return True
        except Exception as exc:
            log.exception("[SUPERVISOR] Failed to stop %s: %s", name, exc)
            proc.state = ProcessState.FAILED
            return False

    async def _do_stop(
        self,
        proc: ManagedProcess,
        *,
        graceful_timeout: float,
        force_timeout: float,
    ) -> None:
        """Low-level stop with tmux/screen/Popen handling."""
        # Linux session stop
        if not IS_WINDOWS and self._session_tool and proc.session_name:
            try:
                if self._session_tool == "tmux":
                    await asyncio.to_thread(
                        subprocess.run,
                        ["tmux", "kill-session", "-t", proc.session_name],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                elif self._session_tool == "screen":
                    await asyncio.to_thread(
                        subprocess.run,
                        ["screen", "-X", "-S", proc.session_name, "quit"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                if proc.session_name in self._linux_sessions:
                    self._linux_sessions.remove(proc.session_name)
            except Exception as exc:
                log.warning("[SUPERVISOR] Session stop failed for %s: %s", proc.name, exc)
            return

        # Direct Popen stop
        if proc.proc is None or proc.proc.poll() is not None:
            return

        if IS_WINDOWS:
            try:
                await asyncio.to_thread(
                    subprocess.run,
                    ["taskkill", "/PID", str(proc.proc.pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    timeout=2.0,
                )
                # Wait briefly for graceful termination
                try:
                    await asyncio.to_thread(proc.proc.wait, timeout=graceful_timeout)
                    return
                except subprocess.TimeoutExpired:
                    pass
            except Exception as exc:
                log.warning("[SUPERVISOR] taskkill failed for %s: %s", proc.name, exc)

            # Force kill tree
            try:
                await asyncio.to_thread(
                    subprocess.run,
                    ["taskkill", "/F", "/T", "/PID", str(proc.proc.pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    timeout=force_timeout,
                )
                await asyncio.to_thread(proc.proc.wait, timeout=force_timeout)
            except Exception as exc:
                log.warning("[SUPERVISOR] Force kill failed for %s: %s", proc.name, exc)
        else:
            try:
                proc.proc.terminate()
                await asyncio.to_thread(proc.proc.wait, timeout=graceful_timeout)
                return
            except subprocess.TimeoutExpired:
                try:
                    proc.proc.kill()
                    await asyncio.to_thread(proc.proc.wait, timeout=force_timeout)
                except Exception as exc:
                    log.warning("[SUPERVISOR] Kill failed for %s: %s", proc.name, exc)
            except Exception as exc:
                log.warning("[SUPERVISOR] Terminate failed for %s: %s", proc.name, exc)

    async def stop_all(
        self,
        *,
        keep_shell: bool = False,
        graceful_timeout: float = 5.0,
        force_timeout: float = 5.0,
    ) -> dict[str, bool]:
        """Stop all registered processes in parallel.

        If *keep_shell* is True, shell processes (the GUI) are left running.
        """
        names = [
            proc.name
            for proc in self.list_processes()
            if not (keep_shell and proc.shell)
        ]
        results_list = await asyncio.gather(
            *(
                self.stop(
                    name,
                    graceful_timeout=graceful_timeout,
                    force_timeout=force_timeout,
                )
                for name in names
            ),
            return_exceptions=True,
        )
        results: dict[str, bool] = {}
        for name, res in zip(names, results_list):
            if isinstance(res, Exception):
                log.warning("[SUPERVISOR] stop_all: %s raised %s", name, res)
                results[name] = False
            else:
                results[name] = res
        return results

    # ------------------------------------------------------------------
    # API server lifecycle (asyncio task, not thread)
    # ------------------------------------------------------------------

    def set_api_server_task(
        self, task: asyncio.Task, server: Any, base_url: str
    ) -> None:
        """Store the running API server task and uvicorn server object."""
        self._api_server_task = task
        self._api_server = server
        self._api_base_url = base_url

    async def stop_api_server(self, timeout: float = 5.0) -> bool:
        """Gracefully stop the API server task and wait for port release."""
        if self._api_server_task is None or self._api_server_task.done():
            return True

        log.info("[SUPERVISOR] Stopping API server...")
        if self._api_server is not None:
            try:
                self._api_server.should_exit = True
            except Exception as exc:
                log.warning("[SUPERVISOR] Error setting should_exit: %s", exc)

        self._api_server_task.cancel()
        try:
            await asyncio.wait_for(self._api_server_task, timeout=timeout)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            log.warning("[SUPERVISOR] API server task did not cancel cleanly")

        self._api_server_task = None
        self._api_server = None

        # Extract host/port from base_url and wait for release
        try:
            host, port = self._parse_api_url(self._api_base_url)
            freed = await _wait_for_port_free(host, port, timeout=timeout)
            if not freed:
                log.warning("[SUPERVISOR] API port %s:%s still in use", host, port)
                return False
        except Exception as exc:
            log.warning("[SUPERVISOR] Could not parse API URL: %s", exc)

        log.info("[SUPERVISOR] API server stopped")
        return True

    @staticmethod
    def _parse_api_url(base_url: str) -> tuple[str, int]:
        """Parse host and port from an API base URL like http://127.0.0.1:29185/api/v1."""
        from urllib.parse import urlparse

        parsed = urlparse(base_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 80
        return host, port

    # ------------------------------------------------------------------
    # High-level lifecycle commands
    # ------------------------------------------------------------------

    async def shutdown(self, *, delay: float = 0.0, restart: bool = False) -> None:
        """Shut down the application.

        If *restart* is True, the GUI shell is kept alive and the supervisor
        will transition back to RUNNING after restarting backend services.
        """
        self._assert_state(
            {SupervisorState.IDLE, SupervisorState.STARTING, SupervisorState.RUNNING},
            "shut down" if not restart else "restart",
        )

        if delay > 0 and not restart:
            # Console countdown handled by caller; just sleep here.
            await asyncio.sleep(delay)

        self.state = SupervisorState.SHUTTING_DOWN if not restart else SupervisorState.RESTARTING

        # 1. Stop all backend child processes.
        await self.stop_all(keep_shell=restart, graceful_timeout=5.0, force_timeout=5.0)

        if not restart:
            # 2a. Full shutdown: stop the API server, then the GUI.
            await self.stop_api_server(timeout=5.0)
            await self.stop_all(graceful_timeout=5.0, force_timeout=5.0)
            self.state = SupervisorState.COMPLETE
            if self._shutdown_complete_event is not None:
                self._shutdown_complete_event.set()
        else:
            # 2b. Restart: keep API server + GUI alive, restart backend children.
            log.info("[SUPERVISOR] Restarting backend services...")
            await asyncio.sleep(0.5)  # Let OS release handles.
            await self._restart_backend()

    async def _restart_backend(self) -> None:
        """Restart backend children after a shutdown(keep_shell=True).

        The API server itself is kept alive in this design, so we only confirm
        it is still reachable before declaring the restart complete.
        """
        self.state = SupervisorState.STARTING

        # Start backend children again.
        await self.start_all()

        # Confirm the API server is still reachable.
        if self._api_base_url:
            if not await _wait_for_api_ready(self._api_base_url, timeout=15.0):
                log.warning(
                    "[SUPERVISOR] API server was not reachable after restart; "
                    "children are running but the dashboard may need a manual reload."
                )

        # Notify listeners (including the GUI via SSE) that the backend is back.
        try:
            from core.api.eventbus import event_bus
            await event_bus.publish("server.started", {})
        except Exception as exc:
            log.debug("[SUPERVISOR] Could not publish restart completion event: %s", exc)

        self.state = SupervisorState.RUNNING
        log.info("[SUPERVISOR] Restart complete")

    async def restart(self) -> None:
        """Public restart command: shutdown and restart backend, keep GUI alive."""
        self._assert_state(
            {SupervisorState.IDLE, SupervisorState.STARTING, SupervisorState.RUNNING},
            "restart",
        )
        await self.shutdown(restart=True)

    async def full_exit(self) -> None:
        """Exit the supervisor process cleanly."""
        await self.shutdown()
        # Signal the event loop to exit.
        if self._loop is not None:
            self._loop.stop()

    async def shutdown_countdown(
        self,
        delay: float | None = None,
        cancel_event: asyncio.Event | None = None,
    ) -> bool:
        """Count down from *delay* seconds, then shut down.

        Returns True if shutdown completed, False if cancelled.
        """
        self._assert_state(
            {SupervisorState.IDLE, SupervisorState.STARTING, SupervisorState.RUNNING},
            "start shutdown countdown",
        )
        if delay is None:
            delay = self.shutdown_delay
        if cancel_event is None:
            cancel_event = shutdown_cancel_event
        self.state = SupervisorState.COUNTDOWN
        remaining = int(delay)
        try:
            while remaining > 0:
                if cancel_event.is_set():
                    self.state = SupervisorState.RUNNING
                    self.clear_shutdown_status()
                    return False
                self.write_shutdown_status(remaining, self.state.value)
                log.info("Shutdown in %d seconds... Press 'stop' to cancel.", remaining)
                await asyncio.wait_for(cancel_event.wait(), timeout=1.0)
                if cancel_event.is_set():
                    self.state = SupervisorState.RUNNING
                    self.clear_shutdown_status()
                    return False
                remaining -= 1
        except asyncio.TimeoutError:
            pass

        self.write_shutdown_status(0, SupervisorState.SHUTTING_DOWN.value)
        await self.shutdown()
        return True

    # ------------------------------------------------------------------
    # Monitoring
    # ------------------------------------------------------------------

    async def health_check(self) -> dict[str, Any]:
        """Return a snapshot of process health."""
        result: dict[str, Any] = {"state": self.state.value, "processes": {}}
        for proc in self.list_processes():
            alive = False
            if proc.proc is not None:
                alive = proc.proc.poll() is None
            result["processes"][proc.name] = {
                "state": proc.state.value,
                "alive": alive,
                "restart_count": proc.restart_count,
                "shell": proc.shell,
            }
        return result

    def write_shutdown_status(self, remaining: int | None, state: str) -> None:
        """Write current shutdown state to a runtime file for the API."""
        try:
            status_file = self._runtime_dir / "shutdown_status"
            data = {"remaining": remaining, "state": state}
            status_file.write_text(json.dumps(data), encoding="utf-8")
        except Exception:
            pass

    def clear_shutdown_status(self) -> None:
        try:
            (self._runtime_dir / "shutdown_status").unlink(missing_ok=True)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_supervisor: ProcessSupervisor | None = None

# Shared event used to cancel an active shutdown countdown from the GUI/API.
shutdown_cancel_event = asyncio.Event()


def get_supervisor() -> ProcessSupervisor:
    """Return the global supervisor instance, creating it if necessary."""
    global _supervisor
    if _supervisor is None:
        _supervisor = ProcessSupervisor()
    return _supervisor


def set_supervisor(supervisor: ProcessSupervisor) -> None:
    """Replace the global supervisor instance (used by tests)."""
    global _supervisor
    _supervisor = supervisor
