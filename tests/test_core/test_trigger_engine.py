"""Tests for the shared TriggerEngine."""

from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch

import pytest

from core.trigger_engine import (
    EngineConfig,
    PayloadValidator,
    TriggerEngine,
)
from core.trigger_engine.dispatcher import BridgeDispatcher
from core.trigger_engine.models import (
    ExecutionStatus,
    TriggerResult,
    TriggerType,
    ValidationError,
)


class TestTriggerType:
    def test_builtin_types_include_standard_events(self):
        types = TriggerType.builtin_types()
        assert "follow" in types
        assert "like" in types
        assert "join" in types
        assert "share" in types
        assert "comment" in types
        assert "gift" in types

    def test_custom_is_not_builtin(self):
        assert "custom" not in TriggerType.builtin_types()

    def test_is_valid_recognises_builtins(self):
        assert TriggerType.is_valid("follow")
        assert TriggerType.is_valid("comment")
        assert TriggerType.is_valid("gift")

    def test_is_valid_also_accepts_custom(self):
        assert TriggerType.is_valid("custom")


class TestPayloadValidator:
    def setup_method(self):
        self.v = PayloadValidator()

    def test_empty_trigger_rejected(self):
        errors = self.v.validate_trigger("")
        assert len(errors) == 1
        assert errors[0].code == "TRIGGER_EMPTY"

    def test_whitespace_trigger_rejected(self):
        errors = self.v.validate_trigger("   ")
        assert len(errors) == 1
        assert errors[0].code == "TRIGGER_EMPTY"

    def test_valid_trigger_passes(self):
        errors = self.v.validate_trigger("follow")
        assert errors == []

    def test_numeric_trigger_passes(self):
        errors = self.v.validate_trigger("5655")
        assert errors == []

    def test_long_trigger_rejected(self):
        long_name = "x" * 200
        errors = self.v.validate_trigger(long_name)
        assert any(e.code == "TRIGGER_NAME_TOO_LONG" for e in errors)

    def test_empty_gift_id_rejected(self):
        errors = self.v.validate_trigger("gift", gift_id="")
        assert any(e.code == "GIFT_ID_EMPTY" for e in errors)

    def test_non_numeric_gift_id_rejected(self):
        errors = self.v.validate_trigger("gift", gift_id="abc")
        assert any(e.code == "GIFT_ID_NOT_NUMERIC" for e in errors)

    def test_negative_gift_id_rejected(self):
        errors = self.v.validate_trigger("gift", gift_id="-5")
        assert any(e.code == "GIFT_ID_INVALID" for e in errors)

    def test_valid_gift_id_passes(self):
        errors = self.v.validate_trigger("gift", gift_id="5655")
        assert errors == []

    def test_empty_comment_text_rejected(self):
        errors = self.v.validate_comment("TestUser", "")
        assert any(e.code == "COMMENT_EMPTY" for e in errors)

    def test_empty_comment_user_rejected(self):
        errors = self.v.validate_comment("", "hello")
        assert any(e.code == "USER_EMPTY" for e in errors)

    def test_valid_comment_passes(self):
        errors = self.v.validate_comment("TestUser", "Hello World")
        assert errors == []

    def test_long_user_rejected(self):
        long_user = "u" * 100
        errors = self.v.validate_comment(long_user, "hello")
        assert any(e.code == "USER_TOO_LONG" for e in errors)

    def test_long_comment_rejected(self):
        long_text = "x" * 600
        errors = self.v.validate_comment("TestUser", long_text)
        assert any(e.code == "COMMENT_TOO_LONG" for e in errors)


