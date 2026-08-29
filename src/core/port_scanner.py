"""Port conflict detection and auto-resolution on startup.

Scans all configured ports before any component binds them.
If a port is already in use, the scanner can either resolve
to the next available port or halt startup with a clear error.
"""

from __future__ import annotations

import json
import logging
import os
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ruamel.yaml.error import YAMLError

log = logging.getLogger(__name__)

RUNTIME_FILE = "ports_resolved.json"

# Ports the application binds (in order they should be checked)
BIND_PORTS: list[dict[str, Any]] = [
    {
        "key": "api_port",
        "config_path": "api.port",
        "default": 29185,
        "desc": "Central API server (FastAPI)",
    },
    {
        "key": "webhook_port",
        "config_path": "minecraft_server_api.web_server_port",
        "default": 29188,
        "desc": "Bot webhook (Flask)",
    },
    {
        "key": "mcserver_api_port",
        "config_path": "minecraft_server_api.api_port",
        "default": 29187,
        "desc": "MC Server API plugin",
    },
]

# Connect-only ports that don't need scanning
CONNECT_PORTS = {
    "rcon_port": 25575,
    "mc_game_port": 25565,
}


@dataclass
class PortPolicy:
    auto_resolve: bool = True
    session_only: bool = True
    max_offset: int = 10

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> PortPolicy:
        raw = cfg.get("port_policy", {})
        return cls(
            auto_resolve=raw.get("auto_resolve", True),
            session_only=raw.get("session_only", True),
            max_offset=raw.get("max_offset", 10),
        )


@dataclass
class PortCheckResult:
    port: int
    key: str
    description: str
    in_use: bool = False
    resolved_port: int | None = None


def is_port_in_use(host: str, port: int) -> bool:
    """Check if *port* is already bound on *host*."""
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except (ConnectionRefusedError, OSError, TimeoutError):
        return False


def find_available_port(host: str, preferred: int, max_offset: int) -> int:
    """Return the first available port starting at *preferred*.

    Tries ``preferred``, then ``preferred + 1``, up to
    ``preferred + max_offset``.  Pass ``-1`` for *max_offset*
    to scan indefinitely until a free port is found.

    If a finite offset is given and no port is free within the
    range, returns ``preferred + max_offset`` (last resort —
    will likely fail on bind with a clearer error).
    """
    if max_offset == -1:
        candidate = preferred
        while is_port_in_use(host, candidate):
            candidate += 1
        return candidate

    for offset in range(max_offset + 1):
        candidate = preferred + offset
        if not is_port_in_use(host, candidate):
            return candidate
    return preferred + max_offset


def _read_config_port(
    config: dict[str, Any] | None,
    config_path: str,
    default: int,
) -> int:
    """Read a port value from a dotted config path (e.g. ``api.port``)."""
    if not config or not config_path:
        return default
    parts = config_path.split(".")
    val: Any = config
    for part in parts:
        if isinstance(val, dict):
            val = val.get(part)
        else:
            return default
    if val is not None:
        try:
            return int(val)
        except (ValueError, TypeError):
            pass
    return default


def scan_bind_ports(
    host: str,
    policy: PortPolicy,
    config: dict[str, Any] | None = None,
    bind_ports: list[dict[str, Any]] | None = None,
) -> list[PortCheckResult]:
    """Check every bind port and optionally resolve conflicts.

    Returns a list of ``PortCheckResult``, one per port.
    When *auto_resolve* is true, ``resolved_port`` is set to
    the next available port if the default is taken.

    If *config* is provided, the ``config_path`` of each bind port
    entry is used to look up a user-preferred port value.
    """
    results: list[PortCheckResult] = []
    for bp in bind_ports or BIND_PORTS:
        preferred = _read_config_port(config, bp.get("config_path", ""), bp["default"])
        in_use = is_port_in_use(host, preferred)
        r = PortCheckResult(
            port=preferred,
            key=bp["key"],
            description=bp["desc"],
            in_use=in_use,
        )
        if in_use and policy.auto_resolve:
            r.resolved_port = find_available_port(host, preferred, policy.max_offset)
        results.append(r)
    return results


