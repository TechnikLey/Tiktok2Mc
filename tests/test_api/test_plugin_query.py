"""Tests for C.3 #3: plugin queries with correlation ids.

``POST /plugins/{name}/query`` delivers a query through the plugin's
command queue (reserved command ``__query__``) and waits for the plugin's
answer posted to ``POST /plugins/{name}/query-response``.
"""

import json
import threading
import time

import pytest


@pytest.fixture
def query_plugin(project_dir):
    plugins_dir = project_dir / "src" / "plugins"
    plugin_dir = plugins_dir / "qtest"
    plugin_dir.mkdir()
    manifest = {
        "name": "qtest",
        "version": "1.0.0",
        "entry_point": "src/plugins/qtest/main.py",
        "queries": ["top", "stats"],
    }
    (plugin_dir / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
    from core.api.registry import get_registry

    get_registry().register(
        __import__(
            "core.api.models", fromlist=["PluginRegistration"]
        ).PluginRegistration(
            name="qtest",
            path=str(plugin_dir / "main.py"),
            entry_point="src/plugins/qtest/main.py",
            enabled=True,
        )
    )
    return plugin_dir


def _drain_and_respond(client, result=None, error=None, delay=0.0):
    """Simulate the plugin process: poll commands, answer the first query."""

    def worker():
        if delay:
            time.sleep(delay)
        deadline = time.time() + 5
        while time.time() < deadline:
            resp = client.get("/api/v1/plugins/qtest/commands")
            entries = [
                e
                for e in resp.json().get("commands", [])
                if e["command"] == "__query__"
            ]
            if entries:
                # Answer every pending query (stale ids resolve as False)
                for entry in entries:
                    body = {"id": entry["args"]["_query_id"]}
                    if error is not None:
                        body.update({"ok": False, "error": error})
                    else:
                        body.update({"ok": True, "result": result})
                    client.post("/api/v1/plugins/qtest/query-response", json=body)
                return
            time.sleep(0.02)

    t = threading.Thread(target=worker)
    t.start()
    return t


class TestPluginQuery:
    def test_unknown_plugin_404(self, client, project_dir):
        resp = client.post("/api/v1/plugins/nope/query", json={"query": "x"})
        assert resp.status_code == 404

    def test_undeclared_query_404(self, client, project_dir, query_plugin):
        resp = client.post("/api/v1/plugins/qtest/query", json={"query": "bogus"})
        assert resp.status_code == 404
        assert "top" in resp.json()["detail"]

    def test_missing_query_field_422(self, client, project_dir, query_plugin):
        resp = client.post("/api/v1/plugins/qtest/query", json={})
        assert resp.status_code == 422

    def test_query_roundtrip(self, client, project_dir, query_plugin):
        t = _drain_and_respond(client, result={"users": ["alice", "bob"]})
        resp = client.post("/api/v1/plugins/qtest/query", json={"query": "top"})
        t.join(timeout=5)
        assert resp.status_code == 200
        assert resp.json()["result"] == {"users": ["alice", "bob"]}

    def test_query_timeout_504(self, client, project_dir, query_plugin):
        resp = client.post(
            "/api/v1/plugins/qtest/query", json={"query": "top", "timeout": 0.5}
        )
        assert resp.status_code == 504
        assert "PLUGIN-0018" in resp.json()["detail"]

    def test_query_handler_error_502(self, client, project_dir, query_plugin):
        """A failed handler surfaces as 502 PLUGIN-0019 with the error."""
        t = _drain_and_respond(client, error="boom")
        # Generous caller timeout: under a fully loaded test suite the
        # answering thread can lag; only the explicit-timeout test (below)
        # must produce a 504.
        resp = client.post(
            "/api/v1/plugins/qtest/query", json={"query": "top", "timeout": 20}
        )
        t.join(timeout=5)
        assert resp.status_code == 502
        assert "PLUGIN-0019" in resp.json()["detail"]

    def test_response_for_unknown_id_is_accepted(
        self, client, project_dir, query_plugin
    ):
        """Late answers (caller already timed out) must not error."""
        resp = client.post(
            "/api/v1/plugins/qtest/query-response",
            json={"id": "does-not-exist", "ok": True, "result": 1},
        )
        assert resp.status_code == 200
        assert resp.json()["resolved"] is False

    def test_reserved_query_skips_command_validation(
        self, client, caplog, query_plugin
    ):
        """__query__ deliveries must not warn about accepted_commands."""
        import logging

        (query_plugin / "main.py").write_text("# stub\n", encoding="utf-8")
        manifest_path = query_plugin / "plugin.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["accepted_commands"] = {
            "do_thing": {"name": "Do Thing", "desc": "", "args": {}}
        }
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        from core.api.routes import plugin_overlay as routes_mod

        routes_mod.invalidate_accepted_commands_cache("qtest")
        try:
            with caplog.at_level(logging.WARNING):
                resp = client.post(
                    "/api/v1/plugins/qtest/command",
                    json={"command": "__query__", "args": {}},
                )
            assert resp.status_code == 200
            assert "not in accepted_commands" not in caplog.text
        finally:
            routes_mod.invalidate_accepted_commands_cache("qtest")


