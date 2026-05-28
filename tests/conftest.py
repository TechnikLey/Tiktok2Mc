import sys
import os
import tempfile
import yaml
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

# Ensure src/ is on sys.path so `import core.*` works.
_src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

MINIMAL_CONFIG = {
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


@pytest.fixture(scope="session")
def project_dir():
    with tempfile.TemporaryDirectory(prefix="tiktok2mc_test_") as tmp:
        root = Path(tmp)
        config_file = root / "config.yaml"
        with config_file.open("w", encoding="utf-8") as f:
            yaml.dump(MINIMAL_CONFIG, f)
        (root / "data").mkdir()
        (root / "plugins").mkdir()
        yield root


@pytest.fixture(scope="session", autouse=True)
def _patch_paths(project_dir):
    import core.paths

    orig_root_dir = core.paths.get_root_dir
    orig_config_file = core.paths.get_config_file
    core.paths.get_root_dir = lambda: project_dir
    core.paths.get_config_file = lambda: project_dir / "config.yaml"
    yield
    core.paths.get_root_dir = orig_root_dir
    core.paths.get_config_file = orig_config_file


@pytest.fixture
def client():
    from core.api import create_app

    app = create_app()
    with TestClient(app) as tc:
        yield tc
