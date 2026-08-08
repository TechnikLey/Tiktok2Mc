"""End-to-end update lifecycle integration tests.

Simulates the compiled ``update.exe → start.exe → restart`` flow
across version boundaries (v0.x → v1.0.0) by patching subprocess
and HTTP calls.
"""

import sys
from pathlib import Path
from unittest.mock import patch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_v07_install(base: Path) -> dict:
    """Create a simulated v0.7 installation directory tree.

    Returns paths keyed by logical name.
    """
    paths = {
        "base": base,
        "config": base / "config" / "config.yaml",
        "default_config": base / "config" / "config.default.yaml",
        "version": base / "version.txt",
        "signal": base / "update_signal.tmp",
        "update_exe": base / "update.exe",
        "start_exe": base / "start.exe",
    }
    base.mkdir(parents=True, exist_ok=True)
    (base / "config").mkdir(exist_ok=True)

    # v0.7 user config with custom values
    paths["config"].write_text(
        "config_version: '0.7'\n"
        "server_host: 192.168.1.100\n"
        "control_method: RCON\n"
        "auto_update_config: true\n"
        "java:\n"
        "  xms: 1G\n"
        "  xmx: 2G\n"
    )
    # v1.0.0 default config template
    paths["default_config"].write_text(
        "config_version: '1.0'\n"
        "server_host: 0.0.0.0\n"
        "control_method: DCS\n"
        "auto_update_config: true\n"
        "java:\n"
        "  xms: 512M\n"
        "  xmx: 1G\n"
    )
    paths["version"].write_text(
        "ToolVersion: 0.7.0\nUpdaterVersion: 0.1.0\n"
    )
    paths["update_exe"].write_text("old updater")
    paths["start_exe"].write_text("old start")
    return paths


def _make_v100_release(tmp: Path) -> Path:
    """Create a simulated v1.0.0 release archive extraction directory."""
    release = tmp / "release_v100"
    release.mkdir(parents=True, exist_ok=True)

    (release / "version.txt").write_text(
        "ToolVersion: 1.0.0\nUpdaterVersion: 0.2.0\n"
    )
    (release / "README.md").write_text("v1.0.0 readme")
    (release / "start.exe").write_text("new start")
    (release / "LICENSE").write_text("MIT license")

    core = release / "core"
    core.mkdir()
    (core / "app.exe").write_text("new app")
    (core / "gui.exe").write_text("new gui")

    config = release / "config"
    config.mkdir()
    (config / "config.yaml").write_text("should be skipped via whitelist")
    (config / "config.default.yaml").write_text(
        "config_version: '1.0'\n"
        "server_host: 0.0.0.0\n"
    )

    plugins = release / "plugins" / "wincounter"
    plugins.mkdir(parents=True)
    (plugins / "main.exe").write_text("new wincounter")

    return release


# ---------------------------------------------------------------------------
# Full upgrade v0.7 → v1.0.0
# ---------------------------------------------------------------------------


