import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.port_scanner import (
    RUNTIME_FILE,
    PortCheckResult,
    PortPolicy,
    build_resolved_map,
    clear_runtime_file,
    find_available_port,
    get_resolved_port,
    is_port_in_use,
    persist_to_config,
    ports_to_env,
    scan_bind_ports,
    write_runtime_file,
)


class TestPortPolicy:
    def test_from_config_defaults(self):
        p = PortPolicy.from_config({})
        assert p.auto_resolve is True
        assert p.session_only is True
        assert p.max_offset == 10

    def test_from_config_overrides(self):
        p = PortPolicy.from_config(
            {
                "port_policy": {
                    "auto_resolve": False,
                    "session_only": False,
                    "max_offset": 5,
                }
            }
        )
        assert p.auto_resolve is False
        assert p.session_only is False
        assert p.max_offset == 5

    def test_from_config_partial(self):
        p = PortPolicy.from_config({"port_policy": {"auto_resolve": False}})
        assert p.auto_resolve is False
        assert p.session_only is True
        assert p.max_offset == 10


class TestIsPortInUse:
    @patch("core.port_scanner.socket.create_connection")
    def test_port_in_use(self, mock_conn):
        mock_conn.return_value = MagicMock()
        assert is_port_in_use("127.0.0.1", 8000) is True
        mock_conn.assert_called_once_with(("127.0.0.1", 8000), timeout=1)

    @patch("core.port_scanner.socket.create_connection")
    def test_port_free(self, mock_conn):
        mock_conn.side_effect = ConnectionRefusedError
        assert is_port_in_use("127.0.0.1", 8000) is False


class TestFindAvailablePort:
    @patch("core.port_scanner.is_port_in_use")
    def test_preferred_free(self, mock_check):
        mock_check.return_value = False
        assert find_available_port("127.0.0.1", 8000, 10) == 8000
        mock_check.assert_called_once_with("127.0.0.1", 8000)

    @patch("core.port_scanner.is_port_in_use")
    def test_preferred_taken(self, mock_check):
        mock_check.side_effect = lambda _h, p: p == 8000
        assert find_available_port("127.0.0.1", 8000, 10) == 8001

    @patch("core.port_scanner.is_port_in_use")
    def test_negative_one_infinite(self, mock_check):
        mock_check.side_effect = lambda _h, p: p < 8100
        assert find_available_port("127.0.0.1", 8000, -1) == 8100

    @patch("core.port_scanner.is_port_in_use")
    def test_all_taken(self, mock_check):
        mock_check.return_value = True
        assert find_available_port("127.0.0.1", 8000, 3) == 8003

    @patch("core.port_scanner.is_port_in_use")
    def test_skip_used_ports(self, mock_check):
        used = {8000, 8001, 8003}
        mock_check.side_effect = lambda _h, p: p in used
        assert find_available_port("127.0.0.1", 8000, 10) == 8002


class TestScanBindPorts:
    @patch("core.port_scanner.is_port_in_use")
    def test_all_free(self, mock_check):
        mock_check.return_value = False
        results = scan_bind_ports("127.0.0.1", PortPolicy())
        assert len(results) == 3
        for r in results:
            assert r.in_use is False
            assert r.resolved_port is None

    @patch("core.port_scanner.is_port_in_use")
    def test_with_conflict_auto_resolve(self, mock_check):
        mock_check.side_effect = lambda _h, p: p == 29185
        results = scan_bind_ports("127.0.0.1", PortPolicy(auto_resolve=True))
        api_result = next(r for r in results if r.key == "api_port")
        assert api_result.in_use is True
        assert api_result.resolved_port is not None
        assert api_result.resolved_port != 29185

    @patch("core.port_scanner.is_port_in_use")
    def test_with_conflict_no_resolve(self, mock_check):
        mock_check.side_effect = lambda _h, p: p == 29185
        results = scan_bind_ports("127.0.0.1", PortPolicy(auto_resolve=False))
        api_result = next(r for r in results if r.key == "api_port")
        assert api_result.in_use is True
        assert api_result.resolved_port is None

    @patch("core.port_scanner.is_port_in_use")
    def test_custom_bind_ports(self, mock_check):
        mock_check.return_value = True
        custom_ports = [
            {
                "key": "test",
                "config_path": "test.port",
                "default": 9999,
                "desc": "test",
            },
        ]
        results = scan_bind_ports(
            "127.0.0.1", PortPolicy(auto_resolve=True), bind_ports=custom_ports
        )
        assert len(results) == 1
        assert results[0].key == "test"
        assert results[0].in_use is True
        assert results[0].resolved_port is not None


