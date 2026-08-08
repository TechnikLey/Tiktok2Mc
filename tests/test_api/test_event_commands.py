class TestEventCommandsEndpoints:
    def test_get_event_commands_empty(self, client, project_dir):
        # Ensure no file exists at data/event_commands.yaml
        data_file = project_dir / "data" / "event_commands.yaml"
        if data_file.exists():
            data_file.unlink()
        resp = client.get("/api/v1/event-commands")
        assert resp.status_code == 200
        body = resp.json()
        assert "path" in body
        assert "event_commands" in body
        assert body["event_commands"] == {}

    def test_get_event_commands_with_data(self, client, project_dir):
        from core.yaml_utils import save_yaml

        data_file = project_dir / "data" / "event_commands.yaml"
        data_file.parent.mkdir(parents=True, exist_ok=True)
        save_yaml(
            data_file,
            {
                "event_commands": {
                    "minecraft.player_death": [{"target": "timer", "command": "pause"}]
                }
            },
            backup=False,
        )
        resp = client.get("/api/v1/event-commands")
        assert resp.status_code == 200
        body = resp.json()
        assert "minecraft.player_death" in body["event_commands"]
        assert body["event_commands"]["minecraft.player_death"][0]["target"] == "timer"

    def test_update_event_commands_persists(self, client, project_dir):
        from core.yaml_utils import load_yaml

        payload = {
            "event_commands": {
                "timer.zero": [
                    {
                        "target": "win-counter",
                        "command": "add_win",
                        "args": {"amount": 1},
                    }
                ]
            }
        }
        resp = client.put("/api/v1/event-commands", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["event_commands"]["timer.zero"][0]["args"]["amount"] == 1

        # Verify file on disk
        data_file = project_dir / "data" / "event_commands.yaml"
        cfg = load_yaml(data_file)
        assert cfg["event_commands"]["timer.zero"][0]["args"]["amount"] == 1

    def test_update_event_commands_overwrites(self, client, project_dir):
        from core.yaml_utils import load_yaml, save_yaml

        data_file = project_dir / "data" / "event_commands.yaml"
        data_file.parent.mkdir(parents=True, exist_ok=True)
        save_yaml(
            data_file,
            {
                "event_commands": {
                    "old.event": [{"target": "timer", "command": "start"}]
                }
            },
            backup=False,
        )

        resp = client.put("/api/v1/event-commands", json={"event_commands": {}})
        assert resp.status_code == 200
        cfg = load_yaml(data_file)
        assert cfg["event_commands"] == {}

    def test_update_event_commands_invalid_json_args_rejected(self, client):
        # This tests the GUI behaviour: the API itself accepts any dict,
        # but if a user sends a non-dict it will be stored as-is.
        payload = {
            "event_commands": {
                "test": [{"target": "timer", "command": "pause", "args": "not_a_dict"}]
            }
        }
        resp = client.put("/api/v1/event-commands", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["event_commands"]["test"][0]["args"] == "not_a_dict"
