"""Trigger execution service for the Event Tester GUI.

This is a thin wrapper around the shared ``TriggerEngine``.
It adds session history and debounce — concerns that are specific
to the API layer, not the trigger logic itself.

Every trigger operation ultimately flows through
``core.trigger_engine.engine.TriggerEngine``, which is the single
source of truth for trigger execution, validation, and dispatch.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from ruamel.yaml.error import YAMLError

import core.paths
from core.trigger_engine import EngineConfig, TriggerEngine
from core.trigger_engine.models import TriggerResult
from core.yaml_utils import load_yaml

log = logging.getLogger(__name__)


def _resolve_bridge_port() -> int:
    """Determine the bridge webhook port from env, config, or default.

    Priority:
    1. Environment variable ``RESOLVED_PORT_WEBHOOK_PORT`` (set by port scanner)
    2. Config key ``minecraft_server_api.web_server_port``
    3. Default ``29188``
    """
    env_port = os.environ.get("RESOLVED_PORT_WEBHOOK_PORT")
    if env_port is not None:
        try:
            return int(env_port)
        except (ValueError, TypeError):
            pass

    try:
        config_path = core.paths.get_config_file()
        if config_path.exists():
            cfg = load_yaml(config_path)
            port = cfg.get("minecraft_server_api", {}).get("web_server_port", 29188)
            return int(port)
    except (OSError, ValueError, YAMLError):  # best-effort: fall back to default port
        pass

    return 29188


class TriggerService:
    """API-layer service wrapping the shared TriggerEngine.

    Responsibilities:
    - Session history management
    - Debounce / cooldown
    - Delegating all trigger logic to ``TriggerEngine``
    - Converting ``TriggerResult`` to API-friendly dicts
    """

    DEBOUNCE_SECONDS = 1.5
    MAX_HISTORY: int = 500

    def __init__(self, engine: TriggerEngine | None = None) -> None:
        if engine is None:
            bridge_port = _resolve_bridge_port()
            config = EngineConfig(bridge_port=bridge_port)
            engine = TriggerEngine(config=config)
        self._engine = engine
        self._history: list[tuple[float, TriggerResult]] = []
        self._last_execution: float = 0.0

    # ------------------------------------------------------------------
    # Public API — delegates to TriggerEngine
    # ------------------------------------------------------------------

    def get_event_types(self) -> list[str]:
        return self._engine.get_event_types()

    def get_trigger_definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "name": d.name,
                "display_name": d.display_name,
                "description": d.description,
                "requires_gift_selection": d.requires_gift_selection,
                "supports_comment_text": d.supports_comment_text,
                "supports_comment_flags": d.supports_moderator_flag,
            }
            for d in self._engine.get_trigger_definitions()
        ]

    def get_history(self) -> list[dict[str, Any]]:
        return [
            {
                "timestamp": completed_at,
                "duration_ms": r.execution_time_ms,
                "kind": r.trigger_name,
                "payload": r.payload,
                "status": r.status.value,
                "message": r.error_message,
                "success": r.success,
            }
            for completed_at, r in reversed(self._history)
        ]

    def can_execute(self) -> tuple[bool, str]:
        now = time.time()
        elapsed = now - self._last_execution
        if elapsed < self.DEBOUNCE_SECONDS:
            remaining = round(self.DEBOUNCE_SECONDS - elapsed, 1)
            return False, f"Please wait {remaining}s before triggering again."
        return True, ""

    def execute_trigger(
        self, trigger: str, user: str = "System", gift_id: str | None = None
    ) -> dict[str, Any]:
        ok, msg = self.can_execute()
        if not ok:
            return {"status": "error", "message": msg}

        self._last_execution = time.time()
        result = self._engine.execute_trigger(
            trigger_name=trigger,
            user=user,
            gift_id=gift_id,
        )
        self._record(result)
        return self._result_to_api_dict(result, trigger, user)

    def dispatch(
        self,
        trigger: str,
        user: str = "System",
        gift_id: str | None = None,
        gift_name: str | None = None,
    ) -> dict[str, Any]:
        """Execute a trigger WITHOUT debounce.

        This is the programmatic entry point for extensions (plugins, hooks,
        schedulers).  Unlike ``execute_trigger`` (GUI Event Tester), calls are
        never rate-limited by the shared GUI cooldown; every call is recorded
        in history for observability.
        """
        result = self._engine.execute_trigger(
            trigger_name=trigger,
            user=user,
            gift_id=gift_id,
            gift_name=gift_name,
        )
        self._record(result)
        return self._result_to_api_dict(result, trigger, user)

    def toggle_tiktok_connection(self) -> dict[str, Any]:
        ok, msg = self.can_execute()
        if not ok:
            return {"status": "error", "message": msg}

        self._last_execution = time.time()
        result = self._engine.execute_trigger(
            trigger_name="tiktok",
            user="System",
        )
        self._record(result)

        # Prefer the structured flag from the bridge response; fall back to
        # parsing the human-readable message for older bridge versions.
        bridge_data = result.bridge_response or {}
        connected = bridge_data.get("connected")
        if not isinstance(connected, bool):
            connected = True
            message = result.error_message
            if (
                "DISABLE_TIKTOK_CONNECT=True" in message
                or (message and "disabled" in message.lower())
                or (message and "now true" in message.lower())
            ):
                connected = False

        return {
            "status": result.status.value if result.success else "error",
            "message": result.error_message,
            "connected": connected,
        }

    def send_comment(
        self,
        user: str,
        text: str,
        moderator: bool = False,
        superfan: bool = False,
        fanclub: bool = False,
    ) -> dict[str, Any]:
        ok, msg = self.can_execute()
        if not ok:
            return {"status": "error", "message": msg}

        self._last_execution = time.time()
        result = self._engine.execute_comment(
            user=user,
            text=text,
            moderator=moderator,
            superfan=superfan,
            fanclub=fanclub,
        )
        self._record(result)
        return self._result_to_api_dict(result, "comment", user)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _record(self, result: TriggerResult) -> None:
        """Append to history with the wall-clock completion time, trimming to
        ``MAX_HISTORY`` entries."""
        self._history.append((time.time(), result))
        if len(self._history) > self.MAX_HISTORY:
            del self._history[: len(self._history) - self.MAX_HISTORY]

    @staticmethod
    def _result_to_api_dict(
        result: TriggerResult, trigger: str, user: str
    ) -> dict[str, Any]:
        return {
            "status": result.status.value if result.success else "error",
            "message": result.error_message or "",
            "trigger": trigger,
            "user": user,
        }


# Singleton
_trigger_service: TriggerService | None = None


def get_trigger_service() -> TriggerService:
    global _trigger_service
    if _trigger_service is None:
        _trigger_service = TriggerService()
    return _trigger_service