class TestTriggerResult:
    def test_validation_failure_result(self):
        errors = [ValidationError(field="trigger", message="Empty trigger", code="TRIGGER_EMPTY")]
        result = TriggerResult.validation_failure("test", errors)
        assert result.success is False
        assert result.status == ExecutionStatus.VALIDATION_ERROR
        assert len(result.validation_errors) == 1
        assert result.error_code == "TRIGGER_VALIDATION_ERROR"

    def test_connection_error_result(self):
        result = TriggerResult.connection_error(
            "follow", {"trigger": "follow"}, "Connection refused", time.time()
        )
        assert result.success is False
        assert result.status == ExecutionStatus.CONNECTION_ERROR
        assert result.error_code == "TRIGGER_CONNECTION_ERROR"

    def test_exception_result(self):
        exc = RuntimeError("Unexpected error")
        result = TriggerResult.exception_result(
            "follow", {"trigger": "follow"}, exc, time.time()
        )
        assert result.success is False
        assert result.status == ExecutionStatus.ERROR
        assert "RuntimeError" in result.exception_detail
        assert result.error_code == "TRIGGER_EXCEPTION"

    def test_successful_from_bridge_response(self):
        start = time.time()
        result = TriggerResult.from_bridge_response(
            "follow",
            {"trigger": "follow", "user": "TestUser"},
            {"status": "ok", "trigger": "follow", "user": "TestUser"},
            start,
        )
        assert result.success is True
        assert result.status == ExecutionStatus.SUCCESS
        assert result.bridge_response is not None

    def test_error_from_bridge_response(self):
        start = time.time()
        result = TriggerResult.from_bridge_response(
            "unknown",
            {"trigger": "unknown", "user": "TestUser"},
            {"status": "error", "message": "Trigger 'unknown' does not exist"},
            start,
        )
        assert result.success is False
        assert result.error_code == "TRIGGER_NOT_FOUND"

    def test_none_bridge_response(self):
        start = time.time()
        result = TriggerResult.from_bridge_response(
            "follow", {"trigger": "follow"}, None, start
        )
        assert result.success is False
        assert result.error_code == "TRIGGER_BRIDGE_NO_RESPONSE"

    def test_to_dict_serialization(self):
        errors = [ValidationError(field="trigger", message="Empty", code="TRIGGER_EMPTY")]
        result = TriggerResult.validation_failure("test", errors)
        d = result.to_dict()
        assert d["success"] is False
        assert d["status"] == "validation_error"
        assert len(d["validation_errors"]) == 1
        assert d["validation_errors"][0]["field"] == "trigger"


