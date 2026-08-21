"""Tests for the chatbot config/status API routes."""

from core.tiktok_chatbot import ChatbotConfig


class TestChatbotConfigEndpoints:
    def test_get_config_empty_when_no_file(self, client, project_dir):
        resp = client.get("/api/v1/chatbot/config")
        assert resp.status_code == 200
        body = resp.json()
        assert body["chatbot"] == {}
        assert "path" in body

    def test_put_config_persists_and_returns_payload(self, client, project_dir):
        from core.yaml_utils import load_yaml

        payload = {"chatbot": ChatbotConfig(enabled=True).to_dict()}
        resp = client.put("/api/v1/chatbot/config", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["chatbot"]["enabled"] is True
        assert body["reloaded"] is True

        # File on disk matches.
        cfg = load_yaml(project_dir / "config" / "chatbot.yaml")
        assert cfg["enabled"] is True

    def test_put_config_writes_reload_signal(self, client, project_dir):
        signal = project_dir / "core" / "runtime" / "reload_chatbot"
        assert not signal.exists()
        resp = client.put(
            "/api/v1/chatbot/config", json={"chatbot": {"enabled": False}}
        )
        assert resp.status_code == 200
        assert signal.exists()

    def test_get_config_roundtrip(self, client, project_dir):
        original = ChatbotConfig(
            enabled=True, keyword_replies={"discord": "hi"}
        ).to_dict()
        client.put("/api/v1/chatbot/config", json={"chatbot": original})
        resp = client.get("/api/v1/chatbot/config")
        assert resp.status_code == 200
        assert resp.json()["chatbot"] == original


class TestChatbotStatusEndpoint:
    def test_status_is_none_without_bridge(self, client):
        resp = client.get("/api/v1/chatbot/status")
        assert resp.status_code == 200
        assert resp.json()["status"] is None

    def test_status_reflects_injected_event(self, client):
        from core.api.chatbot_status import get_chatbot_status_tracker

        tracker = get_chatbot_status_tracker()
        tracker.record({"enabled": True, "sent_count": 5})

        resp = client.get("/api/v1/chatbot/status")
        assert resp.status_code == 200
        status = resp.json()["status"]
        assert status is not None
        assert status["enabled"] is True
        assert status["sent_count"] == 5

        # Cleanup so other tests start fresh.
        tracker._status = None
        tracker._last_update = 0.0
