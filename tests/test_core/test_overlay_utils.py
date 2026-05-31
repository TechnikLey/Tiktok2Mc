import json
import pytest
from pathlib import Path

from core.overlay_utils import (
    OverlayClient,
    OverlayManager,
    send_overlay_text,
)


class TestOverlayClient:
    def test_initial_state(self):
        client = OverlayClient("default", 3, 10)
        assert client.name == "default"
        assert client.max_fails == 3
        assert client.cooldown == 10

    def test_cooldown_activates_after_max_fails(self):
        client = OverlayClient("test", 2, 5)
        blocked, _ = client.get_cooldown_status()
        assert blocked is False

        client.mark_failure()
        client.mark_failure()
        blocked, remaining = client.get_cooldown_status()
        assert blocked is True
        assert remaining <= 5

    def test_success_resets_cooldown(self):
        client = OverlayClient("test", 2, 5)
        client.mark_failure()
        client.mark_failure()
        assert client.get_cooldown_status()[0] is True

        client.mark_success()
        blocked, _ = client.get_cooldown_status()
        assert blocked is False


class TestOverlayManager:
    def test_loads_config_from_global(self, tmp_path, monkeypatch):
        from core.yaml_utils import save_yaml

        config_file = tmp_path / "config.yaml"
        save_yaml(
            config_file,
            {
                "overlay": {
                    "max_fails": 5,
                    "cooldown": 15,
                    "overlays": [{"name": "alerts"}, {"name": "chat"}],
                },
            },
            backup=False,
        )
        monkeypatch.setattr(
            "core.overlay_utils.get_config_file", lambda: config_file
        )

        mgr = OverlayManager()
        assert "alerts" in mgr.clients
        assert "chat" in mgr.clients
        assert "default" in mgr.clients  # fallback
        assert mgr.clients["alerts"].max_fails == 5

    def test_loads_fallback_defaults(self, tmp_path, monkeypatch):
        from core.yaml_utils import save_yaml

        config_file = tmp_path / "config.yaml"
        save_yaml(config_file, {}, backup=False)
        monkeypatch.setattr(
            "core.overlay_utils.get_config_file", lambda: config_file
        )

        mgr = OverlayManager()
        assert "default" in mgr.clients
        assert mgr.clients["default"].max_fails == 3
        assert mgr.clients["default"].cooldown == 10

    def test_dispatch_unknown_overlay(self, tmp_path, monkeypatch):
        from core.yaml_utils import save_yaml

        config_file = tmp_path / "config.yaml"
        save_yaml(config_file, {}, backup=False)
        monkeypatch.setattr(
            "core.overlay_utils.get_config_file", lambda: config_file
        )

        mgr = OverlayManager()
        result = mgr.dispatch("Title", "Subtitle", 3, "nonexistent")
        assert result is False

    def test_dispatch_during_cooldown(self, tmp_path, monkeypatch):
        from core.yaml_utils import save_yaml

        config_file = tmp_path / "config.yaml"
        save_yaml(config_file, {}, backup=False)
        monkeypatch.setattr(
            "core.overlay_utils.get_config_file", lambda: config_file
        )

        mgr = OverlayManager()
        client = mgr.clients["default"]
        client._fail_count = client.max_fails
        client._last_fail_time = __import__("time").time()

        result = mgr.dispatch("Title", "Subtitle", 3, "default")
        assert result is False