class TestTriggerEngine:
    def setup_method(self):
        # Use config that won't hit real network
        self.config = EngineConfig(bridge_host="127.0.0.1", bridge_port=9999, bridge_timeout=0.1)
        self.engine = TriggerEngine(config=self.config)

    def test_get_event_types(self):
        types = self.engine.get_event_types()
        assert isinstance(types, list)
        assert "follow" in types
        assert "comment" in types
        assert "gift" in types
        assert "tiktok" not in types

    def test_get_trigger_definitions(self):
        defs = self.engine.get_trigger_definitions()
        assert len(defs) >= 6
        follow_def = next(d for d in defs if d.name == "follow")
        assert follow_def.display_name == "Follow"
        gift_def = next(d for d in defs if d.name == "gift")
        assert gift_def.requires_gift_selection is True

    def test_is_valid_trigger(self):
        assert self.engine.is_valid_trigger("follow") is True
        assert self.engine.is_valid_trigger("gift") is True

    def test_validate_trigger_valid(self):
        errors = self.engine.validate_trigger("follow", user="TestUser")
        assert errors == []

    def test_validate_trigger_empty(self):
        errors = self.engine.validate_trigger("", user="TestUser")
        assert len(errors) >= 1

    def test_validate_comment_valid(self):
        errors = self.engine.validate_comment("TestUser", "Hello World")
        assert errors == []

    def test_validate_comment_empty_text(self):
        errors = self.engine.validate_comment("TestUser", "")
        assert len(errors) >= 1

    def test_execute_trigger_validation_failure(self):
        result = self.engine.execute_trigger("")
        assert result.success is False
        assert result.status == ExecutionStatus.VALIDATION_ERROR

    def test_execute_trigger_connection_error(self):
        result = self.engine.execute_trigger("follow", user="TestUser")
        assert result.success is False
        assert result.status == ExecutionStatus.CONNECTION_ERROR

    def test_execute_trigger_with_gift_id_valid_fails_connection(self):
        result = self.engine.execute_trigger("gift", user="TestUser", gift_id="5655")
        # Validation passes, but connection fails
        assert result.success is False
        assert result.status == ExecutionStatus.CONNECTION_ERROR

    def test_execute_trigger_with_invalid_gift_id(self):
        result = self.engine.execute_trigger("gift", user="TestUser", gift_id="abc")
        assert result.success is False
        assert result.status == ExecutionStatus.VALIDATION_ERROR

    def test_execute_comment_validation_failure(self):
        result = self.engine.execute_comment("", "")
        assert result.success is False
        assert result.status == ExecutionStatus.VALIDATION_ERROR

    def test_execute_comment_connection_error(self):
        result = self.engine.execute_comment("TestUser", "Hello")
        assert result.success is False
        assert result.status == ExecutionStatus.CONNECTION_ERROR

    def test_check_bridge_health_when_down(self):
        assert self.engine.check_bridge_health() is False

    def test_execution_time_is_measured(self):
        result = self.engine.execute_trigger("follow")
        assert result.execution_time_ms >= 0

    def test_trigger_payload_contains_user(self):
        result = self.engine.execute_trigger("follow", user="Alice")
        # Even on connection error, payload should be present
        assert result.payload.get("user") == "Alice"

    def test_trigger_payload_gift_id_as_trigger(self):
        result = self.engine.execute_trigger("gift", user="Alice", gift_id="5655")
        assert result.payload.get("trigger") == "5655"

    def test_comment_payload_structure(self):
        result = self.engine.execute_comment("Alice", "hello", moderator=True, superfan=True)
        assert result.payload.get("user") == "Alice"
        assert result.payload.get("text") == "hello"
        assert result.payload.get("moderator") is True
        assert result.payload.get("superfan") is True
        assert result.payload.get("fanclub") is False

    def test_warnings_included_in_result(self):
        result = self.engine.execute_trigger("follow")
        assert isinstance(result.warnings, list)

    def test_suggested_fix_on_failure(self):
        result = self.engine.execute_trigger("")
        assert result.suggested_fix  # Should provide actionable guidance


class TestTriggerEngineWithMockDispatcher:
    """Tests that verify engine behaviour with a mocked dispatcher."""

    def setup_method(self):
        self.mock_dispatcher = MagicMock(spec=BridgeDispatcher)
        self.engine = TriggerEngine(dispatcher=self.mock_dispatcher)

    def test_successful_dispatch(self):
        self.mock_dispatcher.dispatch_trigger.return_value = {
            "status": "ok",
            "trigger": "follow",
            "user": "TestUser",
        }
        result = self.engine.execute_trigger("follow", user="TestUser")
        assert result.success is True
        assert result.status == ExecutionStatus.SUCCESS
        self.mock_dispatcher.dispatch_trigger.assert_called_once()

    def test_failed_dispatch(self):
        self.mock_dispatcher.dispatch_trigger.return_value = {
            "status": "error",
            "message": "Trigger 'bad' does not exist",
        }
        result = self.engine.execute_trigger("bad")
        assert result.success is False
        assert result.error_code == "TRIGGER_NOT_FOUND"

    def test_dispatcher_raises_connection_error(self):
        self.mock_dispatcher.dispatch_trigger.side_effect = ConnectionError("Connection refused")
        result = self.engine.execute_trigger("follow")
        assert result.success is False
        assert result.status == ExecutionStatus.CONNECTION_ERROR

    def test_dispatcher_raises_unexpected_exception(self):
        self.mock_dispatcher.dispatch_trigger.side_effect = RuntimeError("Unexpected")
        result = self.engine.execute_trigger("follow")
        assert result.success is False
        assert result.status == ExecutionStatus.ERROR
        assert result.error_code == "TRIGGER_EXCEPTION"

    def test_comment_successful_dispatch(self):
        self.mock_dispatcher.dispatch_comment.return_value = {"status": "ok"}
        result = self.engine.execute_comment("TestUser", "hello")
        assert result.success is True
        self.mock_dispatcher.dispatch_comment.assert_called_once()

    def test_comment_dispatch_error(self):
        self.mock_dispatcher.dispatch_comment.side_effect = ConnectionError("refused")
        result = self.engine.execute_comment("TestUser", "hello")
        assert result.success is False
        assert result.status == ExecutionStatus.CONNECTION_ERROR


