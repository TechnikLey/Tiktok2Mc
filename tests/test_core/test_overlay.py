from core.overlay import (
    OverlayClient,
    OverlayConfig,
    OverlayManager,
)
from core.yaml_utils import save_yaml


class TestOverlayClient:
    def test_circuit_breaker(self):
        client = OverlayClient("test", 2, 5)
        assert client.get_cooldown_status() == (False, 0)
        client.mark_failure()
        client.mark_failure()
        blocked, remaining = client.get_cooldown_status()
        assert blocked is True
        assert 0 <= remaining <= 5
        client.mark_success()
        assert client.get_cooldown_status() == (False, 0)


class TestOverlayConfig:
    def test_loads_from_global_config(self, tmp_path, monkeypatch):
        config_file = tmp_path / "config.yaml"
        save_yaml(
            config_file,
            {"overlay": {"display_mode": "queue", "fade_in": 1000}},
            backup=False,
        )
        monkeypatch.setattr("core.overlay.get_config_file", lambda: config_file)

        cfg = OverlayConfig()
        assert cfg.get("display_mode") == "queue"
        assert cfg.get("fade_in") == 1000
        assert cfg.get("fade_out") == 500  # default

    def test_fallback_defaults(self, tmp_path, monkeypatch):
        config_file = tmp_path / "config.yaml"
        save_yaml(config_file, {}, backup=False)
        monkeypatch.setattr("core.overlay.get_config_file", lambda: config_file)

        cfg = OverlayConfig()
        assert cfg.get("display_mode") == "overwrite"
        assert cfg.get("max_fails") == 3


class TestOverlayManager:
    def test_render_html(self, tmp_path, monkeypatch):
        config_file = tmp_path / "config.yaml"
        save_yaml(
            config_file,
            {
                "overlay": {
                    "display_mode": "queue",
                    "fade_in": 250,
                    "fade_out": 750,
                    "overlays": [{"name": "alerts"}],
                }
            },
            backup=False,
        )
        monkeypatch.setattr("core.overlay.get_config_file", lambda: config_file)

        mgr = OverlayManager()
        html = mgr.render_html("alerts", chroma=True)
        assert "queue" in html
        assert "250" in html
        assert "750" in html
        assert "alerts" in html
        assert "#00FF00" in html  # default background

    def test_render_html_escapes_overlay_name(self, tmp_path, monkeypatch):
        config_file = tmp_path / "config.yaml"
        save_yaml(config_file, {}, backup=False)
        monkeypatch.setattr("core.overlay.get_config_file", lambda: config_file)

        mgr = OverlayManager()
        html = mgr.render_html('x";alert(1);//', chroma=False)
        assert 'const OVERLAY_NAME = "x\\";alert(1);//";' in html
        assert html.count("</script>") == 1

    def test_render_html_sanitizes_theme_overrides(self, tmp_path, monkeypatch):
        config_file = tmp_path / "config.yaml"
        save_yaml(config_file, {}, backup=False)
        monkeypatch.setattr("core.overlay.get_config_file", lambda: config_file)

        mgr = OverlayManager()
        html = mgr.render_html(
            "default",
            chroma=True,
            theme_overrides={
                "background": "</style><script>alert(1)</script>",
            },
        )
        assert html.count("</style>") == 1
        assert html.count("<script>") == 1
        assert "--background: /stylescriptalert(1)/script;" in html

    def test_dispatch_unknown_overlay(self, tmp_path, monkeypatch):
        config_file = tmp_path / "config.yaml"
        save_yaml(config_file, {}, backup=False)
        monkeypatch.setattr("core.overlay.get_config_file", lambda: config_file)

        mgr = OverlayManager()
        assert mgr.dispatch("T", "S", 3, "missing") is False


class TestOverlayApiRoutes:
    def test_overlay_html_endpoint(self, client):
        """Test that the overlay HTML endpoint returns valid HTML."""
        response = client.get("/api/v1/overlay?overlay=default&chroma=1")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "default" in response.text

    def test_overlay_display_endpoint(self, client):
        """Test the overlay display command endpoint."""
        response = client.post(
            "/api/v1/overlay/display",
            json={
                "title": "Hello",
                "subtitle": "World",
                "duration": 5,
                "overlay_name": "default",
            },
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_overlay_display_unknown_overlay(self, client):
        """Test that an unknown overlay returns 404."""
        response = client.post(
            "/api/v1/overlay/display",
            json={
                "title": "Hello",
                "subtitle": "World",
                "duration": 5,
                "overlay_name": "nonexistent",
            },
        )
        assert response.status_code == 404
