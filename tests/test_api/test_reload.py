"""Tests for the runtime reload endpoint."""

import json

from core.api.routes import reload as reload_mod


class TestReloadEndpoint:
    def test_reload_default_writes_signals(self, client):
        resp = client.post("/api/v1/reload", json={})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "reload_requested"
        assert "reload_config" in body["signals"]
        assert "reload_actions" in body["signals"]

        runtime = reload_mod._RUNTIME_DIR
        assert (runtime / "reload_config").exists()
        assert (runtime / "reload_config").read_text(encoding="utf-8") == "reload"
        assert (runtime / "reload_actions").exists()
        payload = json.loads((runtime / "reload_actions").read_text(encoding="utf-8"))
        assert payload["send_minecraft_reload"] is False

        # Clean up so the files do not affect other tests.
        (runtime / "reload_config").unlink(missing_ok=True)
        (runtime / "reload_actions").unlink(missing_ok=True)

    def test_reload_config_only(self, client):
        resp = client.post("/api/v1/reload", json={"config": True, "actions": False})
        assert resp.status_code == 200
        assert resp.json()["signals"] == ["reload_config"]

        runtime = reload_mod._RUNTIME_DIR
        assert (runtime / "reload_config").exists()
        assert not (runtime / "reload_actions").exists()

        (runtime / "reload_config").unlink(missing_ok=True)

    def test_reload_actions_only(self, client):
        resp = client.post("/api/v1/reload", json={"config": False, "actions": True})
        assert resp.status_code == 200
        assert resp.json()["signals"] == ["reload_actions"]

        runtime = reload_mod._RUNTIME_DIR
        assert (runtime / "reload_actions").exists()
        assert not (runtime / "reload_config").exists()
        payload = json.loads((runtime / "reload_actions").read_text(encoding="utf-8"))
        assert payload["send_minecraft_reload"] is False

        (runtime / "reload_actions").unlink(missing_ok=True)

    def test_reload_actions_with_minecraft_reload(self, client):
        resp = client.post(
            "/api/v1/reload",
            json={"config": False, "actions": True, "send_minecraft_reload": True},
        )
        assert resp.status_code == 200

        runtime = reload_mod._RUNTIME_DIR
        payload = json.loads((runtime / "reload_actions").read_text(encoding="utf-8"))
        assert payload["send_minecraft_reload"] is True

        (runtime / "reload_actions").unlink(missing_ok=True)

    def test_reload_no_targets_bad_request(self, client):
        resp = client.post("/api/v1/reload", json={"config": False, "actions": False})
        assert resp.status_code == 400

    def test_reload_config_refreshes_outbound_channels(self, client, monkeypatch):
        """A config reload also re-reads outbound channel configuration."""
        calls = []

        class _FakeDispatcher:
            def refresh_channels(self):
                calls.append(True)

        monkeypatch.setattr(
            reload_mod,
            "get_outbound_dispatcher",
            lambda: _FakeDispatcher(),
        )

        resp = client.post("/api/v1/reload", json={"config": True, "actions": False})
        assert resp.status_code == 200
        assert calls == [True]

        runtime = reload_mod._RUNTIME_DIR
        (runtime / "reload_config").unlink(missing_ok=True)
