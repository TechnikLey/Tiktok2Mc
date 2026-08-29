import asyncio
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path

from mcrcon import MCRcon, MCRconException

log = logging.getLogger(__name__)


def _read_server_properties(instance_dir: Path) -> dict[str, str]:
    props: dict[str, str] = {}
    props_file = instance_dir / "server.properties"
    if not props_file.exists():
        return props
    try:
        for line in props_file.read_text("utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, val = line.split("=", 1)
                props[key.strip()] = val.strip()
    except (OSError, UnicodeDecodeError) as exc:
        log.debug("Could not read server.properties for readiness check: %s", exc)
    return props


def make_minecraft_readiness_check(instance_dir: Path) -> Callable[[], Awaitable[bool]]:
    """Return an async readiness probe for a Minecraft server instance.

    Tries RCON first (if enabled and configured), then falls back to
    scanning ``logs/latest.log`` for the standard startup-done line.
    """
    props = _read_server_properties(instance_dir)
    rcon_enabled = props.get("enable-rcon", "false").lower() == "true"
    rcon_port = int(props.get("rcon.port", "25575"))
    rcon_password = props.get("rcon.password", "")
    log_path = instance_dir / "logs" / "latest.log"

    async def _check() -> bool:
        # Primary: RCON readiness (server accepting commands)
        if rcon_enabled and rcon_password:
            try:

                def _try_rcon():
                    conn = MCRcon("localhost", rcon_password, port=rcon_port)
                    conn.connect()
                    conn.command("list")
                    conn.disconnect()
                    return True

                return await asyncio.wait_for(asyncio.to_thread(_try_rcon), timeout=3.0)
            except (MCRconException, OSError, TimeoutError):  # fall back to log-scan
                pass

        # Fallback: log file parsing for "Done (x.xxs)!"
        if log_path.exists():
            try:
                text = await asyncio.to_thread(log_path.read_text, "utf-8", "replace")
                if "Done (" in text and "! For help, type" in text:
                    return True
            except (OSError, UnicodeDecodeError):  # fall back to "not ready"
                pass

        return False

    return _check
