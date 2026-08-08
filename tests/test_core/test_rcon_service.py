import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture(autouse=True)
def _mock_mcrcon():
    mcrcon_mock = MagicMock()
    mcrcon_mock.MCRconException = type("MCRconException", (Exception,), {})
    with patch.dict("sys.modules", {"mcrcon": mcrcon_mock}):
        yield


@pytest.fixture
def rcon():
    from core.api.services.rcon import RconService

    svc = RconService()
    svc.configure("localhost", 25575, "test_pass")
    return svc


class TestRconServiceConfigure:
    def test_default_host_port(self):
        from core.api.services.rcon import RconService

        svc = RconService()
        assert svc.host == "localhost"
        assert svc.port == 25575
        assert svc.connected is False

    def test_configure_updates_values(self, rcon):
        assert rcon.host == "localhost"
        assert rcon.port == 25575

    def test_reconfigure(self, rcon):
        rcon.configure("10.0.0.1", 12345, "new_pass")
        assert rcon.host == "10.0.0.1"
        assert rcon.port == 12345


class TestRconServiceConnect:
    @pytest.mark.asyncio
    async def test_connect_success(self, rcon):
        mock_conn = MagicMock()
        with patch("core.api.services.rcon.MCRcon", return_value=mock_conn):
            result = await rcon.connect()
        assert result is True
        assert rcon.connected is True

    @pytest.mark.asyncio
    async def test_connect_failure(self, rcon):
        with patch("core.api.services.rcon.MCRcon", side_effect=OSError("conn failed")):
            result = await rcon.connect()
        assert result is False
        assert rcon.connected is False

    @pytest.mark.asyncio
    async def test_reconnect_disconnects_existing(self, rcon):
        mock_conn = MagicMock()
        with patch("core.api.services.rcon.MCRcon", return_value=mock_conn):
            await rcon.connect()
            mock_conn2 = MagicMock()
            with patch("core.api.services.rcon.MCRcon", return_value=mock_conn2):
                result = await rcon.connect()
        assert result is True
        assert mock_conn.disconnect.called


class TestRconServiceDisconnect:
    @pytest.mark.asyncio
    async def test_disconnect(self, rcon):
        mock_conn = MagicMock()
        with patch("core.api.services.rcon.MCRcon", return_value=mock_conn):
            await rcon.connect()
        assert rcon.connected is True
        await rcon.disconnect()
        assert rcon.connected is False

    @pytest.mark.asyncio
    async def test_disconnect_when_not_connected(self, rcon):
        await rcon.disconnect()
        assert rcon.connected is False

    @pytest.mark.asyncio
    async def test_disconnect_handles_error(self, rcon):
        mock_conn = MagicMock()
        mock_conn.disconnect.side_effect = OSError("disconnect error")
        with patch("core.api.services.rcon.MCRcon", return_value=mock_conn):
            await rcon.connect()
        await rcon.disconnect()
        assert rcon.connected is False


class TestRconServiceCommand:
    @pytest.mark.asyncio
    async def test_command_not_connected(self, rcon):
        with pytest.raises(ConnectionError, match="Not connected"):
            await rcon.command("list")

    @pytest.mark.asyncio
    async def test_command_success(self, rcon):
        mock_conn = MagicMock()
        mock_conn.command.return_value = "There are 1/20 players online"
        with patch("core.api.services.rcon.MCRcon", return_value=mock_conn):
            await rcon.connect()
        response = await rcon.command("list")
        assert "players" in response
        assert rcon.connected is True

    @pytest.mark.asyncio
    async def test_command_failure(self, rcon):
        mock_conn = MagicMock()
        mock_conn.command.side_effect = OSError("cmd failed")
        with patch("core.api.services.rcon.MCRcon", return_value=mock_conn):
            await rcon.connect()
        with pytest.raises(ConnectionError, match="RCON command failed"):
            await rcon.command("list")
        assert rcon.connected is False

    @pytest.mark.asyncio
    async def test_command_returns_empty_string(self, rcon):
        mock_conn = MagicMock()
        mock_conn.command.return_value = None
        with patch("core.api.services.rcon.MCRcon", return_value=mock_conn):
            await rcon.connect()
        response = await rcon.command("say hi")
        assert response == ""


class TestRconServiceSingleton:
    def test_get_rcon_service(self):
        from core.api.services.rcon import get_rcon_service

        svc1 = get_rcon_service()
        svc2 = get_rcon_service()
        assert svc1 is svc2
