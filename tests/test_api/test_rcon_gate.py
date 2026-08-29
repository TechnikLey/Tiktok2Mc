"""Tests for C.3 #8: the ``rcon.http_command_api`` gate.

``POST /api/v1/rcon/command`` executes commands directly against the
Minecraft server (bypassing the bridge's RCON queue). It is disabled by
default (``rcon.http_command_api: false``) and rejects such requests with
403/MC-0012; enabling it in config.yaml turns it on for the dashboard
console and extensions.
"""

import pytest

from core.api.routes import rcon as rcon_routes
from core.yaml_utils import save_yaml


@pytest.fixture
def fake_rcon(monkeypatch):
    """Replace the real RCON service (no server in the test environment)."""

    class FakeSvc:
        connected = True
        host = "localhost"
        port = 25575

        def __init__(self) -> None:
            self.command_calls: list[str] = []

        def configure(self, host: str, port: int, password: str) -> None:
            pass

        async def command(self, cmd: str) -> str:
            self.command_calls.append(cmd)
            return f"echo:{cmd}"

    svc = FakeSvc()
    monkeypatch.setattr(rcon_routes, "get_rcon_service", lambda: svc)
    return svc


def _set_rcon_config(project_dir, rcon_cfg: dict) -> None:
    from core.api.services import ApiService

    config_path = project_dir / "config.yaml"
    current = ApiService().read_config() if config_path.exists() else {}
    current["rcon"] = rcon_cfg
    save_yaml(config_path, current, backup=False)
    # Force the route module to drop its cached ApiService singleton
    rcon_routes._api_service = None


class TestHttpCommandGate:
    def test_disabled_rejects_with_mc_0012(self, client, project_dir, fake_rcon):
        _set_rcon_config(project_dir, {"http_command_api": False})
        resp = client.post("/api/v1/rcon/command", json={"command": "say hi"})
        assert resp.status_code == 403
        assert "MC-0012" in resp.json()["detail"]
        assert fake_rcon.command_calls == []

    def test_missing_key_defaults_to_disabled(self, client, project_dir, fake_rcon):
        """Default is false — direct commands are rejected out of the box."""
        _set_rcon_config(project_dir, {})
        resp = client.post("/api/v1/rcon/command", json={"command": "say hi"})
        assert resp.status_code == 403
        assert "MC-0012" in resp.json()["detail"]
        assert fake_rcon.command_calls == []

    def test_explicit_true_executes(self, client, project_dir, fake_rcon):
        _set_rcon_config(project_dir, {"http_command_api": True})
        resp = client.post("/api/v1/rcon/command", json={"command": "list"})
        assert resp.status_code == 200
        assert resp.json()["response"] == "echo:list"

    def test_status_stays_available_when_disabled(self, client, project_dir, fake_rcon):
        _set_rcon_config(project_dir, {"http_command_api": False})
        resp = client.get("/api/v1/rcon/status")
        assert resp.status_code == 200
        assert resp.json()["connected"] is True