class TestBuildResolvedMap:
    def test_no_resolution_needed(self):
        results = [
            PortCheckResult(
                port=29185, key="api_port", description="API", in_use=False
            ),
            PortCheckResult(
                port=29188, key="webhook_port", description="Webhook", in_use=False
            ),
        ]
        m = build_resolved_map(results)
        assert m["api_port"] == 29185
        assert m["webhook_port"] == 29188

    def test_with_resolutions(self):
        results = [
            PortCheckResult(
                port=29185,
                key="api_port",
                description="API",
                in_use=True,
                resolved_port=29186,
            ),
            PortCheckResult(
                port=29188, key="webhook_port", description="Webhook", in_use=False
            ),
        ]
        m = build_resolved_map(results)
        assert m["api_port"] == 29186
        assert m["webhook_port"] == 29188


class TestRuntimeFile:
    def test_write_runtime_file(self, tmp_path):
        resolved = {"api_port": 29186, "webhook_port": 29188}
        write_runtime_file(resolved, tmp_path)
        f = tmp_path / RUNTIME_FILE
        assert f.exists()
        assert json.loads(f.read_text(encoding="utf-8")) == resolved

    def test_clear_runtime_file(self, tmp_path):
        f = tmp_path / RUNTIME_FILE
        f.write_text("{}", encoding="utf-8")
        clear_runtime_file(tmp_path)
        assert not f.exists()

    def test_clear_runtime_file_noop(self, tmp_path):
        clear_runtime_file(tmp_path)


class TestGetResolvedPort:
    def test_default(self):
        assert get_resolved_port("test", 8080) == 8080

    def test_env_var(self):
        with patch.dict(os.environ, {"RESOLVED_PORT_TEST": "9090"}, clear=True):
            assert get_resolved_port("test", 8080) == 9090

    def test_env_var_non_numeric(self):
        with patch.dict(os.environ, {"RESOLVED_PORT_TEST": "abc"}, clear=True):
            assert get_resolved_port("test", 8080) == 8080

    def test_runtime_file(self, tmp_path):
        resolved = {"test": 7070}
        write_runtime_file(resolved, tmp_path)
        assert get_resolved_port("test", 8080, tmp_path) == 7070

    def test_env_takes_precedence(self, tmp_path):
        write_runtime_file({"test": 7070}, tmp_path)
        with patch.dict(os.environ, {"RESOLVED_PORT_TEST": "6060"}, clear=True):
            assert get_resolved_port("test", 8080, tmp_path) == 6060


class TestPortsToEnv:
    def test_conversion(self):
        resolved = {"api_port": 29186, "webhook_port": 29188}
        env = ports_to_env(resolved)
        assert env == {
            "RESOLVED_PORT_API_PORT": "29186",
            "RESOLVED_PORT_WEBHOOK_PORT": "29188",
        }


class TestPersistToConfig:
    @patch("core.yaml_utils.load_yaml")
    @patch("core.yaml_utils.save_yaml")
    def test_persist_changed_ports(self, mock_save, mock_load):
        mock_load.return_value = {"minecraft_server_api": {"web_server_port": 29188}}
        resolved = {"webhook_port": 29189}
        persist_to_config(resolved, Path("/fake/config.yaml"))
        mock_save.assert_called_once()
        args = mock_save.call_args
        assert args[0][1]["minecraft_server_api"]["web_server_port"] == 29189

    @patch("core.yaml_utils.load_yaml")
    @patch("core.yaml_utils.save_yaml")
    def test_no_change_default_port(self, mock_save, mock_load):
        mock_load.return_value = {}
        resolved = {"webhook_port": 29188}
        persist_to_config(resolved, Path("/fake/config.yaml"))
        mock_save.assert_not_called()

    @patch("core.yaml_utils.load_yaml")
    @patch("core.yaml_utils.save_yaml")
    def test_creates_missing_section(self, mock_save, mock_load):
        mock_load.return_value = {}
        resolved = {"webhook_port": 29189}
        persist_to_config(resolved, Path("/fake/config.yaml"))
        mock_save.assert_called_once()
        args = mock_save.call_args
        assert args[0][1] == {"minecraft_server_api": {"web_server_port": 29189}}
