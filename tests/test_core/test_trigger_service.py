"""Tests for TriggerService (API-layer wrapper around TriggerEngine)."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

from core.api.services.trigger_service import TriggerService, get_trigger_service
from core.trigger_engine import TriggerEngine
from core.trigger_engine.models import ExecutionStatus, TriggerResult


class TestTriggerService:
    def test_singleton(self):
        s1 = get_trigger_service()
        s2 = get_trigger_service()
        assert s1 is s2

    def test_event_types_not_empty(self):
        svc = TriggerService()
        types = svc.get_event_types()
        assert isinstance(types, list)
        assert "follow" in types
        assert "comment" in types

    def test_tiktok_is_not_an_event_type(self):
        svc = TriggerService()
        types = svc.get_event_types()
        assert "tiktok" not in types
        assert "gift" in types

    def test_history_initially_empty(self):
        svc = TriggerService()
        assert svc.get_history() == []

    def test_debounce_blocks_rapid_calls(self):
        svc = TriggerService()
        svc._last_execution = time.time()
        ok, msg = svc.can_execute()
        assert ok is False
        assert "wait" in msg.lower()

    def test_debounce_allows_after_delay(self):
        svc = TriggerService()
        svc._last_execution = time.time() - 10
        ok, _msg = svc.can_execute()
        assert ok is True

    def test_debounce_message_on_block(self):
        svc = TriggerService()
        svc._last_execution = time.time()
        _ok, msg = svc.can_execute()
        assert "wait" in msg.lower()
        assert "s before" in msg.lower()

    def test_execute_trigger_records_history(self):
        mock_engine = MagicMock(spec=TriggerEngine)
        mock_engine.execute_trigger.return_value = TriggerResult(
            success=True,
            trigger_name="follow",
            status=ExecutionStatus.SUCCESS,
            execution_time_ms=5.0,
            payload={"trigger": "follow", "user": "TestUser"},
        )
        svc = TriggerService(engine=mock_engine)
        svc._last_execution = time.time() - 10  # bypass debounce

        result = svc.execute_trigger("follow", "TestUser")

        assert result["status"] == "success"
        assert len(svc.get_history()) == 1
        assert svc.get_history()[0]["kind"] == "follow"
        assert svc.get_history()[0]["success"] is True
        mock_engine.execute_trigger.assert_called_once_with(
            trigger_name="follow", user="TestUser", gift_id=None
        )

    def test_execute_trigger_error_result(self):
        mock_engine = MagicMock(spec=TriggerEngine)
        mock_engine.execute_trigger.return_value = TriggerResult(
            success=False,
            trigger_name="bad",
            status=ExecutionStatus.ERROR,
            execution_time_ms=5.0,
            payload={"trigger": "bad", "user": "System"},
            error_code="TRIGGER_NOT_FOUND",
            error_message="Trigger 'bad' does not exist",
        )
        svc = TriggerService(engine=mock_engine)
        svc._last_execution = time.time() - 10

        result = svc.execute_trigger("bad")

        assert result["status"] == "error"
        assert "does not exist" in result["message"]

    def test_send_comment_records_history(self):
        mock_engine = MagicMock(spec=TriggerEngine)
        mock_engine.execute_comment.return_value = TriggerResult(
            success=True,
            trigger_name="comment",
            status=ExecutionStatus.SUCCESS,
            execution_time_ms=5.0,
            payload={"user": "TestUser", "text": "hello"},
        )
        svc = TriggerService(engine=mock_engine)
        svc._last_execution = time.time() - 10

        result = svc.send_comment("TestUser", "hello", moderator=True)

        assert result["status"] == "success"
        assert len(svc.get_history()) == 1
        assert svc.get_history()[0]["kind"] == "comment"
        mock_engine.execute_comment.assert_called_once_with(
            user="TestUser", text="hello", moderator=True, superfan=False, fanclub=False
        )

    def test_execute_trigger_debounce_blocks(self):
        mock_engine = MagicMock(spec=TriggerEngine)
        svc = TriggerService(engine=mock_engine)
        svc._last_execution = time.time()  # recently executed

        result = svc.execute_trigger("follow")

        assert result["status"] == "error"
        assert "wait" in result["message"]
        mock_engine.execute_trigger.assert_not_called()

    def test_execute_trigger_with_gift_id(self):
        mock_engine = MagicMock(spec=TriggerEngine)
        mock_engine.execute_trigger.return_value = TriggerResult(
            success=True,
            trigger_name="5655",
            status=ExecutionStatus.SUCCESS,
            execution_time_ms=5.0,
            payload={"trigger": "5655", "user": "TestUser"},
        )
        svc = TriggerService(engine=mock_engine)
        svc._last_execution = time.time() - 10

        result = svc.execute_trigger("gift", "TestUser", gift_id="5655")

        assert result["status"] == "success"
        mock_engine.execute_trigger.assert_called_once_with(
            trigger_name="gift", user="TestUser", gift_id="5655"
        )

    def test_toggle_tiktok_connection(self):
        mock_engine = MagicMock(spec=TriggerEngine)
        mock_engine.execute_trigger.return_value = TriggerResult(
            success=True,
            trigger_name="tiktok",
            status=ExecutionStatus.SUCCESS,
            execution_time_ms=5.0,
            payload={"trigger": "tiktok", "user": "System"},
            error_message="TikTok connection toggled. Now DISABLE_TIKTOK_CONNECT=True",
            bridge_response={
                "status": "ok",
                "message": "TikTok connection toggled. Now DISABLE_TIKTOK_CONNECT=True",
            },
        )
        svc = TriggerService(engine=mock_engine)
        svc._last_execution = time.time() - 10

        result = svc.toggle_tiktok_connection()

        assert result["status"] == "success"
        assert result["connected"] is False
        assert len(svc.get_history()) == 1

    def test_toggle_tiktok_connection_connected_state(self):
        mock_engine = MagicMock(spec=TriggerEngine)
        mock_engine.execute_trigger.return_value = TriggerResult(
            success=True,
            trigger_name="tiktok",
            status=ExecutionStatus.SUCCESS,
            execution_time_ms=5.0,
            payload={"trigger": "tiktok", "user": "System"},
            error_message="TikTok connection toggled. Now DISABLE_TIKTOK_CONNECT=False",
        )
        svc = TriggerService(engine=mock_engine)
        svc._last_execution = time.time() - 10

        result = svc.toggle_tiktok_connection()

        assert result["status"] == "success"
        assert result["connected"] is True

    def test_get_trigger_definitions(self):
        svc = TriggerService()
        defs = svc.get_trigger_definitions()
        assert len(defs) >= 6
        names = [d["name"] for d in defs]
        assert "follow" in names
        assert "comment" in names
        assert "gift" in names

    def test_history_contains_trigger_fields(self):
        mock_engine = MagicMock(spec=TriggerEngine)
        mock_engine.execute_trigger.return_value = TriggerResult(
            success=True,
            trigger_name="follow",
            status=ExecutionStatus.SUCCESS,
            execution_time_ms=5.0,
            payload={"trigger": "follow", "user": "Alice"},
        )
        svc = TriggerService(engine=mock_engine)
        svc._last_execution = time.time() - 10
        svc.execute_trigger("follow", "Alice")
        entry = svc.get_history()[0]
        assert "timestamp" in entry
        assert "kind" in entry
        assert "payload" in entry
        assert "status" in entry
        assert "message" in entry
        assert "success" in entry

    def test_history_timestamp_is_wall_clock_not_duration(self):
        mock_engine = MagicMock(spec=TriggerEngine)
        mock_engine.execute_trigger.return_value = TriggerResult(
            success=True,
            trigger_name="follow",
            status=ExecutionStatus.SUCCESS,
            execution_time_ms=5.0,
            payload={"trigger": "follow", "user": "Alice"},
        )
        svc = TriggerService(engine=mock_engine)
        svc._last_execution = time.time() - 10
        svc.execute_trigger("follow", "Alice")
        entry = svc.get_history()[0]
        assert entry["duration_ms"] == 5.0
        assert entry["timestamp"] > 1_600_000_000
        assert abs(entry["timestamp"] - time.time()) < 10

    def test_multiple_executions_in_history(self):
        mock_engine = MagicMock(spec=TriggerEngine)

        def side_effect(trigger_name, user="System", gift_id=None, gift_name=None):
            return TriggerResult(
                success=True,
                trigger_name=trigger_name,
                status=ExecutionStatus.SUCCESS,
                execution_time_ms=5.0,
                payload={"trigger": trigger_name, "user": user},
            )

        mock_engine.execute_trigger.side_effect = side_effect
        svc = TriggerService(engine=mock_engine)
        svc._last_execution = time.time() - 10

        svc.execute_trigger("follow", "A")
        svc._last_execution = time.time() - 5
        svc.execute_trigger("follow", "B")

        assert len(svc.get_history()) == 2
        assert svc.get_history()[0]["payload"]["user"] == "B"
        assert svc.get_history()[1]["payload"]["user"] == "A"

    def test_history_is_bounded(self):
        mock_engine = MagicMock(spec=TriggerEngine)

        def side_effect(trigger_name, user="System", gift_id=None, gift_name=None):
            return TriggerResult(
                success=True,
                trigger_name=trigger_name,
                status=ExecutionStatus.SUCCESS,
                execution_time_ms=5.0,
                payload={"trigger": trigger_name, "user": user},
            )

        mock_engine.execute_trigger.side_effect = side_effect
        svc = TriggerService(engine=mock_engine)
        svc.MAX_HISTORY = 3
        for i in range(6):
            svc._last_execution = time.time() - 10
            svc.execute_trigger("follow", str(i))

        history = svc.get_history()
        assert len(history) == 3
        assert {entry["payload"]["user"] for entry in history} == {"3", "4", "5"}
