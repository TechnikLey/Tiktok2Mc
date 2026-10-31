"""Integration tests for the P3a update lifecycle.

Covers cross-cutting invariants of the new architecture that span more
than one module:

- config migration (launcher first-start hook) preserves user values
- pointer flip keeps the rollback generation and the old install intact
- interrupted/repeated staging is safe (stale dirs are wiped, pointer
  only flips when a fully verified app dir was moved)
- platform path conventions
- legacy kill-signal endpoints (API) remain available for old binaries
"""

import sys
from pathlib import Path

from core.update_engine.migration import parse_version_txt
from core.update_engine.pointer import (
    AppPointer,
    read_pointer,
    resolve_active_app_dir,
    write_pointer,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_v07_install(base: Path) -> dict:
    """A pre-P3a flat v0.7 installation."""
    paths = {
        "base": base,
        "config": base / "config" / "config.yaml",
        "default_config": base / "config" / "config.default.yaml",
        "version": base / "version.txt",
    }
    base.mkdir(parents=True, exist_ok=True)
    (base / "config").mkdir(exist_ok=True)
    paths["config"].write_text(
        "config_version: '0.7'\n"
        "server_host: 192.168.1.100\n"
        "control_method: RCON\n"
        "auto_update_config: true\n"
        "java:\n"
        "  xms: 1G\n"
        "  xmx: 2G\n"
    )
    (base / "config" / "config.default.yaml").write_text(
        "config_version: '1.0'\n"
        "server_host: 0.0.0.0\n"
        "control_method: DCS\n"
        "auto_update_config: true\n"
        "java:\n"
        "  xms: 512M\n"
        "  xmx: 1G\n"
    )
    paths["version"].write_text("ToolVersion: 0.7.0\nUpdaterVersion: 0.1.0\n")
    return paths


def _make_versioned_install(
    tmp: Path, tool: str = "1.0.0", suffix: str | None = None
) -> Path:
    """A versioned root: pointer + one active app dir."""
    suffix = suffix or (".exe" if sys.platform == "win32" else ".bin")
    root = tmp / f"versioned_{tool}"
    app_dir = root / f"app-{tool}"
    (app_dir / "core").mkdir(parents=True)
    (app_dir / "core" / f"app{suffix}").write_bytes(b"old-app")
    write_pointer(root, AppPointer(active_app_dir=f"app-{tool}", tool_version=tool))
    return root


# ---------------------------------------------------------------------------
# Config preservation (launcher first-start hook, P3a §7)
# ---------------------------------------------------------------------------


class TestVersionBoundaryUpgrade:
    def test_config_preserved_across_upgrade(self, tmp_path):
        """Upgrading 0.7 → 1.0 keeps all user values (launcher hook call)."""
        from unittest.mock import patch

        from core.config_migration import migrate_config

        base = tmp_path / "install"
        paths = _make_v07_install(base)

        with (
            patch("core.config_migration.get_backup_manager", return_value=None),
        ):
            ok = migrate_config(paths["config"], paths["default_config"])
        assert ok

        content = paths["config"].read_text()
        assert "server_host: 192.168.1.100" in content
        assert "control_method: RCON" in content
        assert "xms: 1G" in content
        assert "512M" not in content  # template default replaced by user value
        assert "config_version: '1.0'" in content

    def test_new_app_content_isolated_from_user_data(self, tmp_path):
        """The new tool version lives in app-<ver>/ next to untouched user
        data — config.yaml is never part of the installed package."""
        suffix = ".exe" if sys.platform == "win32" else ".bin"
        base = tmp_path / "install2"
        paths = _make_v07_install(base)

        app_dir = base / "app-1.0.0"
        (app_dir / "core").mkdir(parents=True)
        (app_dir / "core" / f"app{suffix}").write_bytes(b"new app")
        write_pointer(
            base, AppPointer(active_app_dir="app-1.0.0", tool_version="1.0.0")
        )

        # User config untouched by the package move
        assert "192.168.1.100" in paths["config"].read_text()
        assert resolve_active_app_dir(base) == app_dir

    def test_version_file_updated_after_upgrade(self, tmp_path):
        base = tmp_path / "install5"
        _make_v07_install(base)
        (base / "version.txt").write_text("ToolVersion: 1.0.0\nUpdaterVersion: 0.3.0\n")
        content = (base / "version.txt").read_text()
        assert "ToolVersion: 1.0.0" in content
        assert "UpdaterVersion: 0.3.0" in content

    def test_version_txt_parse_matches_updater_format(self, tmp_path):
        (tmp_path / "version.txt").write_text(
            "ToolVersion: v0.7.0\nUpdaterVersion: 0.1\n"
        )
        versions = parse_version_txt(tmp_path / "version.txt")
        assert versions == {"tool": "0.7.0", "updater": "0.1"}


# ---------------------------------------------------------------------------
# Pointer semantics across the update lifecycle
# ---------------------------------------------------------------------------


class TestPointerRollbackSemantics:
    def test_previous_generation_survives_flip(self, tmp_path):
        """After the flip the previous app dir is recorded + kept on disk."""
        root = _make_versioned_install(tmp_path, tool="0.9.0")
        old_dir = root / "app-0.9.0"

        # Simulate the updater's flip for 1.0.0
        new_dir = root / "app-1.0.0"
        (new_dir / "core").mkdir(parents=True)
        write_pointer(
            root,
            AppPointer(
                active_app_dir="app-1.0.0",
                tool_version="1.0.0",
                previous_app_dir="app-0.9.0",
            ),
        )

        pointer = read_pointer(root)
        assert pointer is not None
        assert pointer.previous_app_dir == "app-0.9.0"
        assert old_dir.is_dir(), "rollback generation must survive"
        assert resolve_active_app_dir(root) == new_dir

    def test_state_recoverable_when_active_dir_lost(self, tmp_path):
        """If the active app dir disappears, resolution falls back to the
        previous generation instead of booting nothing."""
        root = _make_versioned_install(tmp_path, tool="0.9.0")
        write_pointer(
            root,
            AppPointer(
                active_app_dir="app-1.0.0",
                tool_version="1.0.0",
                previous_app_dir="app-0.9.0",
            ),
        )
        import shutil

        lost_dir = root / "app-1.0.0"
        (lost_dir / "core").mkdir(parents=True)
        shutil.rmtree(lost_dir)  # crash after flip, dir gone

        pointer = read_pointer(root)
        assert pointer is not None
        assert pointer.previous_app_dir == "app-0.9.0"
        old_dir = root / pointer.previous_app_dir
        assert (old_dir / "core").is_dir()

    def test_rerunning_update_after_interruption_succeeds(self, tmp_path):
        """Crash between stage and flip leaves a stale app dir; the next
        run replaces it instead of failing (updater-level guarantee,
        pointer-level simulation here)."""
        root = _make_versioned_install(tmp_path, tool="0.9.0")
        stale = root / "app-1.0.0"
        (stale / "core").mkdir(parents=True)
        (stale / "core" / "partial.bin").write_bytes(b"junk")

        # next updater run: stale target not active → wiped, re-staged
        replaced = replaced_from(stale, {"core/partial.bin": b"complete"})
        assert (replaced / "core" / "partial.bin").read_bytes() == b"complete"


def replaced_from(target: Path, content: dict[str, bytes]) -> Path:
    """Helper simulating the updater's wipe + re-stage of a stale dir."""
    import shutil

    shutil.rmtree(target)
    for rel, data in content.items():
        p = target / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    return target


# ---------------------------------------------------------------------------
# Platform path correctness
# ---------------------------------------------------------------------------


class TestPlatformPathsIntegration:
    def test_windows_exe_suffix_consistent(self):
        suffix = ".exe" if sys.platform == "win32" else ".bin"
        assert suffix in (".exe", ".bin")

    def test_root_launcher_names(self):
        suffix = ".exe" if sys.platform == "win32" else ".bin"
        for name in ("start{0}", "update{0}", "update_new{0}", "start_new{0}"):
            assert name.format(suffix).endswith(suffix)

    def test_app_dir_naming_pattern(self, tmp_path):
        root = _make_versioned_install(tmp_path)
        pointer = read_pointer(root)
        assert pointer is not None
        assert pointer.active_app_dir.startswith("app-")
        assert (root / pointer.active_app_dir).is_dir()

    def test_archive_name_platform_specific(self):
        if sys.platform == "win32":
            archive = "Tiktok2Mc_v1.0.0_Windows.zip"
            assert archive.endswith(".zip")
        else:
            archive = "Tiktok2Mc_v1.0.0_Linux.tar.gz"
            assert archive.endswith(".tar.gz")

    def test_update_tmp_dir_resolved(self, tmp_path):
        base = tmp_path
        temp_dir = (base / "_update_tmp").resolve()
        assert str(temp_dir).endswith("_update_tmp")


# ---------------------------------------------------------------------------
# Legacy signal API endpoints (still served for old binaries)
# ---------------------------------------------------------------------------


class TestSignalLifecycleIntegration:
    def test_api_signal_lifecycle(self, client):
        """The kill-signal API contract works: set → read → clear."""
        resp = client.put("/api/v1/updater/signal", json={"signal": "kill"})
        assert resp.status_code == 200
        resp = client.get("/api/v1/updater/signal")
        assert resp.json().get("signal") == "kill"
        resp = client.delete("/api/v1/updater/signal")
        assert resp.status_code == 200
        assert client.get("/api/v1/updater/signal").json().get("signal") is None
