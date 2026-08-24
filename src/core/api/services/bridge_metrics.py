"""Bridge metrics service — fetches live metrics from the TikTok bridge."""

import asyncio
import json
import logging
import time
import urllib.request
from typing import Any

from core.api.services.bridge_port import bridge_base_url

log = logging.getLogger(__name__)


class BridgeMetricsService:
    """Fetches metrics from the bridge's /metrics endpoint."""

    def __init__(self) -> None:
        self._cache: dict[str, Any] = {}
        self._cache_time: float = 0.0
        self._cache_ttl: float = 5.0  # seconds

    def _get_bridge_url(self) -> str:
        """Get the bridge metrics URL."""
        return f"{bridge_base_url()}/metrics"

    def _fetch(self, url: str) -> dict[str, Any]:
        """Blocking HTTP GET of the bridge metrics endpoint (runs in a thread)."""
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            return json.loads(resp.read().decode("utf-8"))

    async def get_metrics(self, use_cache: bool = True) -> dict[str, Any]:
        """Fetch metrics from the bridge."""
        now = time.time()

        if use_cache and self._cache and (now - self._cache_time) < self._cache_ttl:
            return self._cache

        url = self._get_bridge_url()
        try:
            # The blocking urlopen must not run on the event loop — a slow
            # or dead bridge would stall every concurrent request for up
            # to the full 3 s timeout.
            data = await asyncio.to_thread(self._fetch, url)
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
