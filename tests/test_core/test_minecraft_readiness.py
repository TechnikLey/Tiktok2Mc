from unittest.mock import MagicMock, patch

import pytest


class TestReadServerProperties:
    def test_read_properties(self, tmp_path):
        from core.minecraft_readiness import _read_server_properties

        instance_dir = tmp_path / "server"
        instance_dir.mkdir()
        props_file = instance_dir / "server.properties"
        props_file.write_text(
            "enable-rcon=true\nrcon.port=25575\nrcon.password=secret\nsome.key=value\n",
            encoding="utf-8",
        )
        props = _read_server_properties(instance_dir)
        assert props["enable-rcon"] == "true"
        assert props["rcon.port"] == "25575"
        assert props["rcon.password"] == "secret"
        assert props["some.key"] == "value"

    def test_read_properties_missing_file(self, tmp_path):
        from core.minecraft_readiness import _read_server_properties

        props = _read_server_properties(tmp_path / "nonexistent")
        assert props == {}

    def test_read_properties_skip_comments_and_blanks(self, tmp_path):
        from core.minecraft_readiness import _read_server_properties

        instance_dir = tmp_path / "server"
        instance_dir.mkdir()
        props_file = instance_dir / "server.properties"
        props_file.write_text("# this is a comment\n\nkey=val\n", encoding="utf-8")
        props = _read_server_properties(instance_dir)
        assert props == {"key": "val"}

    def test_read_properties_handles_exception(self, tmp_path):
        from core.minecraft_readiness import _read_server_properties

        f = tmp_path / "server.properties"
        f.write_text("key=val", encoding="utf-8")
        f.chmod(0o000)
        try:
            props = _read_server_properties(tmp_path)
        finally:
            f.chmod(0o666)
        assert isinstance(props, dict)

    def test_read_properties_strips_whitespace(self, tmp_path):
        from core.minecraft_readiness import _read_server_properties

        instance_dir = tmp_path / "server"
        instance_dir.mkdir()
        (instance_dir / "server.properties").write_text(
            "  key  =  val  \n", encoding="utf-8"
        )
        props = _read_server_properties(instance_dir)
        assert props["key"] == "val"


class TestMakeMinecraftReadinessCheck:
    @pytest.mark.asyncio
    async def test_rcon_enabled_and_connected(self, tmp_path):
        from core.minecraft_readiness import make_minecraft_readiness_check

        instance_dir = tmp_path / "server"
        instance_dir.mkdir()
        (instance_dir / "server.properties").write_text(
            "enable-rcon=true\nrcon.port=25575\nrcon.password=secret\n",
            encoding="utf-8",
        )

        check = make_minecraft_readiness_check(instance_dir)
        with patch("core.minecraft_readiness.MCRcon") as MockMCRcon:
            mock_conn = MagicMock()
            MockMCRcon.return_value = mock_conn
            result = await check()
        assert result is True

    @pytest.mark.asyncio
    async def test_rcon_enabled_but_connection_fails(self, tmp_path):
        from core.minecraft_readiness import make_minecraft_readiness_check

        instance_dir = tmp_path / "server"
        instance_dir.mkdir()
        (instance_dir / "server.properties").write_text(
            "enable-rcon=true\nrcon.port=25575\nrcon.password=secret\n",
            encoding="utf-8",
        )

        check = make_minecraft_readiness_check(instance_dir)
        with patch("core.minecraft_readiness.MCRcon", side_effect=OSError("conn fail")):
            result = await check()
        assert result is False

    @pytest.mark.asyncio
    async def test_rcon_disabled_falls_back_to_log(self, tmp_path):
        from core.minecraft_readiness import make_minecraft_readiness_check

        instance_dir = tmp_path / "server"
        instance_dir.mkdir()
        (instance_dir / "server.properties").write_text(
            "enable-rcon=false\n", encoding="utf-8"
        )
        log_dir = instance_dir / "logs"
        log_dir.mkdir()
        (log_dir / "latest.log").write_text(
            '[12:00:00] [Server thread/INFO]: Done (5.234s)! For help, type "help"\n',
            encoding="utf-8",
        )

        check = make_minecraft_readiness_check(instance_dir)
        result = await check()
        assert result is True

    @pytest.mark.asyncio
    async def test_no_rcon_no_log_returns_false(self, tmp_path):
        from core.minecraft_readiness import make_minecraft_readiness_check

        instance_dir = tmp_path / "server"
        instance_dir.mkdir()
        (instance_dir / "server.properties").write_text(
            "enable-rcon=false\n", encoding="utf-8"
        )

        check = make_minecraft_readiness_check(instance_dir)
        result = await check()
        assert result is False

    @pytest.mark.asyncio
    async def test_log_not_ready_yet(self, tmp_path):
        from core.minecraft_readiness import make_minecraft_readiness_check

        instance_dir = tmp_path / "server"
        instance_dir.mkdir()
        (instance_dir / "server.properties").write_text(
            "enable-rcon=false\n", encoding="utf-8"
        )
        log_dir = instance_dir / "logs"
        log_dir.mkdir()
        (log_dir / "latest.log").write_text(
            "[12:00:00] [Server thread/INFO]: Starting server...\n",
            encoding="utf-8",
        )

        check = make_minecraft_readiness_check(instance_dir)
        result = await check()
        assert result is False

    @pytest.mark.asyncio
    async def test_rcon_without_password_skips_rcon(self, tmp_path):
        from core.minecraft_readiness import make_minecraft_readiness_check

        instance_dir = tmp_path / "server"
        instance_dir.mkdir()
        (instance_dir / "server.properties").write_text(
            "enable-rcon=true\nrcon.port=25575\nrcon.password=\n",
            encoding="utf-8",
        )

        check = make_minecraft_readiness_check(instance_dir)
        result = await check()
        assert result is False

    @pytest.mark.asyncio
    async def test_rcon_enabled_password_not_set_falls_back(self, tmp_path):
        from core.minecraft_readiness import make_minecraft_readiness_check

        instance_dir = tmp_path / "server"
        instance_dir.mkdir()
        (instance_dir / "server.properties").write_text(
            "enable-rcon=true\nrcon.port=25575\n", encoding="utf-8"
        )

        check = make_minecraft_readiness_check(instance_dir)
        result = await check()
        assert result is False
