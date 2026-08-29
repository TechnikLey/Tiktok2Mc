"""Tests for the generic plugin RPC endpoint (custom endpoints).

``POST /plugins/{name}/rpc`` delivers a REST-style call through the
plugin's command queue (reserved command ``__rpc__``) and waits for the
answer posted to ``POST /plugins/{name}/query-response`` — reusing the
query correlation machinery.
"""

import json
import threading

import pytest


@pytest.fixture
def rpc_plugin(project_dir):
    plugins_dir = project_dir / "src" / "plugins"
    plugin_dir = plugins_dir / "rpctest"
    plugin_dir.mkdir()
    manifest = {
        "name": "rpctest",
        "version": "1.0.0",
        "entry_point": "src/plugins/rpctest/main.py",
    }
    (plugin_dir / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
    from core.api.models import PluginRegistration
    from core.api.registry import get_registry

    get_registry().register(
        PluginRegistration(
            name="rpctest",
            path=str(plugin_dir / "main.py"),
            entry_point="src/plugins/rpctest/main.py",
            enabled=True,
        )
    )
    return plugin_dir


def _drain_and_respond_rpc(client, result=None, error=None, command="__rpc__"):
    """Simulate the plugin process: poll commands, answer the first RPC."""
    client.get("/api/v1/plugins/rpctest/commands")

    def worker():
        deadline = __import__("time").time() + 5
        while __import__("time").time() < deadline:
            resp = client.get("/api/v1/plugins/rpctest/commands")
            entries = [
                e for e in resp.json().get("commands", []) if e["command"] == command
            ]
            if entries:
                for entry in entries:
                    body = {"id": entry["args"]["_rpc_id"]}
                    if error is not None:
                        body.update({"ok": False, "error": error})
                    else:
                        body.update({"ok": True, "result": result})
                    client.post("/api/v1/plugins/rpctest/query-response", json=body)
                return
            __import__("time").sleep(0.02)

    t = threading.Thread(target=worker)
    t.start()
    return t


class TestPluginRpcRoute:
    def test_unknown_plugin_404(self, client, project_dir):
        resp = client.post(
            "/api/v1/plugins/nope/rpc", json={"method": "GET", "path": "/x"}
        )
        assert resp.status_code == 404

    @pytest.mark.parametrize(
        "payload",
        [
            {"method": "TELEPORT", "path": "/x"},  # invalid method
            {"path": "/x"},  # missing method -> defaults GET, ok
            {"method": "GET"},  # missing path
            {"method": "GET", "path": "no-slash"},
            {"method": "GET", "path": "/x", "body": [1, 2]},  # body not object
        ],
    )
    def test_validation_422(self, client, project_dir, rpc_plugin, payload):
        expect_422 = payload != {"path": "/x"}
        # The one valid case must return fast (no plugin process answers).
        if not expect_422:
            payload = {**payload, "timeout": 0.5}
        resp = client.post("/api/v1/plugins/rpctest/rpc", json=payload)
        assert (resp.status_code == 422) is expect_422

    def test_rpc_enqueues_reserved_command(self, client, project_dir, rpc_plugin):
        # Drain stale entries from earlier tests.
        client.get("/api/v1/plugins/rpctest/commands")
        resp = client.post(
            "/api/v1/plugins/rpctest/rpc",
            json={"method": "POST", "path": "/songs/42", "body": {"play": True}},
        )
        assert resp.status_code != 404  # accepted for delivery
        cmds = client.get("/api/v1/plugins/rpctest/commands").json()["commands"]
        entry = next(c for c in cmds if c["command"] == "__rpc__")
        args = entry["args"]
        assert args["_rpc_method"] == "POST"
        assert args["_rpc_path"] == "/songs/42"
        assert args["_rpc_body"] == {"play": True}
        assert args["_rpc_id"]

    def test_rpc_roundtrip(self, client, project_dir, rpc_plugin):
        responder = _drain_and_respond_rpc(client, result={"playing": True})
        try:
            resp = client.post(
                "/api/v1/plugins/rpctest/rpc",
                json={"method": "GET", "path": "/player/state"},
            )
        finally:
            responder.join(timeout=5)
        assert resp.status_code == 200
        body = resp.json()
        assert body["result"] == {"playing": True}

    def test_rpc_handler_error_502(self, client, project_dir, rpc_plugin):
        responder = _drain_and_respond_rpc(client, error="boom")
        try:
            resp = client.post(
                "/api/v1/plugins/rpctest/rpc",
                json={"method": "DELETE", "path": "/songs/42"},
            )
        finally:
            responder.join(timeout=5)
        assert resp.status_code == 502
        assert "PLUGIN-0019" in resp.json()["detail"]

    def test_rpc_timeout_504(self, client, project_dir, rpc_plugin):
        # No responder: minimum timeout bound keeps this fast.
        resp = client.post(
            "/api/v1/plugins/rpctest/rpc",
            json={"method": "GET", "path": "/slow", "timeout": 0.5},
        )
        assert resp.status_code == 504
        assert "PLUGIN-0018" in resp.json()["detail"]
