import json


class TestReactionCatalogEndpoint:
    def test_catalog_returns_core_events(self, client):
        resp = client.get("/api/v1/reactions/catalog")
        assert resp.status_code == 200
        body = resp.json()
        assert "events" in body
        assert "plugins" in body
        assert "commands" in body
        assert "templates" in body
        assert "tiktok.gift" in body["events"]
        assert "minecraft.player_death" in body["events"]
        assert "server.started" in body["events"]

    def test_catalog_includes_plugin_manifests(self, client, project_dir):
        plugins_dir = project_dir / "src" / "plugins"
        plugin_dir = plugins_dir / "demo"
        plugin_dir.mkdir()
        manifest = {
            "name": "demo",
            "version": "1.0.0",
            "entry_point": "src/plugins/demo/main.py",
            "display_name": "Demo Plugin",
            "icon": "⚡",
            "emitted_events": [
                {
                    "key": "demo.thing",
                    "name": "Thing Happened",
                    "desc": "A thing happened",
                    "icon": "✨",
                }
            ],
            "accepted_commands": {
                "do": {
                    "name": "Do Thing",
                    "desc": "Do a thing",
                    "args": {
                        "count": {
                            "type": "number",
                            "label": "Count",
                            "default": 1,
                            "min": 1,
                        }
                    },
                }
            },
        }
        (plugin_dir / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")

        resp = client.get("/api/v1/reactions/catalog")
        assert resp.status_code == 200
        body = resp.json()
        assert "demo.thing" in body["events"]
        assert body["events"]["demo.thing"]["name"] == "Thing Happened"
        assert body["events"]["demo.thing"]["category"] == "demo"
        assert "demo" in body["plugins"]
        assert body["plugins"]["demo"]["icon"] == "⚡"
        assert "demo" in body["commands"]
        assert "do" in body["commands"]["demo"]
        assert body["commands"]["demo"]["do"]["args"]["count"]["default"] == 1

    def test_catalog_plugin_overrides_core_event(self, client, project_dir):
        plugins_dir = project_dir / "src" / "plugins"
        plugin_dir = plugins_dir / "tweaker"
        plugin_dir.mkdir()
        manifest = {
            "name": "tweaker",
            "version": "1.0.0",
            "entry_point": "src/plugins/tweaker/main.py",
            "display_name": "Tweaker",
            "emitted_events": [
                {
                    "key": "tiktok.gift",
                    "name": "Custom Gift",
                    "desc": "Overridden gift event",
                    "icon": "🎁",
                }
            ],
        }
        (plugin_dir / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")

        resp = client.get("/api/v1/reactions/catalog")
        assert resp.status_code == 200
        body = resp.json()
        assert body["events"]["tiktok.gift"]["name"] == "Custom Gift"
        # Overridden core event is re-categorized under the plugin's name.
        assert body["events"]["tiktok.gift"]["category"] == "tweaker"

    def test_catalog_templates_present(self, client):
        resp = client.get("/api/v1/reactions/catalog")
        body = resp.json()
        assert len(body["templates"]) >= 3
        assert all(
            "event" in t and "plugin" in t and "command" in t for t in body["templates"]
        )
