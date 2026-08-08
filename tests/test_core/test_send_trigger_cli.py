"""Tests for the ``src/python/send_trigger.py`` CLI tool.

These tests verify that the CLI correctly parses arguments and
delegates to ``TriggerEngine``.  They mock the engine to avoid
actual network calls.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from core.trigger_engine.models import ExecutionStatus, TriggerResult


@pytest.fixture
def mock_engine():
    with patch("python.send_trigger.TriggerEngine") as mock_cls:
        instance = MagicMock()
        mock_cls.return_value = instance
        yield instance


class TestSendTriggerCLI:
    def test_minimal_trigger(self, mock_engine):
        import python.send_trigger as st

        mock_engine.execute_trigger.return_value = TriggerResult(
            success=True,
            trigger_name="follow",
            status=ExecutionStatus.SUCCESS,
            execution_time_ms=5.0,
            payload={"trigger": "follow", "user": "System"},
        )
        rc = st.main(["follow"])
        assert rc == 0
        mock_engine.execute_trigger.assert_called_once_with(
            trigger_name="follow", user="System", gift_id=None, gift_name=None
        )

    def test_trigger_with_user(self, mock_engine):
        import python.send_trigger as st

        mock_engine.execute_trigger.return_value = TriggerResult(
            success=True,
            trigger_name="follow",
            status=ExecutionStatus.SUCCESS,
            execution_time_ms=5.0,
            payload={"trigger": "follow", "user": "Alice"},
        )
        rc = st.main(["follow", "--user", "Alice"])
        assert rc == 0
        mock_engine.execute_trigger.assert_called_once_with(
            trigger_name="follow", user="Alice", gift_id=None, gift_name=None
        )

    def test_gift_with_id(self, mock_engine):
        import python.send_trigger as st

        mock_engine.execute_trigger.return_value = TriggerResult(
            success=True,
            trigger_name="5655",
            status=ExecutionStatus.SUCCESS,
            execution_time_ms=5.0,
            payload={"trigger": "5655", "user": "System"},
        )
        rc = st.main(["gift", "--gift-id", "5655", "--gift-name", "Rose"])
        assert rc == 0
        mock_engine.execute_trigger.assert_called_once_with(
            trigger_name="5655", user="System", gift_id="5655", gift_name="Rose"
        )

    def test_comment(self, mock_engine):
        import python.send_trigger as st

        mock_engine.execute_comment.return_value = TriggerResult(
            success=True,
            trigger_name="comment",
            status=ExecutionStatus.SUCCESS,
            execution_time_ms=5.0,
            payload={"user": "TestUser", "text": "hello"},
        )
        rc = st.main(["comment", "--user", "TestUser", "--text", "hello"])
        assert rc == 0
        mock_engine.execute_comment.assert_called_once_with(
            user="TestUser",
            text="hello",
            moderator=False,
            superfan=False,
            fanclub=False,
        )

    def test_comment_with_flags(self, mock_engine):
        import python.send_trigger as st

        mock_engine.execute_comment.return_value = TriggerResult(
            success=True,
            trigger_name="comment",
            status=ExecutionStatus.SUCCESS,
            execution_time_ms=5.0,
            payload={"user": "TestUser", "text": "hello"},
        )
        rc = st.main(
            [
                "comment",
                "--user",
                "TestUser",
                "--text",
                "hello",
                "--moderator",
                "--superfan",
            ]
        )
        assert rc == 0
        mock_engine.execute_comment.assert_called_once_with(
            user="TestUser", text="hello", moderator=True, superfan=True, fanclub=False
        )

    def test_trigger_failure_returns_nonzero(self, mock_engine):
        import python.send_trigger as st

        mock_engine.execute_trigger.return_value = TriggerResult(
            success=False,
            trigger_name="unknown",
            status=ExecutionStatus.ERROR,
            execution_time_ms=10.0,
            payload={"trigger": "unknown"},
            error_code="TRIGGER_NOT_FOUND",
            error_message="Trigger 'unknown' does not exist",
        )
        rc = st.main(["unknown"])
        assert rc == 1

    def test_json_output(self, mock_engine, capsys):
        import python.send_trigger as st

        mock_engine.execute_trigger.return_value = TriggerResult(
            success=True,
            trigger_name="follow",
            status=ExecutionStatus.SUCCESS,
            execution_time_ms=5.0,
            payload={"trigger": "follow", "user": "System"},
        )
        rc = st.main(["follow", "--json"])
        assert rc == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["success"] is True
        assert data["trigger_name"] == "follow"

    def test_json_output_on_failure(self, mock_engine, capsys):
        import python.send_trigger as st

        mock_engine.execute_trigger.return_value = TriggerResult(
            success=False,
            trigger_name="bad",
            status=ExecutionStatus.ERROR,
            execution_time_ms=5.0,
            payload={"trigger": "bad"},
            error_code="TRIGGER_NOT_FOUND",
        )
        rc = st.main(["bad", "--json"])
        assert rc == 1
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["success"] is False

    def test_no_arguments_returns_error(self, mock_engine):
        import python.send_trigger as st

        rc = st.main([])
        assert rc == 1

    def test_verbose_logging_enabled(self, mock_engine):
        import python.send_trigger as st

        mock_engine.execute_trigger.return_value = TriggerResult(
            success=True,
            trigger_name="follow",
            status=ExecutionStatus.SUCCESS,
            execution_time_ms=5.0,
            payload={"trigger": "follow"},
        )
        rc = st.main(["follow", "--verbose"])
        assert rc == 0

    def test_custom_host_port(self, mock_engine):
        import python.send_trigger as st

        mock_engine.execute_trigger.return_value = TriggerResult(
            success=True,
            trigger_name="follow",
            status=ExecutionStatus.SUCCESS,
            execution_time_ms=5.0,
            payload={"trigger": "follow"},
        )
        rc = st.main(["follow", "--host", "10.0.0.1", "--port", "30000"])
        assert rc == 0

    def test_list_types(self, mock_engine, capsys):
        import python.send_trigger as st
        from core.trigger_engine.models import TriggerDefinition

        mock_engine.get_trigger_definitions.return_value = [
            TriggerDefinition(
                name="follow", display_name="Follow", description="A follow event"
            ),
            TriggerDefinition(
                name="gift",
                display_name="Gift",
                description="A gift event",
                requires_gift_selection=True,
            ),
            TriggerDefinition(
                name="comment",
                display_name="Comment",
                description="A comment",
                supports_comment_text=True,
            ),
        ]
        rc = st.main(["--list"])
        assert rc == 0
        captured = capsys.readouterr()
        assert "follow" in captured.out
        assert "gift" in captured.out
        assert "comment" in captured.out
        assert "requires gift-id" in captured.out
        assert "supports comment text" in captured.out
