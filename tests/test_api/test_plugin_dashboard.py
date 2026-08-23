"""Tests for J.3 #11 plugin dashboard pages.

Plugins register their dashboard HTML via ``POST /plugins/{name}/dashboard-html``
and the API serves it at ``GET /plugins/{name}/dashboard`` so the web
dashboard can embed it as a tab.
"""

import json

import pytest


@pytest.fixture
def dash_plugin(project_dir):
    plugins_dir = project_dir / "src" / "plugins"
    plugin_dir = plugins_dir / "dashy"
    plugin_dir.mkdir()
    manifest = {
        "name": "dashy",
        "version": "1.0.0",
        "entry_point": "src/plugins/dashy/main.py",
        "dashboard_ui": True,
    }
    (plugin_dir / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
    (plugin_dir / "main.py").write_text("# stub\n", encoding="utf-8")
    return plugin_dir


class TestDashboardRoutes:
    def test_register_and_serve_dashboard(self, client, dash_plugin):
        resp = client.post(
            "/api/v1/plugins/dashy/dashboard-html",
            json={"html": "<html><body><h1>Dashboard</h1></body></html>"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

        served = client.get("/api/v1/plugins/dashy/dashboard")
        assert served.status_code == 200
        assert "Dashboard" in served.text
        assert served.headers["content-type"].startswith("text/html")

    def test_register_replaces_previous_html(self, client, dash_plugin):
        client.post(
            "/api/v1/plugins/dashy/dashboard-html",
            json={"html": "<html>old</html>"},
        )
        client.post(
            "/api/v1/plugins/dashy/dashboard-html",
            json={"html": "<html>new</html>"},
        )
        served = client.get("/api/v1/plugins/dashy/dashboard")
        assert "new" in served.text
        assert "old" not in served.text

    def test_serve_unknown_dashboard_404(self, client):
        resp = client.get("/api/v1/plugins/nope/dashboard")
        assert resp.status_code == 404

    def test_register_without_html_422(self, client, dash_plugin):
        resp = client.post("/api/v1/plugins/dashy/dashboard-html", json={})
        assert resp.status_code == 422

    def test_list_plugins_exposes_manifest_flag(self, client, dash_plugin):
        """The manifest's dashboard_ui flag reaches GET /plugins responses."""
        resp = client.post(
            "/api/v1/plugins/register",
            json={
                "name": "dashy",
                "path": str(dash_plugin / "main.py"),
                "entry_point": "src/plugins/dashy/main.py",
                "enabled": True,
            },
        )
        assert resp.status_code == 201
        listed = client.get("/api/v1/plugins")
        assert listed.status_code == 200
        entry = next(p for p in listed.json()["plugins"] if p["name"] == "dashy")
        assert entry["dashboard_ui"] is True

    def test_bundled_flag_exposed_and_default_false(self, client, project_dir):
        """'bundled' comes from the manifest; third-party plugins default to False."""
        plugins_dir = project_dir / "src" / "plugins"
        for name, bundled in (("coreplug", True), ("external", None)):
            plugin_dir = plugins_dir / name
            plugin_dir.mkdir()
            manifest: dict = {"name": name, "version": "1.0.0"}
            if bundled is not None:
                manifest["bundled"] = bundled
            (plugin_dir / "plugin.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            (plugin_dir / "main.py").write_text("# stub\n", encoding="utf-8")
            resp = client.post(
                "/api/v1/plugins/register",
                json={
                    "name": name,
                    "path": str(plugin_dir / "main.py"),
                    "entry_point": f"src/plugins/{name}/main.py",
                    "enabled": True,
                },
            )
            assert resp.status_code == 201

        listed = client.get("/api/v1/plugins").json()["plugins"]
        by_name = {p["name"]: p for p in listed}
        assert by_name["coreplug"]["bundled"] is True
        assert by_name["external"]["bundled"] is False
