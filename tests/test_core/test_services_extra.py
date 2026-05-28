import pytest
import yaml


class TestApiServiceFallback:
    def test_fallback_to_defaults_when_config_missing(
        self, project_dir, monkeypatch
    ):
        from core.api.services import ApiService

        main_config = project_dir / "config.yaml"
        main_config.unlink()
        defaults_dir = project_dir / "defaults"
        defaults_dir.mkdir(exist_ok=True)
        fallback = defaults_dir / "config.yaml"
        fallback.write_text(
            yaml.dump(
                {
                    "config_version": "1.0",
                    "auto_update_config": True,
                    "show_sudo_warning": False,
                    "server_host": "127.0.0.1",
                    "control_method": "DCS",
                    "shutdown": {},
                    "java": {},
                    "rcon": {},
                    "tiktok": {},
                    "comment_commands": {},
                    "random_triggers": {},
                    "console": {},
                    "minecraft_server_api": {},
                    "overlay_text": {"enabled": False},
                    "like_goal": {"enabled": False},
                    "timer": {"enabled": False},
                    "death_counter": {"enabled": False},
                    "win_counter": {"enabled": False},
                    "gui": {},
                    "spotify": {"enabled": False},
                    "channel_points": {"enabled": False},
                    "theme": {},
                    "update": {},
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(
            "core.paths.get_config_file", lambda: main_config
        )
        monkeypatch.setattr(
            "core.paths.get_root_dir", lambda: project_dir
        )

        svc = ApiService()
        assert svc.config_path == fallback
        assert svc.get_config_status() is True


class TestConfigFileCorrupt:
    def test_read_corrupt_yaml_raises(self, project_dir, monkeypatch):
        config_file = project_dir / "config.yaml"
        config_file.write_text(": broken yaml [", encoding="utf-8")
        monkeypatch.setattr(
            "core.paths.get_config_file", lambda: config_file
        )

        from core.api.services import ApiService

        svc = ApiService()
        with pytest.raises(Exception):
            svc.read_config()