class TestQueryDiscovery:
    def _write_plugin(self, plugins_dir, name, manifest):
        d = plugins_dir / name
        d.mkdir()
        (d / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
        return d

    def test_lists_declared_queries(self, client, project_dir):
        self._write_plugin(
            project_dir / "src" / "plugins",
            "disc",
            {"name": "disc", "version": "1.0.0", "queries": ["stats", "top"]},
        )
        resp = client.get("/api/v1/plugins/queries")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert data["plugins"] == [
            {"name": "disc", "queries": ["stats", "top"], "enabled": False}
        ]

    def test_plugins_without_queries_omitted(self, client, project_dir):
        plugins_dir = project_dir / "src" / "plugins"
        self._write_plugin(plugins_dir, "noq", {"name": "noq", "version": "1.0.0"})
        self._write_plugin(
            plugins_dir, "emptyq", {"name": "emptyq", "version": "1.0.0", "queries": []}
        )
        resp = client.get("/api/v1/plugins/queries")
        assert resp.status_code == 200
        assert resp.json() == {"total": 0, "plugins": []}

    def test_broken_manifest_skipped(self, client, project_dir):
        plugins_dir = project_dir / "src" / "plugins"
        self._write_plugin(
            plugins_dir, "good", {"name": "good", "version": "1.0.0", "queries": ["x"]}
        )
        broken = plugins_dir / "broken"
        broken.mkdir()
        (broken / "plugin.json").write_text("{not json", encoding="utf-8")
        resp = client.get("/api/v1/plugins/queries")
        assert resp.status_code == 200
        data = resp.json()
        assert [p["name"] for p in data["plugins"]] == ["good"]

    def test_enabled_flag_from_registry(self, client, project_dir, query_plugin):
        resp = client.get("/api/v1/plugins/queries")
        assert resp.status_code == 200
        data = resp.json()
        entry = next(p for p in data["plugins"] if p["name"] == "qtest")
        assert entry["queries"] == ["stats", "top"]
        assert entry["enabled"] is True

    def test_list_endpoint_includes_queries_field(
        self, client, project_dir, query_plugin
    ):
        """GET /plugins exposes the declared queries per plugin."""
        resp = client.get("/api/v1/plugins")
        assert resp.status_code == 200
        entry = next(p for p in resp.json()["plugins"] if p["name"] == "qtest")
        assert entry["queries"] == ["stats", "top"]

    def test_list_endpoint_without_manifest_empty(self, client, project_dir):
        """Registered plugins without a manifest report no queries."""
        from core.api.models import PluginRegistration
        from core.api.registry import get_registry

        get_registry().register(
            PluginRegistration(name="bare", path="", entry_point="", enabled=True)
        )
        resp = client.get("/api/v1/plugins")
        assert resp.status_code == 200
        entry = next(p for p in resp.json()["plugins"] if p["name"] == "bare")
        assert entry["queries"] == []
