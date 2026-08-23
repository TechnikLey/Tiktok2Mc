"""Tests for J.3 #12 delivery-side command validation.

``POST /plugins/{name}/command`` warns (but still delivers) when the
command is not in the target plugin's declared ``accepted_commands``.
"""

import json

import pytest


@pytest.fixture
def plugin_with_commands(project_dir, monkeypatch):
    plugins_dir = project_dir / "src" / "plugins"
    plugin_dir = plugins_dir / "validated"
    plugin_dir.mkdir()
    manifest = {
        "name": "validated",
        "version": "1.0.0",
        "entry_point": "src/plugins/validated/main.py",
        "accepted_commands": {"do_thing": {"name": "Do Thing", "desc": "", "args": {}}},
    }
    (plugin_dir / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")

    from core.api.routes import plugin_overlay as routes_mod

    routes_mod.invalidate_accepted_commands_cache()
    yield plugin_dir
    routes_mod.invalidate_accepted_commands_cache()


class TestAcceptedCommandsValidation:
    def test_unknown_command_warns_but_delivers(
        self, client, plugin_with_commands, caplog
    ):
        import logging

        with caplog.at_level(logging.WARNING):
            resp = client.post(
                "/api/v1/plugins/validated/command",
                json={"command": "bogus_command", "args": {}},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        assert "bogus_command" in caplog.text
        assert "accepted_commands" in caplog.text

    def test_declared_command_no_warning(self, client, plugin_with_commands, caplog):
        import logging

        with caplog.at_level(logging.WARNING):
            resp = client.post(
                "/api/v1/plugins/validated/command",
                json={"command": "do_thing", "args": {}},
            )
        assert resp.status_code == 200
        assert "not in accepted_commands" not in caplog.text

    def test_missing_declaration_skips_validation(self, client, project_dir, caplog):
        """No accepted_commands section -> no warning, delivery unaffected."""
        import logging

        plugins_dir = project_dir / "src" / "plugins"
        plugin_dir = plugins_dir / "undeclared"
        plugin_dir.mkdir()
        manifest = {
            "name": "undeclared",
            "version": "1.0.0",
            "entry_point": "src/plugins/undeclared/main.py",
        }
        (plugin_dir / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")

        from core.api.routes import plugin_overlay as routes_mod

        routes_mod.invalidate_accepted_commands_cache()
        try:
            with caplog.at_level(logging.WARNING):
                resp = client.post(
                    "/api/v1/plugins/undeclared/command",
                    json={"command": "anything", "args": {}},
                )
        finally:
            routes_mod.invalidate_accepted_commands_cache()
        assert resp.status_code == 200
        assert "not in accepted_commands" not in caplog.text

    def test_unknown_plugin_skips_validation(self, client, caplog):
        import logging

        from core.api.routes import plugin_overlay as routes_mod

        routes_mod.invalidate_accepted_commands_cache("ghost")
        try:
            with caplog.at_level(logging.WARNING):
                resp = client.post(
                    "/api/v1/plugins/ghost/command",
                    json={"command": "x", "args": {}},
                )
        finally:
            routes_mod.invalidate_accepted_commands_cache("ghost")
        assert resp.status_code == 200
        assert "not in accepted_commands" not in caplog.text

    def test_cache_ttl_respects_invalidation(self, plugin_with_commands):
        from core.api.routes.plugin_overlay import _accepted_commands_for

        assert _accepted_commands_for("validated") == {"do_thing"}
