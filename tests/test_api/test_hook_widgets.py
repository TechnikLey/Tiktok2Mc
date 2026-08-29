"""Tests for hook dashboard widgets (UI extension points).

Hooks with the ``ui`` permission register an HTML widget via the bridge;
the API stores it in memory and serves it as JSON and as a standalone
iframe page for the dashboard.
"""

import json

import pytest


@pytest.fixture
def hook_on_disk(project_dir):
    hooks_dir = project_dir / "src" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook_dir = hooks_dir / "widgethook"
    hook_dir.mkdir()
    (hook_dir / "hook.json").write_text(
        json.dumps(
            {
                "name": "widgethook",
                "version": "1.0.0",
                "entry_point": "main.py",
                "permissions": ["ui"],
            }
        ),
        encoding="utf-8",
    )
    return hook_dir


class TestHookWidgets:
    def test_register_and_list(self, client, project_dir, hook_on_disk):
        resp = client.post(
            "/api/v1/hooks/widgethook/widget",
            json={"title": "Combo Stats", "html": "<b>5x</b>"},
        )
        assert resp.status_code == 200
        listing = client.get("/api/v1/hooks/widgets").json()["widgets"]
        assert {"name": "widgethook", "title": "Combo Stats"} in listing

    def test_register_unknown_hook_404(self, client, project_dir):
        resp = client.post(
            "/api/v1/hooks/ghost/widget",
            json={"title": "x", "html": "<b>y</b>"},
        )
        assert resp.status_code == 404

    def test_register_empty_html_422(self, client, project_dir, hook_on_disk):
        resp = client.post(
            "/api/v1/hooks/widgethook/widget", json={"title": "x", "html": "  "}
        )
        assert resp.status_code == 422

    def test_widget_json_roundtrip(self, client, project_dir, hook_on_disk):
        client.post(
            "/api/v1/hooks/widgethook/widget",
            json={"title": "Stats", "html": "<p>hi</p>"},
        )
        data = client.get("/api/v1/hooks/widgethook/widget").json()
        assert data["name"] == "widgethook"
        assert data["title"] == "Stats"
        assert data["html"] == "<p>hi</p>"

    def test_widget_page_served_as_html(self, client, project_dir, hook_on_disk):
        client.post(
            "/api/v1/hooks/widgethook/widget",
            json={"title": "Stats", "html": "<p id='w'>hello</p>"},
        )
        resp = client.get("/api/v1/hooks/widgethook/widget.html")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "hello" in resp.text

    def test_widget_missing_404(self, client, project_dir):
        assert client.get("/api/v1/hooks/nope/widget").status_code == 404

    def test_disable_removes_widget(self, client, project_dir, hook_on_disk):
        from core.hook_registry import HookRegistration, get_hook_registry

        get_hook_registry().register(HookRegistration(name="widgethook", enabled=True))
        client.post(
            "/api/v1/hooks/widgethook/widget",
            json={"title": "t", "html": "<b>x</b>"},
        )
        resp = client.post("/api/v1/hooks/widgethook/disable")
        assert resp.status_code == 200
        assert client.get("/api/v1/hooks/widgethook/widget").status_code == 404
