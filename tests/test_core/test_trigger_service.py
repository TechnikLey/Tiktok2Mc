import json
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

from core.api.services.trigger_service import TriggerService, get_trigger_service


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
        ok, msg = svc.can_execute()
        assert ok is True

    @patch("core.api.services.trigger_service.urllib.request.urlopen")
    def test_execute_trigger_http_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"status": "ok", "trigger": "follow", "user": "TestUser"}).encode()
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        svc = TriggerService()
        svc._webhook_port = 29188
        result = svc.execute_trigger("follow", "TestUser")

        assert result["status"] == "ok"
        assert len(svc.get_history()) == 1
        assert svc.get_history()[0]["kind"] == "trigger"

    @patch("core.api.services.trigger_service.urllib.request.urlopen")
    def test_send_comment_http_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"status": "ok"}).encode()
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        svc = TriggerService()
        svc._webhook_port = 29188
        result = svc.send_comment("TestUser", "hello", moderator=True)

        assert result["status"] == "ok"
        assert len(svc.get_history()) == 1
        assert svc.get_history()[0]["kind"] == "comment"

    @patch("core.api.services.trigger_service.urllib.request.urlopen")
    def test_execute_trigger_http_error(self, mock_urlopen):
        from urllib.error import HTTPError

        mock_urlopen.side_effect = HTTPError(
            url="http://127.0.0.1:29188/custom_trigger",
            code=400,
            msg="Bad Request",
            hdrs={},
            fp=None,
        )

        svc = TriggerService()
        svc._webhook_port = 29188
        result = svc.execute_trigger("unknown", "System")

        assert result["status"] == "error"
        assert len(svc.get_history()) == 1
        assert svc.get_history()[0]["status"] == "error"

    @patch("core.api.services.trigger_service.urllib.request.urlopen")
    def test_execute_trigger_with_gift_id(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"status": "ok", "trigger": "12345", "user": "TestUser"}).encode()
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        svc = TriggerService()
        svc._webhook_port = 29188
        result = svc.execute_trigger("gift", "TestUser", gift_id="12345")

        assert result["status"] == "ok"
        assert len(svc.get_history()) == 1
        # The payload should contain the gift_id as the trigger value
        assert svc.get_history()[0]["payload"]["trigger"] == "12345"

    @patch("core.api.services.trigger_service.urllib.request.urlopen")
    def test_toggle_tiktok_connection(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(
            {"status": "ok", "message": "TikTok connection toggled. Now DISABLE_TIKTOK_CONNECT=True"}
        ).encode()
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        svc = TriggerService()
        svc._webhook_port = 29188
        result = svc.toggle_tiktok_connection()

        assert result["status"] == "ok"
        assert result["connected"] is False
        assert len(svc.get_history()) == 1
        assert svc.get_history()[0]["kind"] == "system"

    def test_dispatch_via_executable_not_found(self):
        svc = TriggerService()
        svc._executable_path = None
        with patch.object(svc, "_dispatch_via_http") as mock_http:
            mock_http.return_value = {"status": "ok"}
            result = svc._dispatch({"trigger": "follow"}, "trigger")
            mock_http.assert_called_once()
            assert result["status"] == "ok"
