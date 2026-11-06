"""Direct RCON connection used by the API server for GUI console access."""

import asyncio
import logging

from mcrcon import MCRcon, MCRconException

# Apply thread-safe mcrcon timeout patch (must import before MCRcon is used).
# See core.mcrcon_compat for why — the upstream signal-based timeouts fail in
# worker threads, which is how RCON is used from the async API server.
from core import mcrcon_compat  # noqa: F401

log = logging.getLogger(__name__)


class RconService:
    """Manages an RCON connection from the API server to the Minecraft server.

    This is independent of ``main.py``'s RCON worker — it provides direct
    console access for the GUI.
    """

    def __init__(self) -> None:
        """Create a disconnected service with default RCON settings."""
        self._host = "localhost"
        self._port = 25575
        self._password = ""
        self._conn: MCRcon | None = None
        self._lock = asyncio.Lock()
        self._connected = False
        self._last_error = ""

    def configure(self, host: str, port: int, password: str) -> None:
        """Set the connection parameters used by the next :meth:`connect`.

An existing connection is not affected until it is reconnected."""

        self._host = host
        self._port = port
        self._password = password

    async def connect(self) -> bool:
        """Connect under the service lock and report success.

Uses the parameters from the last :meth:`configure` call and never
raises for network failures; inspect :attr:`last_error` for the reason."""

        async with self._lock:
            return await self._connect()

    async def _connect(self) -> bool:
        """Replace any existing connection with a fresh one.

The constructor and the connect handshake are each limited to five
seconds and run in worker threads because ``mcrcon`` is blocking. On
failure the connection is cleared and ``False`` is returned."""

        if self._conn:
            try:
                await asyncio.to_thread(self._conn.disconnect)
            except (MCRconException, OSError):
                pass
            self._conn = None
        try:
            conn = await asyncio.wait_for(
                asyncio.to_thread(
                    lambda: MCRcon(self._host, self._password, port=self._port)
                ),
                timeout=5.0,
            )
            await asyncio.wait_for(asyncio.to_thread(conn.connect), timeout=5.0)
            self._conn = conn
            self._connected = True
            self._last_error = ""
            log.info("[RCON] Connected to %s:%s", self._host, self._port)
            return True
        except TimeoutError as e:
            self._conn = None
            self._connected = False
            self._last_error = (
                f"Timed out connecting to RCON at {self._host}:{self._port} — "
                "is the Minecraft server running with RCON enabled?"
            )
            log.warning("[RCON] Connection timed out: %s", e)
            return False
        except (MCRconException, OSError, ValueError) as e:
            self._conn = None
            self._connected = False
            self._last_error = (
                f"RCON connection to {self._host}:{self._port} failed: {e}"
            )
            log.warning("[RCON] Connection failed: %s", e)
            return False

    async def disconnect(self) -> None:
        """Close the connection if one is open and mark the service disconnected."""
        async with self._lock:
            if self._conn:
                try:
                    await asyncio.to_thread(self._conn.disconnect)
                except (MCRconException, OSError):
                    pass
                self._conn = None
            self._connected = False
            log.info("[RCON] Disconnected")

    async def command(self, cmd: str) -> str:
        """Execute a console command and return its response.

Runs the blocking ``mcrcon`` call in a worker thread.

Raises:
    ConnectionError: When no connection is open, or when the command
        fails; in the latter case the broken connection is discarded so the
        next call can reconnect."""

        async with self._lock:
            if not self._conn:
                raise ConnectionError("Not connected to RCON")
            try:
                resp = await asyncio.to_thread(self._conn.command, cmd)
                return resp or ""
            except (MCRconException, OSError) as e:
                self._connected = False
                self._conn = None
                raise ConnectionError(f"RCON command failed: {e}") from e

    @property
    def connected(self) -> bool:
        """Return whether the last connection attempt succeeded."""
        return self._connected

    @property
    def host(self) -> str:
        """Return the configured RCON host."""
        return self._host

    @property
    def port(self) -> int:
        """Return the configured RCON port."""
        return self._port

    @property
    def last_error(self) -> str:
        """Human-readable reason from the last failed connection attempt."""
        return self._last_error


_rcon_service = RconService()


def get_rcon_service() -> RconService:
    """Return the process-wide RCON service used by the API."""
    return _rcon_service