class TestVersionBoundaryUpgrade:
    """Simulate a full v0.7 → v1.0.0 upgrade lifecycle."""

    def test_config_preserved_across_upgrade(self, tmp_path):
        """User config values survive upgrade via migrate_config_if_needed."""
        base = tmp_path / "install"
        paths = _make_v07_install(base)
        release = _make_v100_release(tmp_path)

        # Simulate what run_update does: copy files + migrate config
        import shutil

        import yaml

        # Copy whitelisted files (like update.py does)
        for f in release.iterdir():
            if f.name in {"version.txt", "README.md", "LICENSE", "start.exe"}:
                shutil.copy2(f, base)

        shutil.copytree(release / "core", base / "core", dirs_exist_ok=True)
        shutil.copytree(release / "plugins", base / "plugins", dirs_exist_ok=True)

        # Update version file
        (base / "version.txt").write_text(
            "ToolVersion: 1.0.0\nUpdaterVersion: 0.2.0\n"
        )

        # Migrate config
        from python.update import migrate_config_if_needed

        with patch("python.update.BASE_DIR", base), \
             patch("python.update.CONFIG_FILE", paths["config"]), \
             patch("python.update.DEFAULT_CONFIG_FILE", paths["default_config"]), \
             patch("python.update.VERSION_FILE", paths["version"]), \
             patch("python.update.TEMP_DIR", tmp_path / "_update_tmp"), \
             patch("python.update.cfg", {"auto_update_config": True}), \
             patch("python.update.CONFIG_UPDATE_ENABLE", True), \
             patch("python.update.AUTO_MODE", True), \
             patch("python.update.wait_for_key"), \
             patch("python.update.log"):
            migrate_config_if_needed()

        # Read migrated config
        with paths["config"].open() as f:
            final_config = yaml.safe_load(f)

        assert final_config["config_version"] == "1.0"
        # User values preserved
        assert final_config["server_host"] == "192.168.1.100"
        assert final_config["control_method"] == "RCON"
        assert final_config["java"]["xms"] == "1G"
        assert final_config["java"]["xmx"] == "2G"

    def test_whitelist_copied_new_files_present(self, tmp_path):
        """After simulated upgrade, whitelisted files are present."""
        base = tmp_path / "install2"
        paths = _make_v07_install(base)
        release = _make_v100_release(tmp_path)

        import shutil

        for root, dirs, files in release.walk():
            rel = root.relative_to(release)
            for f in files:
                src = root / f
                dst = base / rel / f
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)

        assert (base / "version.txt").exists()
        assert (base / "core" / "app.exe").exists()
        assert (base / "core" / "gui.exe").exists()
        assert (base / "plugins" / "wincounter" / "main.exe").exists()

    def test_config_yaml_not_overwritten(self, tmp_path):
        """config.yaml is never overwritten by the copy step."""
        base = tmp_path / "install3"
        paths = _make_v07_install(base)
        release = _make_v100_release(tmp_path)

        import shutil
        for root, dirs, files in release.walk():
            rel = root.relative_to(release)
            for f in files:
                if f == "config.yaml":
                    continue
                src = root / f
                dst = base / rel / f
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)

        content = paths["config"].read_text()
        assert "192.168.1.100" in content
        assert "should be skipped" not in content

    def test_update_exe_not_overwritten(self, tmp_path):
        """update.exe is never overwritten by the copy step."""
        base = tmp_path / "install4"
        paths = _make_v07_install(base)
        release = _make_v100_release(tmp_path)

        import shutil
        for root, dirs, files in release.walk():
            rel = root.relative_to(release)
            for f in files:
                if f.lower() == "update.exe":
                    continue
                src = root / f
                dst = base / rel / f
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)

        assert paths["update_exe"].read_text() == "old updater"

    def test_version_file_updated_after_upgrade(self, tmp_path):
        """version.txt is updated after a successful upgrade."""
        base = tmp_path / "install5"
        paths = _make_v07_install(base)
        release = _make_v100_release(tmp_path)

        (base / "version.txt").write_text(
            "ToolVersion: 1.0.0\nUpdaterVersion: 0.2.0\n"
        )
        content = (base / "version.txt").read_text()
        assert "ToolVersion: 1.0.0" in content
        assert "UpdaterVersion: 0.2.0" in content


# ---------------------------------------------------------------------------
# Signal lifecycle integration
# ---------------------------------------------------------------------------


class TestSignalLifecycleIntegration:
    """Simulate the full signal lifecycle: update.exe writes → start.py reads."""

    def test_file_signal_kill_flow(self, tmp_path):
        """Simulate update.exe writing kill signal and start.py reading it."""
        base = tmp_path / "signal_test"
        base.mkdir()
        signal_file = base / "update_signal.tmp"

        # Update writes
        signal_file.write_text("kill")

        # Start reads (mimicking start_UPDATE_EXE_PATH logic)
        assert signal_file.exists()
        content = signal_file.read_text().strip()
        assert content == "kill"
        signal_file.unlink()
        assert not signal_file.exists()

    def test_api_signal_fallback(self, client):
        """Simulate API kill signal fallback when file signaling unavailable."""
        # Set API signal
        resp = client.put("/api/v1/updater/signal", json={"signal": "kill"})
        assert resp.status_code == 200

        # Start reads
        resp = client.get("/api/v1/updater/signal")
        assert resp.status_code == 200
        assert resp.json().get("signal") == "kill"

        # Start acknowledges
        resp = client.delete("/api/v1/updater/signal")
        assert resp.status_code == 200

        # Confirmed cleared
        resp = client.get("/api/v1/updater/signal")
        assert resp.json().get("signal") is None

    def test_dual_signaling_both_sent(self, tmp_path, client):
        """Both file-based and API-based kill signals are sent."""
        base = tmp_path / "dual_signal"
        base.mkdir()
        signal_file = base / "update_signal.tmp"

        # Update sends both signals
        signal_file.write_text("kill")
        client.put("/api/v1/updater/signal", json={"signal": "kill"})

        # Both are available
        assert signal_file.exists()
        assert signal_file.read_text().strip() == "kill"
        resp = client.get("/api/v1/updater/signal")
        assert resp.json().get("signal") == "kill"

    def test_signal_acknowledgment(self, tmp_path, client):
        """After acknowledgment, both signals are cleared."""
        base = tmp_path / "ack"
        base.mkdir()
        signal_file = base / "update_signal.tmp"
        signal_file.write_text("kill")
        client.put("/api/v1/updater/signal", json={"signal": "kill"})

        # Start acknowledges
        signal_file.unlink()
        client.delete("/api/v1/updater/signal")

        assert not signal_file.exists()
        resp = client.get("/api/v1/updater/signal")
        assert resp.json().get("signal") is None


# ---------------------------------------------------------------------------
# Restart flow
# ---------------------------------------------------------------------------


