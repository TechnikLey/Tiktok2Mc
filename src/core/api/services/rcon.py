import asyncio
import logging
from mcrcon import MCRcon, MCRconException

log = logging.getLogger(__name__)


class RconService:
    """Manages an RCON connection from the API server to the Minecraft server.

    This is independent of ``main.py``'s RCON worker — it provides direct
    console access for the GUI.
    """

    def __init__(self) -> None:
        self._host = "localhost"
        self._port = 25575
        self._password = ""
        self._conn: MCRcon | None = None
        self._lock = asyncio.Lock()
        self._connected = False

    def configure(self, host: str, port: int, password: str) -> None:
        self._host = host
        self._port = port
        self._password = password

    async def connect(self) -> bool:
        async with self._lock:
            return await self._connect()

    async def _connect(self) -> bool:
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
            await asyncio.wait_for(
                asyncio.to_thread(conn.connect), timeout=5.0
            )
            self._conn = conn
            self._connected = True
            log.info("[RCON] Connected to %s:%s", self._host, self._port)
            return True
        except (MCRconException, OSError, TimeoutError) as e:
            self._conn = None
            self._connected = False
            log.warning("[RCON] Connection failed: %s", e)
            return False

    async def disconnect(self) -> None:
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
        return self._connected

    @property
    def host(self) -> str:
        return self._host

    @property
    def port(self) -> int:
        return self._port


_rcon_service = RconService()


def get_rcon_service() -> RconService:
    return _rcon_service
