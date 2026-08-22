"""Tests for the /triggers/dispatch endpoint (extension trigger access)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from core.trigger_engine import TriggerEngine
from core.trigger_engine.models import ExecutionStatus, TriggerResult


def _ok_result(name: str) -> TriggerResult:
    return TriggerResult(
        success=True,
        trigger_name=name,
        status=ExecutionStatus.SUCCESS,
        execution_time_ms=1.0,
        payload={"trigger": name, "user": "TestUser"},
    )


class TestDispatchEndpoint:
    def test_dispatch_executes_without_debounce(self, client):
        mock_engine = MagicMock(spec=TriggerEngine)
        mock_engine.execute_trigger.return_value = _ok_result("bonus_drop")
        mock_service = MagicMock()
        mock_service.dispatch.return_value = {
            "status": "success",
            "message": "",
            "trigger": "bonus_drop",
            "user": "System",
        }
        with patch(
            "core.api.routes.triggers.get_trigger_service",
            return_value=mock_service,
        ):
            for _ in range(2):
                resp = client.post(
                    "/api/v1/triggers/dispatch",
                    json={"trigger": "bonus_drop"},
                )
                assert resp.status_code == 200
                assert resp.json()["status"] == "success"

        assert mock_service.dispatch.call_count == 2
        mock_service.dispatch.assert_called_with(
            trigger="bonus_drop", user="System", gift_id=None, gift_name=None
        )

    def test_dispatch_passes_user_and_gift_fields(self, client):
        mock_service = MagicMock()
        mock_service.dispatch.return_value = {
            "status": "success",
            "message": "",
            "trigger": "gift",
            "user": "TestUser",
        }
        with patch(
            "core.api.routes.triggers.get_trigger_service",
            return_value=mock_service,
        ):
            resp = client.post(
                "/api/v1/triggers/dispatch",
                json={
                    "trigger": "gift",
                    "user": "TestUser",
                    "gift_id": "5655",
                    "gift_name": "Rose",
                },
            )

        assert resp.status_code == 200
        mock_service.dispatch.assert_called_once_with(
            trigger="gift", user="TestUser", gift_id="5655", gift_name="Rose"
        )

    def test_dispatch_reports_validation_error(self, client):
        mock_service = MagicMock()
        mock_service.dispatch.return_value = {
            "status": "error",
            "message": "Trigger name is required.",
            "trigger": "",
            "user": "System",
        }
        with patch(
            "core.api.routes.triggers.get_trigger_service",
            return_value=mock_service,
        ):
            resp = client.post("/api/v1/triggers/dispatch", json={"trigger": ""})

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "error"
        assert "required" in body["message"]

    def test_dispatch_requires_trigger_field(self, client):
        resp = client.post("/api/v1/triggers/dispatch", json={"user": "x"})
        assert resp.status_code == 422
