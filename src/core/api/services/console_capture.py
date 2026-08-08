import asyncio
import logging
import time
from pathlib import Path

from core.api.eventbus import event_bus

log = logging.getLogger(__name__)


class ConsoleCapture:
    """Tails ``logs/latest.log`` from a Minecraft server directory.

    Publishes each new line as a ``server.console`` event on the EventBus
    so it reaches the GUI console terminal via SSE.
    """

    def __init__(self, instance_id: str, server_dir: Path) -> None:
        self.instance_id = instance_id
        self._log_path = server_dir / "logs" / "latest.log"
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run())
        log.info("ConsoleCapture started for '%s' — watching %s", self.instance_id, self._log_path)

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        log.info("ConsoleCapture stopped for '%s'", self.instance_id)

    async def _run(self) -> None:
        while self._running:
            try:
                await self._tail()
            except asyncio.CancelledError:
                break
            except Exception:  # noqa: BLE001  # capture loop must survive individual failures and restart
                log.exception("ConsoleCapture error for '%s', restarting in 5s", self.instance_id)
                await asyncio.sleep(5)

    async def _tail(self) -> None:
        # Wait for the log file to exist
        while self._running and not self._log_path.exists():
            await asyncio.sleep(2)

        if not self._running:
            return

        # `inode` tracking for log rotation detection (POSIX only).
        # On Windows the file identity is tracked via the open handle
        # so rotation is detected by checking if the path still exists.
        inode = self._get_inode()

        with open(self._log_path, "r", encoding="utf-8", errors="replace") as f:
            f.seek(0, 2)  # start at end, only new lines
            while self._running:
                line = f.readline()
                if line:
                    line = line.rstrip("\n\r")
                    if line:
                        await event_bus.publish(
                            "server.console",
                            {"line": line, "timestamp": time.time(), "instance_id": self.instance_id},
                        )
                else:
                    # Check for log rotation
                    if not self._log_path.exists() or self._get_inode() != inode:
                        log.info("Log file rotated for '%s', reopening", self.instance_id)
                        break
                    await asyncio.sleep(0.1)

    def _get_inode(self) -> int:
        try:
            return self._log_path.stat().st_ino
        except (OSError, AttributeError):
            return 0


# ---------------------------------------------------------------------------
# Per-instance manager
# ---------------------------------------------------------------------------

_captures: dict[str, ConsoleCapture] = {}


def start_instance_capture(instance_id: str, server_dir: Path) -> ConsoleCapture:
    """Start (or restart) console capture for a server instance."""
    stop_instance_capture(instance_id)
    cap = ConsoleCapture(instance_id, server_dir)
    _captures[instance_id] = cap
    # Schedule start on the running event loop if available,
    # otherwise the caller must await cap.start() manually.
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(cap.start())
    except RuntimeError:
        pass
    return cap


def stop_instance_capture(instance_id: str) -> None:
    """Stop console capture for a server instance."""
    cap = _captures.pop(instance_id, None)
    if cap is not None:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(cap.stop())
        except RuntimeError:
            pass


def get_instance_capture(instance_id: str) -> ConsoleCapture | None:
    return _captures.get(instance_id)


# ---------------------------------------------------------------------------
# Legacy single-capture helpers (kept for API lifespan compat)
# ---------------------------------------------------------------------------

_console_capture: ConsoleCapture | None = None


def get_console_capture() -> ConsoleCapture | None:
    return _console_capture


def init_console_capture(server_dir: Path) -> ConsoleCapture:
    global _console_capture
    _console_capture = ConsoleCapture("default", server_dir)
    return _console_capture
