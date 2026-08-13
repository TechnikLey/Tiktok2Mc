"""Bridge metrics service — fetches live metrics from the TikTok bridge."""

import json
import logging
import urllib.request
from typing import Any

from ruamel.yaml.error import YAMLError

import core.paths
from core.yaml_utils import load_yaml

log = logging.getLogger(__name__)


class BridgeMetricsService:
    """Fetches metrics from the bridge's /metrics endpoint."""

    def __init__(self) -> None:
        self._cache: dict[str, Any] = {}
        self._cache_time: float = 0.0
        self._cache_ttl: float = 5.0  # seconds

    def _get_bridge_url(self) -> str:
        """Get the bridge metrics URL from config."""
        try:
            config_path = core.paths.get_config_file()
            if config_path.exists():
                cfg = load_yaml(config_path)
                if cfg is not None:
                    host = cfg.get("minecraft_server_api", {}).get(
                        "web_server_host", "127.0.0.1"
                    )
                    port = cfg.get("minecraft_server_api", {}).get(
                        "web_server_port", 29188
                    )
                    return f"http://{host}:{port}/metrics"
        except (OSError, ValueError, YAMLError) as exc:
            log.debug("Failed to read bridge metrics URL from config: %s", exc)
        return "http://127.0.0.1:29188/metrics"

    async def get_metrics(self, use_cache: bool = True) -> dict[str, Any]:
        """Fetch metrics from the bridge."""
        import time

        now = time.time()

        if use_cache and self._cache and (now - self._cache_time) < self._cache_ttl:
            return self._cache

        url = self._get_bridge_url()
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                self._cache = data
                self._cache_time = now
                return data
        except (OSError, ValueError) as exc:
            log.debug("Failed to fetch bridge metrics from %s: %s", url, exc)
            return {}


# Module-level singleton
_bridge_metrics_service: BridgeMetricsService | None = None


def get_bridge_metrics_service() -> BridgeMetricsService:
    global _bridge_metrics_service
    if _bridge_metrics_service is None:
        _bridge_metrics_service = BridgeMetricsService()
    return _bridge_metrics_service
