import asyncio
import logging
import time
from pathlib import Path

from core.api.eventbus import event_bus

log = logging.getLogger(__name__)


class ConsoleCapture:
    """Tails ``logs/latest.log`` from the Minecraft server directory.

    Publishes each new line as a ``server.console`` event on the EventBus
    so it reaches the GUI console terminal via SSE.
    """

    def __init__(self, server_dir: Path) -> None:
        self._log_path = server_dir / "logs" / "latest.log"
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run())
        log.info("ConsoleCapture started — watching %s", self._log_path)

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        log.info("ConsoleCapture stopped")

    async def _run(self) -> None:
        while self._running:
            try:
                await self._tail()
            except asyncio.CancelledError:
                break
            except Exception:
                log.exception("ConsoleCapture error, restarting in 5s")
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
                            {"line": line, "timestamp": time.time()},
                        )
                else:
                    # Check for log rotation
                    if not self._log_path.exists() or self._get_inode() != inode:
                        log.info("Log file rotated, reopening")
                        break
                    await asyncio.sleep(0.1)

    def _get_inode(self) -> int:
        try:
            return self._log_path.stat().st_ino
        except (OSError, AttributeError):
            return 0


_console_capture: ConsoleCapture | None = None


def get_console_capture() -> ConsoleCapture | None:
    return _console_capture


def init_console_capture(server_dir: Path) -> ConsoleCapture:
    global _console_capture
    _console_capture = ConsoleCapture(server_dir)
    return _console_capture
