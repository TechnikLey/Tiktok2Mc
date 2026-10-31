"""Unit tests for ``core.update_engine.migration`` (P3a §8).

All fixtures live in ``tmp_path`` (redirected into ``tests/workspace/``).
The runtime dir (journal location) is resolved via ``core.paths``, which
``conftest`` redirects into the per-test ``project_dir`` — the journal is
therefore isolated per test automatically.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.update_engine import migration as migration_mod
from core.update_engine.migration import (
    is_legacy_install,
    migrate_install,
    parse_version_txt,
)
from core.update_engine.pointer import read_pointer, resolve_active_app_dir


def make_legacy(root: Path, tool: str = "1.1.0") -> None:
    """Create a legacy flat release layout under *root*."""
    core_dir = root / "core"
    core_dir.mkdir(parents=True)
    (core_dir / f"main{migration_mod.SUFFIX}").write_bytes(b"m")
    (core_dir / f"gui{migration_mod.SUFFIX}").write_bytes(b"g")
    runtime_dir = core_dir / "runtime"
    runtime_dir.mkdir()
    (runtime_dir / "signal.tmp").write_text("x", encoding="utf-8")
    plugins = root / "plugins"
    plugins.mkdir()
    (plugins / "sample_hook.json").write_text("{}", encoding="utf-8")
    # user data stays
    cfg = root / "config"
    cfg.mkdir()
    (cfg / "config.yaml").write_text("config_version: 1.1\n", encoding="utf-8")
    (root / "version.txt").write_text(
        f"ToolVersion: {tool}\nUpdaterVersion: 0.2.0\n", encoding="utf-8"
    )


class TestVersionTxtParsing:
    def test_parse_releases(self, tmp_path: Path) -> None:
        vfile = tmp_path / "version.txt"
        vfile.write_text(
            "ToolVersion: v1.2.3\nUpdaterVersion: 0.2.1\n", encoding="utf-8"
        )
        versions = parse_version_txt(vfile)
        assert versions == {"tool": "1.2.3", "updater": "0.2.1"}

    def test_missing_file_defaults(self, tmp_path: Path) -> None:
        assert parse_version_txt(tmp_path / "nope.txt") == {
            "tool": "0.0.0",
            "updater": "0.0.0",
        }


class TestLegacyDetection:
    def test_positive(self, tmp_path: Path) -> None:
        make_legacy(tmp_path)
        assert is_legacy_install(tmp_path)

    def test_dev_tree_protected(self, tmp_path: Path) -> None:
        """No version.txt → never treated as legacy (protects dev repos)."""
        core_dir = tmp_path / "core"
        core_dir.mkdir()
        (core_dir / "weird.exe").write_bytes(b"x")
        assert not is_legacy_install(tmp_path)

    def test_versioned_layout_not_legacy(self, tmp_path: Path) -> None:
        make_legacy(tmp_path)
        (tmp_path / "current.json").write_text("{}", encoding="utf-8")
        assert not is_legacy_install(tmp_path)

    def test_missing_root_not_legacy(self, tmp_path: Path) -> None:
        assert not is_legacy_install(tmp_path / "absent")


class TestMigrateInstall:
    def test_full_migration(self, tmp_path: Path) -> None:
        make_legacy(tmp_path, tool="1.1.0")
        result = migrate_install(tmp_path)
        assert result.migrated and result.reason == "migrated"

        app_dir = result.app_dir
        assert app_dir is not None and app_dir.name == "app-1.1.0"
        # Program binaries moved
        assert (app_dir / "core" / f"main{migration_mod.SUFFIX}").is_file()
        assert (app_dir / "core" / f"gui{migration_mod.SUFFIX}").is_file()
        assert (app_dir / "plugins" / "sample_hook.json").is_file()
        # User data untouched
        assert (tmp_path / "config" / "config.yaml").is_file()
        assert (tmp_path / "core" / "runtime" / "signal.tmp").is_file()
        # Pointer points at the app dir
        pointer = read_pointer(tmp_path)
        assert pointer is not None and pointer.active_app_dir == "app-1.1.0"
        assert resolve_active_app_dir(tmp_path) == app_dir
        # No stragglers: core/ only keeps runtime
        remaining_core = [child.name for child in (tmp_path / "core").iterdir()]
        assert remaining_core == ["runtime"]

    def test_idempotent_second_run(self, tmp_path: Path) -> None:
        make_legacy(tmp_path)
        first = migrate_install(tmp_path)
        second = migrate_install(tmp_path)
        assert first.migrated
        assert not second.migrated and second.reason == "already_versioned"
        app_dir = first.app_dir
        assert (app_dir / "core" / f"main{migration_mod.SUFFIX}").is_file()  # type: ignore[index]

    def test_resume_after_partial_core_move(self, tmp_path: Path) -> None:
        """Simulate a crash after gui.exe was moved but main.exe not."""
        make_legacy(tmp_path)
        app_dir = tmp_path / "app-1.1.0"
        (app_dir / "core").mkdir(parents=True)
        (app_dir / "core" / f"gui{migration_mod.SUFFIX}").write_bytes(b"g")
        journal = {
            "phase": "running",
            "app_dir": "app-1.1.0",
            "steps_done": ["move_core"],
        }
        runtime = migration_mod.get_runtime_dir()
        runtime.mkdir(parents=True, exist_ok=True)
        (runtime / migration_mod.STATE_FILE).write_text(
            json.dumps(journal), encoding="utf-8"
        )

        result = migrate_install(tmp_path)
        assert result.migrated and result.reason == "migrated"
        # Nothing got moved twice — main.exe lands next to the already moved gui.
        assert (app_dir / "core" / f"main{migration_mod.SUFFIX}").is_file()
        # Pointer written even though the crash happened after move_core.
        pointer = read_pointer(tmp_path)
        assert pointer is not None and pointer.active_app_dir == "app-1.1.0"

    def test_flat_without_program_content(self, tmp_path: Path) -> None:
        """config-only tree (nothing to move) → nothing_to_migrate."""
        (tmp_path / "config").mkdir()
        assert migrate_install(tmp_path).reason == "nothing_to_migrate"

    def test_unreadable_version_aborts(self, tmp_path: Path) -> None:
        make_legacy(tmp_path)
        (tmp_path / "version.txt").write_text(
            "UpdaterVersion: 0.2.0\n", encoding="utf-8"
        )
        result = migrate_install(tmp_path)
        assert not result.migrated and result.reason == "missing_version"

    @pytest.mark.parametrize("override", ["1.5.0"])
    def test_version_override(self, tmp_path: Path, override: str) -> None:
        make_legacy(tmp_path, tool="1.1.0")
        result = migrate_install(tmp_path, tool_version=override)
        assert result.app_dir is not None
        assert result.app_dir.name == f"app-{override}"
