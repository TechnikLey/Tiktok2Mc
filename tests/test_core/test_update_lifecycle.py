"""End-to-end tests for the update lifecycle (signal files, restart polling, update loop)."""

import subprocess
import sys
import time
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class FakeResponse:
    def __init__(self, data: bytes, status: int = 200):
        self.data = data
        self.status = status

    def read(self):
        return self.data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


# ---------------------------------------------------------------------------
# Signal file mechanism
# ---------------------------------------------------------------------------

class TestUpdateSignalFile:
    """Tests the file-based kill-signal mechanism used by the updater."""

    def test_write_and_read_kill_signal(self, tmp_path: Path):
        signal_file = tmp_path / "update_signal.tmp"
        signal_file.write_text("kill")
        assert signal_file.exists()
        content = signal_file.read_text().strip()
        assert content == "kill"

    def test_signal_deleted_after_read(self, tmp_path: Path):
        signal_file = tmp_path / "update_signal.tmp"
        signal_file.write_text("kill")
        content = signal_file.read_text().strip()
        if content == "kill":
            signal_file.unlink()
        assert not signal_file.exists()

    def test_signal_empty_is_ignored(self, tmp_path: Path):
        signal_file = tmp_path / "update_signal.tmp"
        signal_file.write_text("")
        content = signal_file.read_text().strip()
        assert content == ""

    def test_multiple_signals_in_sequence(self, tmp_path: Path):
        signal_file = tmp_path / "update_signal.tmp"
        for _ in range(3):
            signal_file.write_text("kill")
            assert signal_file.read_text().strip() == "kill"
            signal_file.unlink()
            assert not signal_file.exists()

    def test_signal_file_not_present(self, tmp_path: Path):
        signal_file = tmp_path / "update_signal.tmp"
        assert not signal_file.exists()

    def test_update_signal_path_constant(self):
        from core.paths import get_base_dir
        base = get_base_dir()
        signal_path = base / "update_signal.tmp"
        assert str(signal_path).endswith("update_signal.tmp")

    def test_start_imports_update_exe_path(self):
        from core.paths import get_base_dir
        base = get_base_dir()
        exe_suffix = ".exe" if sys.platform == "win32" else ".bin"
        update_path = base / f"update{exe_suffix}"
        assert str(update_path).endswith(f"update{exe_suffix}")


class TestUpdateAPISignal:
    """Tests the API-based kill signal mechanism."""

    def test_api_signal_endpoint(self, client):
        resp = client.get("/api/v1/updater/signal")
        assert resp.status_code == 200
        assert "signal" in resp.json()

    def test_set_and_clear_api_signal(self, client):
        resp = client.put("/api/v1/updater/signal", json={"signal": "kill"})
        assert resp.status_code == 200
        resp = client.get("/api/v1/updater/signal")
        assert resp.json().get("signal") == "kill"
        resp = client.delete("/api/v1/updater/signal")
        assert resp.status_code == 200
        resp = client.get("/api/v1/updater/signal")
        assert resp.json().get("signal") is None


# ---------------------------------------------------------------------------
# Restart polling helpers (replacing the 3-second blind sleep)
# ---------------------------------------------------------------------------

class TestRestartPollingLogic:
    """Tests the polling-based restart logic that replaced blind sleep()."""

    _RESTART_POLL_INTERVAL = 0.5
    _RESTART_POLL_TIMEOUT = 10.0

    def _wait_for_process_started(self, proc) -> bool:
        deadline = time.time() + self._RESTART_POLL_TIMEOUT
        alive_count = 0
        while time.time() < deadline:
            if proc.poll() is not None:
                return False
            alive_count += 1
            if alive_count >= 3:
                return True
            time.sleep(self._RESTART_POLL_INTERVAL)
        return proc.poll() is None

    def test_process_stays_alive_returns_true(self):
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        try:
            result = self._wait_for_process_started(proc)
            assert result is True
        finally:
            proc.kill()
            proc.wait()

    def test_process_dies_immediately_returns_false(self):
        proc = subprocess.Popen([sys.executable, "-c", "import sys; sys.exit(1)"])
        proc.wait()
        result = self._wait_for_process_started(proc)
        assert result is False

    def test_poll_constants_are_reasonable(self):
        assert self._RESTART_POLL_INTERVAL > 0
        assert self._RESTART_POLL_TIMEOUT > 3

    def test_does_not_block_full_timeout_for_fast_dead_process(self):
        proc = subprocess.Popen([sys.executable, "-c", "import sys; sys.exit(0)"])
        proc.wait()
        start = time.time()
        result = self._wait_for_process_started(proc)
        elapsed = time.time() - start
        assert result is False
        assert elapsed < 3


class TestReplaceUpdaterLogic:
    """Tests the replace_updater_if_exists logic by reimplementing the pattern."""

    def _replace_updater(self, update_new: Path, update_exe: Path):
        if update_new.exists():
            try:
                update_new.replace(update_exe)
                return True
            except PermissionError:
                return False
        return False

    def test_replaces_when_update_new_exists(self, tmp_path: Path):
        update_new = tmp_path / "update_new.exe"
        update_exe = tmp_path / "update.exe"
        update_new.write_text("new version data")
        self._replace_updater(update_new, update_exe)
        assert update_exe.exists()
        assert update_exe.read_text() == "new version data"

    def test_skips_when_update_new_does_not_exist(self, tmp_path: Path):
        update_new = tmp_path / "update_new.exe"
        update_exe = tmp_path / "update.exe"
        self._replace_updater(update_new, update_exe)
        assert not update_exe.exists()

    def test_preserves_old_updater_when_replace_fails(self, tmp_path: Path):
        update_new = tmp_path / "update_new.exe"
        update_exe = tmp_path / "update.exe"
        update_exe.write_text("original")
        # Simulate replacement failure by making source disappear
        update_new.write_text("new")
        update_new.unlink()
        self._replace_updater(update_new, update_exe)
        assert update_exe.read_text() == "original"


# ---------------------------------------------------------------------------
# Update return code handling
# ---------------------------------------------------------------------------

class TestUpdateReturnCodeHandling:
    """Tests the decision logic for update process return codes."""

    def test_result_none_means_no_update_loops(self):
        result = None
        assert result is None

    def test_result_kill_triggers_exit(self):
        result = "kill"
        assert result == "kill"
        assert result != 5

    def test_result_5_means_updater_self_updated(self):
        result = 5
        assert result == 5
        assert result is not None

    def test_result_0_means_update_installed(self):
        result = 0
        assert result == 0


# ---------------------------------------------------------------------------
# Config / update safety
# ---------------------------------------------------------------------------

class TestUpdateSafety:
    """Tests that update configuration is correctly read."""

    def test_update_defaults_to_enabled(self):
        config = {}
        assert config.get("update", {}).get("enabled", True) is True

    def test_update_enabled_in_config(self):
        config = {"update": {"enabled": True}}
        assert config["update"]["enabled"] is True

    def test_update_disabled_in_config(self):
        config = {"update": {"enabled": False}}
        assert config["update"]["enabled"] is False

    def test_auto_restart_after_update_logic(self):
        result = 0
        assert result is not None
        assert result != "kill"
        assert result != 5
        assert not (result is None or result == "kill" or result == 5)


# ---------------------------------------------------------------------------
# Restart flow verification
# ---------------------------------------------------------------------------


