from __future__ import annotations

import logging
import time
from typing import Any

from core.trigger_engine.dispatcher import BridgeDispatcher
from core.trigger_engine.models import (
    EngineConfig,
    ExecutionStatus,
    TriggerDefinition,
    TriggerResult,
    TriggerType,
    ValidationError,
)
from core.trigger_engine.validator import PayloadValidator

log = logging.getLogger(__name__)


class TriggerEngine:
    """Shared trigger execution engine.

    This is the single source of truth for all trigger-related operations.
    Both the GUI (via API routes) and ``test_trigger.py`` (via direct import)
    MUST use this class.  No other code should construct payloads, dispatch
    to the bridge, or interpret bridge responses.
    """

    def __init__(
        self,
        config: EngineConfig | None = None,
        dispatcher: BridgeDispatcher | None = None,
        validator: PayloadValidator | None = None,
    ) -> None:
        self._config = config or EngineConfig()
        self._dispatcher = dispatcher or BridgeDispatcher(self._config)
        self._validator = validator or PayloadValidator()

    # ------------------------------------------------------------------
    # Registry / metadata
    # ------------------------------------------------------------------

    def get_trigger_definitions(self) -> list[TriggerDefinition]:
        """Return metadata for every supported trigger type."""
        return [
            TriggerDefinition(
                name="follow",
                display_name="Follow",
                description="Simulate a follower event.",
            ),
            TriggerDefinition(
                name="like",
                display_name="Like",
                description="Simulate a like event.",
            ),
            TriggerDefinition(
                name="join",
                display_name="Join",
                description="Simulate a viewer join event.",
            ),
            TriggerDefinition(
                name="share",
                display_name="Share",
                description="Simulate a share event.",
            ),
            TriggerDefinition(
                name="comment",
                display_name="Comment",
                description="Simulate a chat comment event.",
                supports_comment_text=True,
                supports_moderator_flag=True,
                supports_superfan_flag=True,
                supports_fanclub_flag=True,
            ),
            TriggerDefinition(
                name="gift",
                display_name="Gift",
                description="Simulate a gift event.",
                requires_gift_selection=True,
            ),
            TriggerDefinition(
                name="custom",
                display_name="Custom",
                description="Send a custom trigger name.",
            ),
        ]

    def get_event_types(self) -> list[str]:
        """Return the list of built-in event type names."""
        return TriggerType.builtin_types()

    def is_valid_trigger(self, trigger_name: str) -> bool:
        """Check whether a trigger name has a known built-in type."""
        return TriggerType.is_valid(trigger_name)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_trigger(
        self,
        trigger_name: str,
        *,
        user: str | None = None,
        gift_id: str | None = None,
        gift_name: str | None = None,
    ) -> list[ValidationError]:
        """Validate a trigger before execution.

        Returns a list of errors (empty = valid).
        """
        errors: list[ValidationError] = []
        errors.extend(self._validator.validate_trigger(trigger_name, gift_id=gift_id, gift_name=gift_name))
        errors.extend(self._validator.validate_user(user))
        return errors

    def validate_comment(
        self,
        user: str,
        text: str,
        *,
        moderator: bool = False,
        superfan: bool = False,
        fanclub: bool = False,
    ) -> list[ValidationError]:
        """Validate a comment trigger."""
        return self._validator.validate_comment(user, text, moderator=moderator, superfan=superfan, fanclub=fanclub)

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def execute_trigger(
        self,
        trigger_name: str,
        *,
        user: str = "System",
        gift_id: str | None = None,
        gift_name: str | None = None,
    ) -> TriggerResult:
        """Execute a trigger event through the bridge.

        Args:
            trigger_name: The trigger/event name (e.g. ``"follow"``, ``"5655"``).
            user: The simulated username.
            gift_id: Numeric gift ID (for gift events).
            gift_name: Gift display name (for gift events).

        Returns:
            A structured ``TriggerResult``.
        """
        # 1. Validate
        errors = self.validate_trigger(trigger_name, user=user, gift_id=gift_id, gift_name=gift_name)
        if errors:
            return TriggerResult.validation_failure(
                trigger_name=trigger_name,
                errors=errors,
                payload=self._build_payload(trigger_name, user=user, gift_id=gift_id),
            )

        payload = self._build_payload(trigger_name, user=user, gift_id=gift_id)
        start = time.time()

        log.info(
            "Trigger execution starting | name=%s user=%s gift_id=%s",
            trigger_name, user, gift_id,
        )

        try:
            bridge_data = self._dispatcher.dispatch_trigger(payload)
            result = TriggerResult.from_bridge_response(
                trigger_name=trigger_name,
                payload=payload,
                bridge_data=bridge_data,
                start_time=start,
            )
        except ConnectionError as exc:
            result = TriggerResult.connection_error(
                trigger_name=trigger_name,
                payload=payload,
                error_detail=str(exc),
                start_time=start,
            )
        except Exception as exc:
            result = TriggerResult.exception_result(
                trigger_name=trigger_name,
                payload=payload,
                exception=exc,
                start_time=start,
            )

        log.info(
            "Trigger execution finished | name=%s status=%s time_ms=%.1f errors=%d",
            trigger_name,
            result.status.value,
            result.execution_time_ms,
            len(result.validation_errors),
        )
        if not result.success:
            log.warning(
                "Trigger execution failed | name=%s code=%s message=%s",
                trigger_name, result.error_code, result.error_message,
            )

        return result

    def execute_comment(
        self,
        user: str,
        text: str,
        *,
        moderator: bool = False,
        superfan: bool = False,
        fanclub: bool = False,
    ) -> TriggerResult:
        """Execute a test comment through the bridge."""
        errors = self.validate_comment(user, text, moderator=moderator, superfan=superfan, fanclub=fanclub)
        if errors:
            return TriggerResult.validation_failure(
                trigger_name="comment",
                errors=errors,
                payload=self._build_comment_payload(user, text, moderator, superfan, fanclub),
            )

        payload = self._build_comment_payload(user, text, moderator, superfan, fanclub)
        start = time.time()

        log.info(
            "Comment execution starting | user=%s text=%s moderator=%s superfan=%s fanclub=%s",
            user, text[:50], moderator, superfan, fanclub,
        )

        try:
            bridge_data = self._dispatcher.dispatch_comment(payload)
            result = TriggerResult.from_bridge_response(
                trigger_name="comment",
                payload=payload,
                bridge_data=bridge_data,
                start_time=start,
            )
        except ConnectionError as exc:
            result = TriggerResult.connection_error(
                trigger_name="comment",
                payload=payload,
                error_detail=str(exc),
                start_time=start,
            )
        except Exception as exc:
            result = TriggerResult.exception_result(
                trigger_name="comment",
                payload=payload,
                exception=exc,
                start_time=start,
            )

        log.info(
            "Comment execution finished | status=%s time_ms=%.1f",
            result.status.value, result.execution_time_ms,
        )

        return result

    def check_bridge_health(self) -> bool:
        """Check whether the bridge web service is reachable."""
        return self._dispatcher.check_connectivity()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_payload(
        trigger_name: str,
        *,
        user: str = "System",
        gift_id: str | None = None,
    ) -> dict[str, Any]:
        trigger_value = gift_id if gift_id is not None else trigger_name
        return {"trigger": trigger_value, "user": user}

    @staticmethod
    def _build_comment_payload(
        user: str,
        text: str,
        moderator: bool,
        superfan: bool,
        fanclub: bool,
    ) -> dict[str, Any]:
        return {
            "user": user,
            "text": text,
            "moderator": moderator,
            "superfan": superfan,
            "fanclub": fanclub,
        }
