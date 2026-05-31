import json
import pytest
from pathlib import Path

from core.overlay_utils import (
    OverlayClient,
    OverlayManager,
    _find_overlay_plugin_dir,
    send_overlay_text,
)
from core.yaml_utils import save_yaml


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


class TestFindOverlayPluginDir:
    def test_finds_overlay_text(self, tmp_path, monkeypatch):
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        overlay_dir = plugins_dir / "overlaytxt"
        overlay_dir.mkdir()
        (overlay_dir / "plugin.json").write_text(
            json.dumps({"name": "overlay-text"}), encoding="utf-8"
        )
        monkeypatch.setattr(
            "core.overlay_utils.discover_plugins_dir", lambda: plugins_dir
        )
        result = _find_overlay_plugin_dir()
        assert result == overlay_dir

    def test_fallback_when_not_found(self, tmp_path, monkeypatch):
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        monkeypatch.setattr(
            "core.overlay_utils.discover_plugins_dir", lambda: plugins_dir
        )
        result = _find_overlay_plugin_dir()
        assert result == plugins_dir / "overlaytxt"


class TestOverlayManager:
    def test_loads_config(self, tmp_path, monkeypatch):
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        overlay_dir = plugins_dir / "overlaytxt"
        overlay_dir.mkdir()
        (overlay_dir / "plugin.json").write_text(
            json.dumps({"name": "overlay-text"}), encoding="utf-8"
        )
        save_yaml(
            overlay_dir / "config.yaml",
            {
                "max_fails": 5,
                "cooldown": 15,
                "overlays": [{"name": "alerts"}, {"name": "chat"}],
            },
            backup=False,
        )
        monkeypatch.setattr(
            "core.overlay_utils.discover_plugins_dir", lambda: plugins_dir
        )

        mgr = OverlayManager()
        assert "alerts" in mgr.clients
        assert "chat" in mgr.clients
        assert "default" in mgr.clients  # fallback
        assert mgr.clients["alerts"].max_fails == 5

    def test_loads_fallback_defaults(self, tmp_path, monkeypatch):
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        overlay_dir = plugins_dir / "overlaytxt"
        overlay_dir.mkdir()
        (overlay_dir / "plugin.json").write_text(
            json.dumps({"name": "overlay-text"}), encoding="utf-8"
        )
        save_yaml(overlay_dir / "config.yaml", {}, backup=False)
        monkeypatch.setattr(
            "core.overlay_utils.discover_plugins_dir", lambda: plugins_dir
        )

        mgr = OverlayManager()
        assert "default" in mgr.clients
        assert mgr.clients["default"].max_fails == 3
        assert mgr.clients["default"].cooldown == 10

    def test_dispatch_unknown_overlay(self, tmp_path, monkeypatch):
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        overlay_dir = plugins_dir / "overlaytxt"
        overlay_dir.mkdir()
        (overlay_dir / "plugin.json").write_text(
            json.dumps({"name": "overlay-text"}), encoding="utf-8"
        )
        save_yaml(overlay_dir / "config.yaml", {}, backup=False)
        monkeypatch.setattr(
            "core.overlay_utils.discover_plugins_dir", lambda: plugins_dir
        )

        mgr = OverlayManager()
        result = mgr.dispatch("Title", "Subtitle", 3, "nonexistent")
        assert result is False

    def test_dispatch_during_cooldown(self, tmp_path, monkeypatch):
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        overlay_dir = plugins_dir / "overlaytxt"
        overlay_dir.mkdir()
        (overlay_dir / "plugin.json").write_text(
            json.dumps({"name": "overlay-text"}), encoding="utf-8"
        )
        save_yaml(overlay_dir / "config.yaml", {}, backup=False)
        monkeypatch.setattr(
            "core.overlay_utils.discover_plugins_dir", lambda: plugins_dir
        )

        mgr = OverlayManager()
        client = mgr.clients["default"]
        client._fail_count = client.max_fails
        client._last_fail_time = __import__("time").time()

        result = mgr.dispatch("Title", "Subtitle", 3, "default")
        assert result is False