def build_resolved_map(
    results: list[PortCheckResult],
) -> dict[str, int]:
    """Build ``{key: resolved_port}`` from scan results."""
    return {r.key: r.resolved_port or r.port for r in results}


def write_runtime_file(
    resolved: dict[str, int],
    runtime_dir: Path,
) -> None:
    """Write resolved ports to ``core/runtime/ports_resolved.json``."""
    runtime_dir.mkdir(parents=True, exist_ok=True)
    path = runtime_dir / RUNTIME_FILE
    try:
        path.write_text(json.dumps(resolved, indent=2), encoding="utf-8")
        log.debug("Wrote resolved ports to %s", path)
    except OSError as exc:
        log.warning("Failed to write port runtime file: %s", exc)


def clear_runtime_file(runtime_dir: Path) -> None:
    """Remove the resolved ports file (session-only cleanup)."""
    path = runtime_dir / RUNTIME_FILE
    try:
        if path.exists():
            path.unlink()
    except OSError as exc:
        log.warning("Failed to clear port runtime file: %s", exc)


def get_resolved_port(
    key: str,
    default: int,
    runtime_dir: Path | None = None,
) -> int:
    """Read a resolved port from runtime file or env var, falling
    back to *default*.

    Preference order:
    1. Environment variable ``RESOLVED_PORT_<upper_key>``
    2. ``ports_resolved.json`` in *runtime_dir*
    3. *default*
    """
    env_key = f"RESOLVED_PORT_{key.upper()}"
    env_val = os.environ.get(env_key)
    if env_val is not None:
        try:
            return int(env_val)
        except (ValueError, TypeError):
            pass

    if runtime_dir is not None:
        path = runtime_dir / RUNTIME_FILE
        try:
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                val = data.get(key)
                if val is not None:
                    return int(val)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            pass

    return default


def ports_to_env(resolved: dict[str, int]) -> dict[str, str]:
    """Convert resolved port map to environment variable dict.

    Variables are prefixed with ``RESOLVED_PORT_`` and uppercased.
    """
    return {f"RESOLVED_PORT_{k.upper()}": str(v) for k, v in resolved.items()}


def persist_to_config(
    resolved: dict[str, int],
    config_path: Path,
    bind_ports: list[dict[str, Any]] | None = None,
) -> None:
    """Write resolved port values back to the user config file.

    Only updates ports that were actually changed from their defaults.
    Preserves all existing comments and formatting via ruamel.yaml.

    The write runs inside ``config_transaction`` so it cannot race a
    concurrent writer and the config version counter is bumped (the
    bridge reloads on version changes).
    """
    from core.config_lock import ConfigLockError, config_transaction
    from core.yaml_utils import load_yaml

    def apply_ports(cfg: dict[str, Any]) -> bool:
        changed = False
        for bp in bind_ports or BIND_PORTS:
            key = bp["key"]
            config_path_key = bp["config_path"]
            resolved_val = resolved.get(key)
            if resolved_val is None or resolved_val == bp["default"]:
                continue
            # Navigate dotted config path (e.g. "minecraft_server_api.web_server_port")
            parts = config_path_key.split(".")
            target = cfg
            for part in parts[:-1]:
                if part not in target or not isinstance(target.get(part), dict):
                    target.setdefault(part, {})
                target = target[part]
            if target.get(parts[-1]) != resolved_val:
                target[parts[-1]] = resolved_val
                changed = True
        return changed

    try:
        # Fast pre-check: skip the transaction (and its backup write)
        # entirely when no port actually changed.
        if not apply_ports(load_yaml(config_path)):
            return
    except (OSError, ValueError, YAMLError) as exc:
        log.warning("Cannot load config for port persistence: %s", exc)
        return

    try:
        with config_transaction(config_path, backup=True) as cfg:
            apply_ports(cfg)
        log.info("Persisted resolved ports to %s", config_path)
    except (
        ConfigLockError,
        OSError,
        ValueError,
        YAMLError,
    ) as exc:
        log.warning("Failed to persist resolved ports: %s", exc)
