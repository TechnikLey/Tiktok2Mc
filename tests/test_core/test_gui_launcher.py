"""Tests for GUI offline-first startup and on-demand API control.

These tests verify that:
1. gui.py can start without an API server running
2. The LauncherAPI correctly starts/stops the API server
3. Action blocking works when API is offline
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

# Mock webview and logging before importing gui.py to prevent file I/O
sys.modules["webview"] = MagicMock()
_core_logger_original = sys.modules.get("core.logger")
sys.modules["core.logger"] = MagicMock()
sys.modules["core.logger"].initialize_logging = MagicMock(return_value=MagicMock())
sys.modules["core.logger"].install_global_exception_hook = MagicMock()
sys.modules["core.logger"].start_heartbeat = MagicMock(return_value=MagicMock())
sys.modules["core.logger"].handle_unhandled_exception = MagicMock()

from python.gui import (  # noqa: E402
    LauncherAPI,
    _api_ready,
    _clear_shutdown_marker,
    _shutdown_pending,
    _spawn_update_splash,
    _write_shutdown_marker,
)


@pytest.fixture(scope="module", autouse=True)
def _restore_core_logger():
    yield
    if _core_logger_original is not None:
        sys.modules["core.logger"] = _core_logger_original
    else:
        sys.modules.pop("core.logger", None)


class TestApiReady:
    """Tests for the _api_ready health check."""

    def test_api_ready_when_health_endpoint_responds(self, monkeypatch):
        mock_resp = MagicMock()
        mock_resp.status = 200
        # urlopen is used as a context manager
        mock_cm = MagicMock(
            __enter__=MagicMock(return_value=mock_resp),
            __exit__=MagicMock(return_value=False),
        )
        monkeypatch.setattr("urllib.request.urlopen", MagicMock(return_value=mock_cm))
        assert _api_ready(timeout=1.0) is True

    def test_api_ready_false_when_connection_fails(self, monkeypatch):
        import urllib.request

        monkeypatch.setattr(
            urllib.request,
            "urlopen",
            MagicMock(side_effect=urllib.error.URLError("Connection refused")),
        )
        assert _api_ready(timeout=0.1) is False

    def test_api_ready_false_on_timeout(self, monkeypatch):
        import urllib.request

        monkeypatch.setattr(
            urllib.request, "urlopen", MagicMock(side_effect=TimeoutError())
        )
        assert _api_ready(timeout=0.1) is False


class TestLauncherAPIStatus:
    """Tests for LauncherAPI.get_api_status."""

    def test_status_offline_when_nothing_running(self, monkeypatch):
        monkeypatch.setattr("python.gui._api_ready", lambda **kw: False)
        api = LauncherAPI()
        assert api.get_api_status() == "offline"

    def test_status_running_when_api_responds(self, monkeypatch):
        monkeypatch.setattr("python.gui._api_ready", lambda **kw: True)
        api = LauncherAPI()
        assert api.get_api_status() == "running"

    def test_status_starting_when_system_process_alive(self, monkeypatch):
        monkeypatch.setattr("python.gui._api_ready", lambda **kw: False)
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        monkeypatch.setattr("python.gui._full_system_proc", mock_proc)
        api = LauncherAPI()
        assert api.get_api_status() == "starting"


class TestLauncherAPIStartSystem:
    """Tests for LauncherAPI.start_system."""

    def test_returns_already_running_when_system_running(self, monkeypatch):
        monkeypatch.setattr("python.gui._full_system_proc", MagicMock())
        api = LauncherAPI()
        assert api.start_system() == "already_running"

    def test_returns_missing_when_start_exe_not_found(self, monkeypatch, tmp_path):
        fake_exe = tmp_path / "nonexistent.bin"
        monkeypatch.setattr("python.gui.START_EXE", fake_exe)
        monkeypatch.setattr("python.gui._full_system_proc", None)
        api = LauncherAPI()
        result = api.start_system()
        assert result.startswith("missing:")

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only CREATE_NO_WINDOW")
    def test_starts_system_process(self, monkeypatch, tmp_path):
        fake_exe = tmp_path / "start.exe"
        fake_exe.write_text("")
        monkeypatch.setattr("python.gui.START_EXE", fake_exe)
        monkeypatch.setattr("python.gui._full_system_proc", None)
        monkeypatch.setattr("python.gui.IS_WINDOWS", True)

        mock_popen = MagicMock()
        mock_popen.return_value.pid = 67890
        monkeypatch.setattr("subprocess.Popen", mock_popen)

        api = LauncherAPI()
        result = api.start_system()
        assert result == "started"
        mock_popen.assert_called_once()

    @pytest.mark.skipif(sys.platform != "win32", reason="needs_password guard on Linux")
    def test_returns_error_on_process_failure(self, monkeypatch, tmp_path):
        fake_exe = tmp_path / "start.exe"
        fake_exe.write_text("")
        monkeypatch.setattr("python.gui.START_EXE", fake_exe)
        monkeypatch.setattr("python.gui._full_system_proc", None)
        monkeypatch.setattr("python.gui.IS_WINDOWS", True)

        monkeypatch.setattr(
            "subprocess.Popen", MagicMock(side_effect=OSError("Permission denied"))
        )

        api = LauncherAPI()
        result = api.start_system()
        assert result.startswith("error:")

    def test_returns_needs_password_on_linux_nonroot(self, monkeypatch, tmp_path):
        fake_exe = tmp_path / "start.exe"
        fake_exe.write_text("")
        monkeypatch.setattr("python.gui.START_EXE", fake_exe)
        monkeypatch.setattr("python.gui._full_system_proc", None)
        monkeypatch.setattr("python.gui.IS_WINDOWS", False)

        api = LauncherAPI()
        result = api.start_system()
        assert result == "needs_password"


class TestLauncherAPIStop:
    """Tests for LauncherAPI.stop_system."""

    def test_returns_not_running_when_no_process(self):
        api = LauncherAPI()
        assert api.stop_system() == "not_running"

    def test_stops_system_process(self, monkeypatch):
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        monkeypatch.setattr("python.gui._full_system_proc", mock_proc)
        monkeypatch.setattr("python.gui.IS_WINDOWS", True)
        monkeypatch.setattr("python.gui._write_shutdown_marker", lambda: None)

        mock_run = MagicMock()
        monkeypatch.setattr("subprocess.run", mock_run)

        api = LauncherAPI()
        assert api.stop_system() == "stopped"
        mock_run.assert_called_once()

    def test_stops_system_process_on_linux(self, monkeypatch):
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        monkeypatch.setattr("python.gui._full_system_proc", mock_proc)
        monkeypatch.setattr("python.gui.IS_WINDOWS", False)
        monkeypatch.setattr("python.gui._write_shutdown_marker", lambda: None)

        api = LauncherAPI()
        result = api.stop_system()
        assert result == "stopped"
        mock_proc.terminate.assert_called_once()

    def test_stop_system_writes_marker(self, monkeypatch):
        marker_written = []
        monkeypatch.setattr(
            "python.gui._write_shutdown_marker", lambda: marker_written.append(True)
        )
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        monkeypatch.setattr("python.gui._full_system_proc", mock_proc)
        monkeypatch.setattr("python.gui.IS_WINDOWS", True)
        monkeypatch.setattr("subprocess.run", MagicMock())

        api = LauncherAPI()
        api.stop_system()
        assert len(marker_written) == 1


class TestLauncherAPICloseFlow:
    """Tests for the unsaved-changes close flow (backward compatibility)."""

    def test_approve_close_sets_flag(self):
        api = LauncherAPI()
        api.approve_close()
        assert api._approved is True

    def test_close_requested_initially_false(self):
        api = LauncherAPI()
        assert api.close_requested() is False

    def test_reset_close_request_clears_flag(self):
        api = LauncherAPI()
        api._close_requested = True
        api.reset_close_request()
        assert api.close_requested() is False

    def test_close_for_update_spawns_splash_and_destroys_window(self, monkeypatch):
        spawn_calls = []

        def fake_spawn(lang):
            spawn_calls.append(lang)
            return True

        mock_window = MagicMock()
        monkeypatch.setattr("python.gui._spawn_update_splash", fake_spawn)
        monkeypatch.setattr("python.gui._window", mock_window)

        api = LauncherAPI()
        assert api.close_for_update() == "closing"
        assert spawn_calls == ["en"]
        mock_window.destroy.assert_called_once()

    def test_close_for_update_passes_german_lang(self, monkeypatch):
        spawn_calls = []

        def fake_spawn(lang):
            spawn_calls.append(lang)
            return True

        monkeypatch.setattr("python.gui._spawn_update_splash", fake_spawn)
        monkeypatch.setattr("python.gui._window", None)

        api = LauncherAPI()
        assert api.close_for_update("de") == "closing"
        assert spawn_calls == ["de"]

    def test_close_for_update_without_window(self, monkeypatch):
        monkeypatch.setattr("python.gui._spawn_update_splash", lambda lang: True)
        monkeypatch.setattr("python.gui._window", None)

        api = LauncherAPI()
        assert api.close_for_update() == "closing"


class TestSpawnUpdateSplash:
    """Tests for the update splash spawn helper."""

    def test_returns_false_when_binary_missing(self, monkeypatch, tmp_path):
        monkeypatch.setattr("python.gui.BASE_DIR", tmp_path)
        monkeypatch.setattr("python.gui.ROOT_DIR", tmp_path)
        assert _spawn_update_splash("en") is False

    def test_returns_false_on_copy_error(self, monkeypatch, tmp_path):
        from python.gui import SUFFIX

        (tmp_path / f"update_progress{SUFFIX}").write_text("")
        monkeypatch.setattr("python.gui.BASE_DIR", tmp_path)
        monkeypatch.setattr("python.gui.ROOT_DIR", tmp_path)
        monkeypatch.setattr(
            "python.gui.shutil.copy2", MagicMock(side_effect=OSError("no space"))
        )
        assert _spawn_update_splash("en") is False

    def test_spawns_copy_on_windows(self, monkeypatch, tmp_path):
        import subprocess as _subprocess

        from python.gui import SUFFIX

        (tmp_path / f"update_progress{SUFFIX}").write_text("")
        monkeypatch.setattr("python.gui.BASE_DIR", tmp_path)
        monkeypatch.setattr("python.gui.ROOT_DIR", tmp_path)
        monkeypatch.setattr("python.gui.IS_WINDOWS", True)
        # DETACHED_PROCESS / CREATE_NEW_PROCESS_GROUP are Windows-only constants
        monkeypatch.setattr(_subprocess, "DETACHED_PROCESS", 0x00000008, raising=False)
        monkeypatch.setattr(
            _subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200, raising=False
        )
        mock_popen = MagicMock()
        monkeypatch.setattr("python.gui.subprocess.Popen", mock_popen)

        assert _spawn_update_splash("de") is True
        mock_popen.assert_called_once()
        args, kwargs = mock_popen.call_args

        copied = tmp_path / "data" / "cache" / f"update_progress{SUFFIX}"
        assert args[0] == [str(copied), "--lang", "de"]
        assert kwargs["creationflags"] is not None

    def test_spawns_copy_on_linux(self, monkeypatch, tmp_path):
        from python.gui import SUFFIX

        (tmp_path / f"update_progress{SUFFIX}").write_text("")
        monkeypatch.setattr("python.gui.BASE_DIR", tmp_path)
        monkeypatch.setattr("python.gui.ROOT_DIR", tmp_path)
        monkeypatch.setattr("python.gui.IS_WINDOWS", False)
        mock_popen = MagicMock()
        monkeypatch.setattr("python.gui.subprocess.Popen", mock_popen)

        assert _spawn_update_splash("en") is True
        _, kwargs = mock_popen.call_args
        assert "start_new_session" in kwargs


class TestGuiAlreadyRunning:
    """Tests for the single-instance guard."""

    def test_no_lockfile_means_not_running(self, monkeypatch, tmp_path):
        from python.gui import _gui_already_running

        monkeypatch.setattr("python.gui.GUI_LOCKFILE", tmp_path / "nonexistent.lock")
        assert _gui_already_running() is False

    def test_lockfile_with_own_pid_is_not_running(self, monkeypatch, tmp_path):
        from python.gui import _gui_already_running

        lockfile = tmp_path / "gui.lock"
        import os

        lockfile.write_text(str(os.getpid()))
        monkeypatch.setattr("python.gui.GUI_LOCKFILE", lockfile)
        assert _gui_already_running() is False

    def test_main_exits_when_another_instance_running(self, monkeypatch):
        """main() should exit immediately if another GUI is already running."""
        opened_urls = []

        def mock_open(url, **kwargs):
            opened_urls.append(url)

        monkeypatch.setattr("python.gui._open_window", mock_open)
        monkeypatch.setattr("python.gui._gui_already_running", lambda: True)
        monkeypatch.setattr("sys.argv", ["gui.py"])

        from python.gui import main

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0
        assert len(opened_urls) == 0


class TestGuiStartup:
    """Tests verifying GUI can start without API dependency."""

    def test_gui_py_imports_without_api_dependency(self):
        """Verify gui.py does not crash on import even if API is offline."""
        # The import at module level already happened in test setup
        # If we got here, the module imported successfully without API
        assert "python.gui" in sys.modules

    def test_launcher_html_exists(self):
        from python.gui import LAUNCHER_HTML

        assert LAUNCHER_HTML.exists(), f"Launcher HTML not found at {LAUNCHER_HTML}"

    def test_main_opens_launcher_when_api_offline(self, monkeypatch):
        """When API is offline, main() should call _open_window with launcher.html."""
        opened_urls = []

        def mock_open(url, **kwargs):
            opened_urls.append(url)

        monkeypatch.setattr("python.gui._open_window", mock_open)
        monkeypatch.setattr("python.gui._api_ready", lambda **kw: False)
        monkeypatch.setattr("python.gui._gui_already_running", lambda: False)
        monkeypatch.setattr("python.gui._check_xcb_cursor", lambda: True)
        monkeypatch.setattr("sys.argv", ["gui.py"])

        from python.gui import main

        main()

        assert len(opened_urls) == 1
        assert "launcher.html" in opened_urls[0]

    def test_main_opens_dashboard_when_api_online(self, monkeypatch):
        """When API is already running, main() should open the dashboard directly."""
        opened_urls = []

        def mock_open(url, **kwargs):
            opened_urls.append(url)

        monkeypatch.setattr("python.gui._open_window", mock_open)
        monkeypatch.setattr("python.gui._api_ready", lambda **kw: True)
        monkeypatch.setattr("python.gui._gui_already_running", lambda: False)
        monkeypatch.setattr("python.gui._check_xcb_cursor", lambda: True)
        monkeypatch.setattr("sys.argv", ["gui.py"])

        from python.gui import main

        main()

        assert len(opened_urls) == 1
        assert "/gui/index.html" in opened_urls[0]


class TestShutdownMarker:
    """Tests for the shutdown-pending marker file mechanism."""

    def test_write_creates_marker(self, monkeypatch, tmp_path):
        marker = tmp_path / "shutdown_pending"
        monkeypatch.setattr("python.gui.SHUTDOWN_PENDING", marker)
        _write_shutdown_marker()
        assert marker.exists()
        marker.unlink()

    def test_write_contains_pid(self, monkeypatch, tmp_path):
        import os

        marker = tmp_path / "shutdown_pending"
        monkeypatch.setattr("python.gui.SHUTDOWN_PENDING", marker)
        _write_shutdown_marker()
        assert marker.read_text() == str(os.getpid())
        marker.unlink()

    def test_clear_removes_marker(self, monkeypatch, tmp_path):
        marker = tmp_path / "shutdown_pending"
        marker.write_text("12345")
        monkeypatch.setattr("python.gui.SHUTDOWN_PENDING", marker)
        _clear_shutdown_marker()
        assert not marker.exists()

    def test_clear_noop_when_no_marker(self, monkeypatch, tmp_path):
        marker = tmp_path / "nonexistent"
        monkeypatch.setattr("python.gui.SHUTDOWN_PENDING", marker)
        _clear_shutdown_marker()

    def test_pending_returns_false_when_no_marker(self, monkeypatch, tmp_path):
        marker = tmp_path / "nonexistent"
        monkeypatch.setattr("python.gui.SHUTDOWN_PENDING", marker)
        assert _shutdown_pending() is False

    def test_pending_returns_true_when_pid_alive(self, monkeypatch, tmp_path):
        import os

        marker = tmp_path / "shutdown_pending"
        marker.write_text(str(os.getpid()))
        monkeypatch.setattr("python.gui.SHUTDOWN_PENDING", marker)
        assert _shutdown_pending() is True
        marker.unlink()

    def test_pending_returns_false_when_pid_dead(self, monkeypatch, tmp_path):
        marker = tmp_path / "shutdown_pending"
        marker.write_text("9999999")
        monkeypatch.setattr("python.gui.SHUTDOWN_PENDING", marker)
        assert _shutdown_pending() is False

    def test_main_opens_launcher_when_marker_exists(self, monkeypatch, tmp_path):
        opened_urls = []

        def mock_open(url, **kwargs):
            opened_urls.append(url)

        marker = tmp_path / "shutdown_pending"
        import os

        marker.write_text(str(os.getpid()))
        monkeypatch.setattr("python.gui.SHUTDOWN_PENDING", marker)
        monkeypatch.setattr("python.gui._open_window", mock_open)
        monkeypatch.setattr("python.gui._api_ready", lambda **kw: True)
        monkeypatch.setattr("python.gui._gui_already_running", lambda: False)
        monkeypatch.setattr("python.gui._check_xcb_cursor", lambda: True)
        monkeypatch.setattr("sys.argv", ["gui.py"])

        from python.gui import main

        main()

        assert len(opened_urls) == 1
        assert "launcher.html" in opened_urls[0]
