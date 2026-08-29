"""Shared bridge endpoint resolution.

Single source of truth for locating the TikTok bridge's HTTP server
(webhook/trigger/metrics endpoints).  Used by the trigger engine
dispatcher service and the bridge metrics service — they must never
disagree about the port.
"""

from __future__ import annotations

import logging
import os

from ruamel.yaml.error import YAMLError

import core.paths
from core.yaml_utils import load_yaml

log = logging.getLogger(__name__)

_BRIDGE_PORT_ENV = "RESOLVED_PORT_WEBHOOK_PORT"
_BRIDGE_DEFAULT_PORT = 29188


def resolve_bridge_port() -> int:
    """Determine the bridge webhook port from env, config, or default.

    Priority:
    1. Environment variable ``RESOLVED_PORT_WEBHOOK_PORT`` (set by port scanner)
    2. Config key ``minecraft_server_api.web_server_port``
    3. Default ``29188``
    """
    env_port = os.environ.get(_BRIDGE_PORT_ENV)
    if env_port is not None:
        try:
            return int(env_port)
        except (ValueError, TypeError):
            pass

    try:
        config_path = core.paths.get_config_file()
        if config_path.exists():
            cfg = load_yaml(config_path)
            port = cfg.get("minecraft_server_api", {}).get(
                "web_server_port", _BRIDGE_DEFAULT_PORT
            )
            return int(port)
    except (OSError, ValueError, YAMLError):  # best-effort: fall back to default port
        pass

    return _BRIDGE_DEFAULT_PORT


def bridge_base_url() -> str:
    """Base URL (``http://host:port``, no trailing slash) of the bridge."""
    try:
        config_path = core.paths.get_config_file()
        if config_path.exists():
            cfg = load_yaml(config_path)
            if cfg is not None:
                host = cfg.get("minecraft_server_api", {}).get(
                    "web_server_host", "127.0.0.1"
                )
                return f"http://{host}:{resolve_bridge_port()}"
    except (OSError, ValueError, YAMLError) as exc:
        log.debug("Failed to read bridge host from config: %s", exc)
    return f"http://127.0.0.1:{resolve_bridge_port()}"