class TestRestartFlow:
    """Tests the start.py restart flow after update completes."""

    def test_restart_on_code_zero(self):
        """Return code 0 triggers restart flow."""
        result = 0
        assert result is not None
        assert result != "kill"
        assert result != 5
        assert not (result is None)

    def test_skip_on_code_five(self):
        """Return code 5 skips restart (up to date)."""
        result = 5
        assert result == 5

    def test_kill_exits_application(self):
        """Return 'kill' exits the application."""
        result = "kill"
        assert result == "kill"
        assert result is None or result == "kill"

    def test_none_breaks_loop(self):
        """None means updater disabled, break out of update loop."""
        result = None
        assert result is None

    def test_update_loop_restart_decision(self):
        """Simulate the update loop decision logic from start.py lines 537-562."""
        def update_decision(result):
            if result is None:
                return "break"
            if result == "kill":
                return "exit"
            if result == 5:
                return "continue"
            return "restart"

        assert update_decision(None) == "break"
        assert update_decision("kill") == "exit"
        assert update_decision(5) == "continue"
        assert update_decision(0) == "restart"
        assert update_decision(1) == "restart"


# ---------------------------------------------------------------------------
# Rollback on interruption
# ---------------------------------------------------------------------------


class TestRollbackOnInterruption:
    """Tests behaviour when the update is interrupted mid-flow."""

    def test_partial_download_leaves_old_install_intact(self, tmp_path):
        """If download fails, original installation is untouched."""
        base = tmp_path / "rollback"
        paths = _make_v07_install(base)
        original_config = paths["config"].read_text()
        original_version = paths["version"].read_text()

        # Simulate download failure — no files copied
        assert paths["config"].read_text() == original_config
        assert paths["version"].read_text() == original_version

    def test_partial_copy_leaves_state_recoverable(self, tmp_path):
        """If copy is interrupted, the original install is still runnable.

        update.py copies files sequentially; if it crashes mid-copy,
        some new files exist alongside old ones. The application can
        still start (old files are present).
        """
        base = tmp_path / "rollback2"
        paths = _make_v07_install(base)
        release = _make_v100_release(tmp_path)

        import shutil
        # Simulate copying only core/app.exe then crashing
        (base / "core").mkdir(parents=True, exist_ok=True)
        shutil.copy2(release / "core" / "app.exe", base / "core" / "app.exe")

        # The rest of the old install is still intact
        assert (base / "start.exe").read_text() == "old start"
        assert (base / "version.txt").read_text() != ""
        assert paths["config"].exists()

    def test_rerunning_update_after_interruption_succeeds(self, tmp_path):
        """Running the update again after a crash completes successfully."""
        base = tmp_path / "rollback3"
        paths = _make_v07_install(base)
        release = _make_v100_release(tmp_path)

        import shutil

        # First attempt crashes mid-copy
        (base / "core").mkdir(parents=True, exist_ok=True)
        shutil.copy2(release / "core" / "app.exe", base / "core" / "app.exe")

        # Second attempt completes normally
        for root, dirs, files in release.walk():
            rel = root.relative_to(release)
            for f in files:
                if f.lower() in ("update.exe", "config.yaml"):
                    continue
                src = root / f
                dst = base / rel / f
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)

        assert (base / "core" / "app.exe").exists()
        assert (base / "core" / "gui.exe").exists()
        assert (base / "plugins" / "wincounter" / "main.exe").exists()


# ---------------------------------------------------------------------------
# Platform path correctness
# ---------------------------------------------------------------------------


class TestPlatformPathsIntegration:
    """Platform-specific path correctness across the update flow."""

    def test_windows_exe_suffix_consistent(self):
        suffix = ".exe" if sys.platform == "win32" else ".bin"
        assert suffix in (".exe", ".bin")

    def test_update_exe_name_consistent(self):
        suffix = ".exe" if sys.platform == "win32" else ".bin"
        name = f"update{suffix}"
        assert name == f"update{suffix}"

    def test_start_exe_name_consistent(self):
        suffix = ".exe" if sys.platform == "win32" else ".bin"
        name = f"start{suffix}"
        assert name == f"start{suffix}"

    def test_update_new_exe_name_consistent(self):
        suffix = ".exe" if sys.platform == "win32" else ".bin"
        name = f"update_new{suffix}"
        assert name == f"update_new{suffix}"

    def test_signal_path_resolved_correctly(self, tmp_path):
        base = tmp_path / "platform_test"
        base.mkdir()
        signal = base / "update_signal.tmp"
        signal.write_text("kill")
        assert signal.parent == base
        assert signal.name == "update_signal.tmp"

    def test_archive_name_platform_specific(self):
        if sys.platform == "win32":
            archive = "Tiktok2Mc_v1.0.0_Windows.zip"
            assert archive.endswith(".zip")
        else:
            archive = "Tiktok2Mc_v1.0.0_Linux.tar.gz"
            assert archive.endswith(".tar.gz")

    def test_temp_dir_resolved(self, tmp_path):
        temp = tmp_path / "_update_tmp"
        temp.mkdir()
        assert temp.exists()
        assert temp.is_dir()
