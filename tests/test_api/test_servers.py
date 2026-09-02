class TestServersList:
    def test_default_instance_reports_missing_jar(self, client, project_dir):
        resp = client.get("/api/v1/servers")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["instances"]) >= 1
        default = next(i for i in body["instances"] if i["id"] == "default")
        assert default["hasJar"] is False

    def test_current_version_is_reported(self, client, project_dir):
        resp = client.get("/api/v1/servers")
        assert resp.status_code == 200
        body = resp.json()
        assert "current_version" in body
        assert body["current_version"] == "1.21.11"

    def test_instance_reports_jar_after_installation(self, client, project_dir):
        jar_dir = project_dir / "server" / "default"
        jar_dir.mkdir(parents=True, exist_ok=True)
        (jar_dir / "server.jar").write_bytes(b"fake jar content")

        resp = client.get("/api/v1/servers")
        assert resp.status_code == 200
        body = resp.json()
        default = next(i for i in body["instances"] if i["id"] == "default")
        assert default["hasJar"] is True

    def test_get_instance_includes_has_jar(self, client, project_dir):
        resp = client.get("/api/v1/servers/instances/default")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == "default"
        assert "hasJar" in body
        assert body["hasJar"] is False


class TestOpenInstanceFolder:
    async def test_open_with_check_reports_failure(self, monkeypatch):
        from unittest.mock import AsyncMock, MagicMock

        from core.api.routes.servers import _open_with_check

        proc = MagicMock()
        proc.returncode = 1
        monkeypatch.setattr("asyncio.to_thread", AsyncMock(return_value=proc))
        assert await _open_with_check(["xdg-open", "/tmp/foo"]) is False

    async def test_open_with_check_reports_success(self, monkeypatch):
        from unittest.mock import AsyncMock, MagicMock

        from core.api.routes.servers import _open_with_check

        proc = MagicMock()
        proc.returncode = 0
        monkeypatch.setattr("asyncio.to_thread", AsyncMock(return_value=proc))
        assert await _open_with_check(["xdg-open", "/tmp/foo"]) is True

    async def test_open_with_check_missing_opener(self, monkeypatch):
        from core.api.routes.servers import _open_with_check

        async def raise_fnf(*_a, **_k):
            raise FileNotFoundError

        monkeypatch.setattr("asyncio.to_thread", raise_fnf)
        assert await _open_with_check(["xdg-open", "/tmp/foo"]) is False

    async def test_open_folder_linux_xdg_success(self, monkeypatch):
        from pathlib import Path
        from unittest.mock import AsyncMock, MagicMock

        from core.api.routes.servers import _open_folder_linux

        monkeypatch.setattr("shutil.which", lambda name: f"/usr/bin/{name}")
        proc = MagicMock()
        proc.returncode = 0
        monkeypatch.setattr("asyncio.to_thread", AsyncMock(return_value=proc))
        ok, reason = await _open_folder_linux(Path("/tmp/foo"))
        assert ok is True
        assert reason == ""

    async def test_open_folder_linux_falls_back_to_file_manager(self, monkeypatch):
        from pathlib import Path
        from unittest.mock import AsyncMock

        from core.api.routes.servers import _open_folder_linux

        which_map = {
            "xdg-open": "/usr/bin/xdg-open",
            "nautilus": "/usr/bin/nautilus",
        }
        monkeypatch.setattr("shutil.which", lambda name: which_map.get(name))

        results = {
            "/usr/bin/xdg-open": 1,
            "/usr/bin/nautilus": 0,
        }

        async def fake_to_thread(fn, *args, **_k):
            cmd = args[0]
            proc = AsyncMock()
            proc.returncode = results.get(cmd[0], 1)
            return proc

        monkeypatch.setattr("asyncio.to_thread", fake_to_thread)
        ok, reason = await _open_folder_linux(Path("/tmp/foo"))
        assert ok is True
        assert reason == ""

    async def test_open_folder_linux_no_file_manager(self, monkeypatch):
        from pathlib import Path

        from core.api.routes.servers import _open_folder_linux

        monkeypatch.setattr("shutil.which", lambda name: None)
        ok, reason = await _open_folder_linux(Path("/tmp/foo"))
        assert ok is False
        assert "No file manager" in reason

    def test_open_instance_folder_missing_instance(self, client):
        resp = client.post("/api/v1/servers/instances/nope/open")
        assert resp.status_code == 404
