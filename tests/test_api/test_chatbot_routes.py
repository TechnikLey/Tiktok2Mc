"""Tests for the chatbot config/session/status API routes."""

import json

from core.tiktok_chatbot import ChatbotConfig, ChatbotReply

VALID_SID = "abcd1234efgh5678ijkl"


class TestChatbotSessionEndpoints:
    def test_get_session_empty_when_not_configured(self, client, project_dir):
        resp = client.get("/api/v1/chatbot/session")
        assert resp.status_code == 200
        body = resp.json()
        assert body["configured"] is False
        assert body["masked_session_id"] is None
        assert body["tt_target_idc"] == ""

    def test_put_session_stores_encrypted_and_masks(self, client, project_dir):
        from core.chatbot_session import load_chatbot_session

        resp = client.put(
            "/api/v1/chatbot/session",
            json={"session_id": VALID_SID, "tt_target_idc": "va"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["configured"] is True
        assert body["masked_session_id"] == "abcd…ijkl"
        assert body["tt_target_idc"] == "va"

        # Raw secret never appears in the stored file.
        store = project_dir / "data" / "chatbot_session.json"
        record = json.loads(store.read_text(encoding="utf-8"))
        assert VALID_SID not in json.dumps(record)

        # But it decrypts correctly for the bridge.
        assert load_chatbot_session() == (VALID_SID, "va")

    def test_put_session_writes_reload_signal(self, client, project_dir):
        signal = project_dir / "core" / "runtime" / "reload_chatbot"
        resp = client.put("/api/v1/chatbot/session", json={"session_id": VALID_SID})
        assert resp.status_code == 200
        assert signal.exists()

    def test_put_session_rejects_invalid_input(self, client):
        resp = client.put(
            "/api/v1/chatbot/session", json={"session_id": "bad sid with spaces!"}
        )
        assert resp.status_code == 422

    def test_delete_session_removes_credentials(self, client):
        client.put("/api/v1/chatbot/session", json={"session_id": VALID_SID})
        resp = client.delete("/api/v1/chatbot/session")
        assert resp.status_code == 200
        body = resp.json()
        assert body["configured"] is False
        assert client.get("/api/v1/chatbot/session").json()["configured"] is False


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
            enabled=True,
            replies=[ChatbotReply(on="keyword", match="discord", message="hi")],
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
