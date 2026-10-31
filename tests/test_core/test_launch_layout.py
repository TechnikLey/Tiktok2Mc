"""Unit tests for ``core.update_engine.launch_layout`` (P3a §7)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.paths import SUFFIX as EXE_SUFFIX
from core.update_engine.launch_layout import resolve_app_base
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