class TestBridgeDispatcher:
    """Tests for BridgeDispatcher HTTP logic."""

    def test_post_success(self):
        dispatcher = BridgeDispatcher(EngineConfig(bridge_host="localhost", bridge_port=12345, bridge_timeout=0.1))
        with patch("core.trigger_engine.dispatcher.urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps({"status": "ok"}).encode()
            mock_resp.__enter__.return_value = mock_resp
            mock_urlopen.return_value = mock_resp

            result = dispatcher.dispatch_trigger({"trigger": "follow"})
            assert result is not None
            assert result["status"] == "ok"

    def test_http_error_returns_detail(self):
        dispatcher = BridgeDispatcher(EngineConfig(bridge_host="localhost", bridge_port=12345, bridge_timeout=0.1))
        with patch("core.trigger_engine.dispatcher.urllib.request.urlopen") as mock_urlopen:
            from urllib.error import HTTPError

            mock_urlopen.side_effect = HTTPError(
                url="http://localhost:12345/custom_trigger",
                code=400,
                msg="Bad Request",
                hdrs={},
                fp=None,
            )

            result = dispatcher.dispatch_trigger({"trigger": "unknown"})
            assert result is not None
            assert result["status"] == "error"

    def test_connection_error_raised(self):
        dispatcher = BridgeDispatcher(EngineConfig(bridge_host="localhost", bridge_port=12345, bridge_timeout=0.1))
        with patch("core.trigger_engine.dispatcher.urllib.request.urlopen") as mock_urlopen:
            from urllib.error import URLError

            mock_urlopen.side_effect = URLError(reason="Connection refused")

            with pytest.raises(ConnectionError):
                dispatcher.dispatch_trigger({"trigger": "follow"})

    def test_check_connectivity(self):
        dispatcher = BridgeDispatcher(EngineConfig(bridge_host="localhost", bridge_port=12345, bridge_timeout=0.1))
        with patch("core.trigger_engine.dispatcher.urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.__enter__.return_value = mock_resp
            mock_urlopen.return_value = mock_resp

            assert dispatcher.check_connectivity() is True

    def test_check_connectivity_failure(self):
        dispatcher = BridgeDispatcher(EngineConfig(bridge_host="localhost", bridge_port=12345, bridge_timeout=0.1))
        with patch("core.trigger_engine.dispatcher.urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = Exception("fail")
            assert dispatcher.check_connectivity() is False


class TestTriggerResultSerialization:
    def test_round_trip_to_dict(self):
        errors = [ValidationError(field="test", message="err", code="ERR")]
        result = TriggerResult(
            success=True,
            trigger_name="follow",
            status=ExecutionStatus.SUCCESS,
            execution_time_ms=12.5,
            payload={"trigger": "follow"},
            warnings=["something"],
            validation_errors=errors,
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["trigger_name"] == "follow"
        assert d["status"] == "success"
        assert d["execution_time_ms"] == 12.5
        assert d["warnings"] == ["something"]
        assert len(d["validation_errors"]) == 1
        assert d["validation_errors"][0]["field"] == "test"

    def test_cli_json_output_roundtrip(self):
        result = TriggerResult(
            success=False,
            trigger_name="bad",
            status=ExecutionStatus.VALIDATION_ERROR,
            execution_time_ms=0.0,
            payload={},
            validation_errors=[ValidationError(field="trigger", message="bad", code="ERR")],
            error_code="TRIGGER_VALIDATION_ERROR",
            error_message="bad trigger",
        )
        d = result.to_dict()
        serialized = json.dumps(d)
        loaded = json.loads(serialized)
        assert loaded["success"] is False
        assert loaded["status"] == "validation_error"
        assert loaded["error_code"] == "TRIGGER_VALIDATION_ERROR"
