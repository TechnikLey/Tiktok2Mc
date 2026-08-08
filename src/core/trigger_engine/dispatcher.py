from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

from core.trigger_engine.models import EngineConfig

log = logging.getLogger(__name__)


class BridgeDispatcher:
    """Sends validated trigger payloads to the bridge.

    This is the only code path that communicates with the bridge's
    ``/custom_trigger`` and ``/test_comment`` endpoints.  Both the
    API routes and the CLI tool ultimately pass through here.
    """

    def __init__(self, config: EngineConfig | None = None) -> None:
        self._config = config or EngineConfig()

    def dispatch_trigger(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        """POST a trigger payload to the bridge.

        Returns the bridge's JSON response or *None* if the response
        body could not be decoded.
        """
        url = (
            f"http://{self._config.bridge_host}:{self._config.bridge_port}"
            f"{self._config.trigger_endpoint}"
        )
        return self._post(url, payload)

    def dispatch_comment(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        """POST a test comment payload to the bridge."""
        url = (
            f"http://{self._config.bridge_host}:{self._config.bridge_port}"
            f"{self._config.comment_endpoint}"
        )
        return self._post(url, payload)

    def check_connectivity(self) -> bool:
        """Check whether the bridge is reachable via its ``/health`` endpoint."""
        url = (
            f"http://{self._config.bridge_host}:{self._config.bridge_port}"
            "/health"
        )
        try:
            with urllib.request.urlopen(url, timeout=self._config.bridge_timeout) as resp:
                return resp.status == 200
        except (urllib.error.URLError, ConnectionResetError, OSError):
            return False

    def _post(self, url: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                req, timeout=self._config.bridge_timeout
            ) as resp:
                raw = resp.read().decode("utf-8")
                if not raw:
                    return None
                data: dict[str, Any] = json.loads(raw)
                data.setdefault("status", "ok")
                return data
        except urllib.error.HTTPError as exc:
            try:
                detail = json.loads(exc.read().decode("utf-8"))
                return detail
            except json.JSONDecodeError:
                return {"status": "error", "message": f"HTTP {exc.code}: {exc.reason}"}
        except urllib.error.URLError as exc:
            log.warning("Bridge unreachable at %s: %s", url, exc.reason)
            raise ConnectionError(
                f"Cannot reach bridge at {url}. "
                f"The TikTok bridge (main.py) may not be running. "
                f"Error: {exc.reason}"
            ) from exc
        except ConnectionResetError as exc:
            raise ConnectionError(
                f"Bridge at {url} refused the connection. "
                f"The bridge may be starting up or is not running."
            ) from exc
