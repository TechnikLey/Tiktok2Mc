"""Unit tests for ``core.update_engine.launch_layout`` (P3a §7)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.paths import SUFFIX as EXE_SUFFIX
from core.update_engine.launch_layout import (
    resolve_app_base,
    run_first_start_config_hook,
    swap_pending_launcher_binaries,
)
from core.update_engine.migration import migrate_install
from core.update_engine.pointer import AppPointer, write_pointer


def _flat_with_program(root: Path, tool: str = "1.1.0") -> Path:
    """Legacy release tree; program content under core/."""
    core_dir = root / "core"
    core_dir.mkdir(parents=True)
    (core_dir / f"app{EXE_SUFFIX}").write_bytes(b"a")
    (core_dir / f"gui{EXE_SUFFIX}").write_bytes(b"g")
    (root / "version.txt").write_text(f"ToolVersion: {tool}\n", encoding="utf-8")
    return root


class TestSwapPendingLauncherBinaries:
    def test_swaps_update_and_start(self, tmp_path: Path) -> None:
        root = tmp_path
        (root / f"update_new{EXE_SUFFIX}").write_bytes(b"n")
        (root / f"start_new{EXE_SUFFIX}").write_bytes(b"n")
        (root / f"start{EXE_SUFFIX}").write_bytes(b"o")
        swap = swap_pending_launcher_binaries(root, EXE_SUFFIX)
        assert swap == {"start": True, "update": True}
        assert (root / f"update{EXE_SUFFIX}").read_bytes() == b"n"
        assert not (root / f"update_new{EXE_SUFFIX}").exists()
        assert (root / f"start{EXE_SUFFIX}").read_bytes() == b"n"
        assert not (root / f"start_new{EXE_SUFFIX}").exists()

    def test_nothing_pending_is_noop(self, tmp_path: Path) -> None:
        swap = swap_pending_launcher_binaries(tmp_path, EXE_SUFFIX)
        assert swap == {"start": False, "update": False}

    def test_replace_failure_is_swallowed(self, tmp_path: Path) -> None:
        """ "Locked target" (e.g. image held) must not crash the boot."""
        root = tmp_path
        pending = root / f"start_new{EXE_SUFFIX}"
        pending.write_bytes(b"n")
        (root / f"start{EXE_SUFFIX}").write_bytes(b"o")

        import core.update_engine.launch_layout as layout_mod

        def locked(_src, _dst):
            raise OSError("Permission denied")

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(layout_mod.os, "replace", locked)
            swap = swap_pending_launcher_binaries(root, EXE_SUFFIX)

        assert swap == {"start": False, "update": False}
        assert pending.exists()
        assert (root / f"start{EXE_SUFFIX}").read_bytes() == b"o"

    def test_stale_prev_image_cleaned(self, tmp_path: Path) -> None:
        root = tmp_path
        (root / f"start_prev{EXE_SUFFIX}").write_bytes(b"old-leftover")
        swap_pending_launcher_binaries(root, EXE_SUFFIX)
        assert not (root / f"start_prev{EXE_SUFFIX}").exists()


class TestFirstStartConfigHook:
    @pytest.fixture()
    def hook_env(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        """Root + runtime isolated in tmp; get_config_file/data-provider patched."""
        from core import paths as paths_mod

        data_home = tmp_path / "datahome"
        (data_home / "config").mkdir(parents=True)
        runtime = data_home / "core" / "runtime"

        monkeypatch.setattr(
            paths_mod, "get_config_file", lambda: data_home / "config" / "config.yaml"
        )
        monkeypatch.setattr(paths_mod, "get_runtime_dir", lambda: runtime)
        return tmp_path

    def test_noop_without_version_alignment(self, hook_env: Path) -> None:
        assert run_first_start_config_hook(hook_env / "nothere") is None

    def test_versioned_layout_migrates_and_marks(self, hook_env: Path) -> None:
        root = hook_env
        data_home = root / "datahome"
        app_dir = root / "app-1.2.0"
        (app_dir / "config").mkdir(parents=True)
        (app_dir / "config" / "config.default.yaml").write_text(
            "config_version: '1.2'\nserver_host: 0.0.0.0\n", encoding="utf-8"
        )
        write_pointer(
            root, AppPointer(active_app_dir="app-1.2.0", tool_version="1.2.0")
        )
        (data_home / "config" / "config.yaml").write_text(
            "config_version: '0.7'\nserver_host: 127.0.0.1\n", encoding="utf-8"
        )

        result = run_first_start_config_hook(root)
        assert result is not None and result["migrated"] is True

        content = (data_home / "config" / "config.yaml").read_text(encoding="utf-8")
        assert "config_version: '1.2'" in content
        assert "server_host: 127.0.0.1" in content

        marker = data_home / "core" / "runtime" / "last_run_version.txt"
        assert marker.read_text(encoding="utf-8").strip() == "1.2.0"

        # Second run with the same version → no-op
        assert run_first_start_config_hook(root) is None

    def test_marker_short_circuits(self, hook_env: Path) -> None:
        root = hook_env
        app_dir = root / "app-1.2.0"
        (app_dir / "config").mkdir(parents=True)
        (app_dir / "config" / "config.default.yaml").write_text(
            "config_version: '1.2'\n", encoding="utf-8"
        )
        write_pointer(
            root, AppPointer(active_app_dir="app-1.2.0", tool_version="1.2.0")
        )
        runtime = root / "datahome" / "core" / "runtime"
        runtime.mkdir(parents=True)
        (runtime / "last_run_version.txt").write_text("1.2.0\n", encoding="utf-8")
        assert run_first_start_config_hook(root) is None

    def test_falls_back_to_root_template(self, hook_env: Path) -> None:
        """Migrated installs keep the template at root config/."""
        root = hook_env
        data_home = root / "datahome"
        app_dir = root / "app-1.3.0"
        (app_dir / "core").mkdir(parents=True)
        write_pointer(
            root, AppPointer(active_app_dir="app-1.3.0", tool_version="1.3.0")
        )
        (root / "config").mkdir()
        (root / "config" / "config.default.yaml").write_text(
            "config_version: '1.3'\ngithub_token: default\n", encoding="utf-8"
        )
        (data_home / "config" / "config.yaml").write_text(
            "config_version: '1.1'\ngithub_token: mytoken\n", encoding="utf-8"
        )

        result = run_first_start_config_hook(root)
        assert result is not None and result["migrated"] is True
        content = (data_home / "config" / "config.yaml").read_text(encoding="utf-8")
        assert "mytoken" in content
        assert "config_version: '1.3'" in content

    def test_missing_template_skips(self, hook_env: Path) -> None:
        root = hook_env
        app_dir = root / "app-1.3.0"
        (app_dir / "core").mkdir(parents=True)
        write_pointer(
            root, AppPointer(active_app_dir="app-1.3.0", tool_version="1.3.0")
        )
        assert run_first_start_config_hook(root) is None


class TestResolveAppBase:
    def test_flat_layout_is_noop(self, tmp_path: Path) -> None:
        base = tmp_path / "flat"
        (base / "core").mkdir(parents=True)
        base_dir, migrated = resolve_app_base(base, tmp_path)
        assert base_dir == base.resolve()
        assert not migrated

    def test_legacy_migrates_and_switches(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _flat_with_program(tmp_path / "install", tool="1.1.0")
        # Journal location must be inside tmp — patch runtime dir resolution.
        from core import paths as paths_mod

        monkeypatch.setattr(paths_mod, "get_data_home_base", lambda: tmp_path)

        base_dir, migrated = resolve_app_base(
            tmp_path / "install", tmp_path / "install"
        )
        assert migrated
        assert base_dir.name == "app-1.1.0"
        assert (base_dir / "core" / f"app{EXE_SUFFIX}").is_file()

    def test_versioned_layout_resolves_without_migration(self, tmp_path: Path) -> None:
        _flat_with_program(tmp_path)
        migrate_install(tmp_path)
        base_dir, migrated = resolve_app_base(tmp_path, tmp_path)
        assert not migrated
        assert base_dir.name == "app-1.1.0"
        assert (base_dir / "core" / f"app{EXE_SUFFIX}").is_file()

    def test_pointer_missing_dir_falls_back_to_base(self, tmp_path: Path) -> None:
        write_pointer(tmp_path, AppPointer("app-9.9.9", "9.9.9"))
        base = tmp_path / "flat"
        (base / "core").mkdir(parents=True)
        base_dir, migrated = resolve_app_base(base, tmp_path)
        # Pointer references a nonexistent dir; no app dirs exist → legacy base.
        assert not migrated
        # No app dirs present, scan fallback finds nothing → base wins.
        assert base_dir == base.resolve()

    def test_migration_failure_degrades_to_base(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        base = _flat_with_program(tmp_path / "install")
        # version.txt unreadable → migration aborts with missing_version
        (base / "version.txt").write_text("Broken: x\n", encoding="utf-8")
        from core import paths as paths_mod

        monkeypatch.setattr(paths_mod, "get_data_home_base", lambda: base)

        got_base, migrated = resolve_app_base(base, base)
        assert not migrated
        assert got_base == base.resolve()

    def test_journal_written_during_migration(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _flat_with_program(tmp_path / "install")
        from core import paths as paths_mod

        monkeypatch.setattr(paths_mod, "get_data_home_base", lambda: tmp_path)
        monkeypatch.setattr(
            "core.update_engine.migration.get_runtime_dir",
            lambda: tmp_path / "core" / "runtime",
        )
        resolve_app_base(tmp_path / "install", tmp_path / "install")
        state_file = tmp_path / "core" / "runtime" / "migration_state.json"
        assert state_file.is_file()
        state = json.loads(state_file.read_text(encoding="utf-8"))
        assert state["phase"] == "done"
