from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TriggerType(str, Enum):
    """Event types that can be triggered for testing."""

    FOLLOW = "follow"
    LIKE = "like"
    JOIN = "join"
    SHARE = "share"
    COMMENT = "comment"
    GIFT = "gift"
    CUSTOM = "custom"

    @classmethod
    def builtin_types(cls) -> list[str]:
        return [t.value for t in cls if t != cls.CUSTOM]

    @classmethod
    def is_valid(cls, name: str) -> bool:
        return name.lower() in cls.builtin_types() or name.lower() == cls.CUSTOM.value


class ExecutionStatus(str, Enum):
    """Outcome of a trigger execution."""

    SUCCESS = "success"
    ERROR = "error"
    VALIDATION_ERROR = "validation_error"
    TIMEOUT = "timeout"
    CONNECTION_ERROR = "connection_error"
    NOT_FOUND = "not_found"
    CANCELLED = "cancelled"


@dataclass
class ValidationError:
    """A single validation problem found in trigger input."""

    field: str
    message: str
    code: str = ""
    suggested_value: str = ""

    def to_dict(self) -> dict[str, str]:
        d = {"field": self.field, "message": self.message}
        if self.code:
            d["code"] = self.code
        if self.suggested_value:
            d["suggested_value"] = self.suggested_value
        return d


@dataclass
class TriggerResult:
    """Structured result from a single trigger execution."""

    success: bool
    trigger_name: str
    status: ExecutionStatus
    execution_time_ms: float
    payload: dict[str, Any]
    warnings: list[str] = field(default_factory=list)
    validation_errors: list[ValidationError] = field(default_factory=list)
    error_code: str = ""
    error_message: str = ""
    exception_detail: str = ""
    suggested_fix: str = ""
    bridge_response: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "trigger_name": self.trigger_name,
            "status": self.status.value,
            "execution_time_ms": self.execution_time_ms,
            "payload": self.payload,
            "warnings": self.warnings,
            "validation_errors": [e.to_dict() for e in self.validation_errors],
            "error_code": self.error_code,
            "error_message": self.error_message,
            "exception_detail": self.exception_detail,
            "suggested_fix": self.suggested_fix,
            "bridge_response": self.bridge_response,
        }

    @classmethod
    def validation_failure(
        cls,
        trigger_name: str,
        errors: list[ValidationError],
        payload: dict[str, Any] | None = None,
    ) -> TriggerResult:
        return cls(
            success=False,
            trigger_name=trigger_name,
            status=ExecutionStatus.VALIDATION_ERROR,
            execution_time_ms=0.0,
            payload=payload or {},
            validation_errors=errors,
            error_code="TRIGGER_VALIDATION_ERROR",
            error_message="; ".join(e.message for e in errors),
            suggested_fix="Correct the highlighted input fields and retry.",
        )

    @classmethod
    def from_bridge_response(
        cls,
        trigger_name: str,
        payload: dict[str, Any],
        bridge_data: dict[str, Any] | None,
        start_time: float,
        warnings: list[str] | None = None,
    ) -> TriggerResult:
        elapsed = (time.time() - start_time) * 1000
        if bridge_data is None:
            return cls(
                success=False,
                trigger_name=trigger_name,
                status=ExecutionStatus.ERROR,
                execution_time_ms=elapsed,
                payload=payload,
                error_code="TRIGGER_BRIDGE_NO_RESPONSE",
                error_message="Bridge returned no response.",
                suggested_fix="Check that the bridge (main.py) is running and reachable.",
            )
        status_str = bridge_data.get("status", "error")
        ok = status_str in ("ok", "success")
        message = bridge_data.get("message", "")
        warn_list = warnings or []
        err_code = ""
        if not ok:
            if "does not exist" in message or "not valid" in message:
                err_code = "TRIGGER_NOT_FOUND"
            elif "queue is full" in message:
                err_code = "TRIGGER_QUEUE_FULL"
            elif "not ready" in message:
                err_code = "TRIGGER_BRIDGE_NOT_READY"
            else:
                err_code = "TRIGGER_BRIDGE_ERROR"
        return cls(
            success=ok,
            trigger_name=trigger_name,
            status=ExecutionStatus.SUCCESS if ok else ExecutionStatus.ERROR,
            execution_time_ms=elapsed,
            payload=payload,
            warnings=warn_list,
            error_code=err_code,
            error_message=message,
            bridge_response=bridge_data,
        )

    @classmethod
    def connection_error(
        cls,
        trigger_name: str,
        payload: dict[str, Any],
        error_detail: str,
        start_time: float,
        warnings: list[str] | None = None,
    ) -> TriggerResult:
        elapsed = (time.time() - start_time) * 1000
        return cls(
            success=False,
            trigger_name=trigger_name,
            status=ExecutionStatus.CONNECTION_ERROR,
            execution_time_ms=elapsed,
            payload=payload,
            warnings=warnings or [],
            error_code="TRIGGER_CONNECTION_ERROR",
            error_message="Cannot reach the bridge service.",
            exception_detail=error_detail,
            suggested_fix="Ensure the bot is running (main.py) and the webhook port is accessible.",
        )

    @classmethod
    def exception_result(
        cls,
        trigger_name: str,
        payload: dict[str, Any],
        exception: Exception,
        start_time: float,
    ) -> TriggerResult:
        elapsed = (time.time() - start_time) * 1000
        return cls(
            success=False,
            trigger_name=trigger_name,
            status=ExecutionStatus.ERROR,
            execution_time_ms=elapsed,
            payload=payload,
            error_code="TRIGGER_EXCEPTION",
            error_message=str(exception),
            exception_detail=f"{type(exception).__name__}: {exception}",
            suggested_fix="Check the logs for detailed error information.",
        )


@dataclass
class TriggerDefinition:
    """Metadata for a registered trigger type."""

    name: str
    display_name: str
    description: str
    requires_gift_selection: bool = False
    supports_comment_text: bool = False
    supports_moderator_flag: bool = False
    supports_superfan_flag: bool = False
    supports_fanclub_flag: bool = False


@dataclass
class EngineConfig:
    """Configuration for the TriggerEngine."""

    bridge_host: str = "127.0.0.1"
    bridge_port: int = 29188
    bridge_timeout: float = 5.0
    trigger_endpoint: str = "/custom_trigger"
    comment_endpoint: str = "/test_comment"
    log_payloads: bool = True
