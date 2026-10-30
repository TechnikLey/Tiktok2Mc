"""Unit tests for ``core.update_engine.pointer`` (P3a).

All paths operate inside ``tmp_path`` (redirected into ``tests/workspace/``).
"""

from __future__ import annotations

import json
from logging import Logger
from pathlib import Path
from unittest.mock import patch

import pytest
from packaging.version import Version

from core.update_engine.pointer import (
    APP_DIR_PREFIX,
    AppPointer,
    PointerError,
    pointer_path,
    prune_versions,
    read_pointer,
    resolve_active_app_dir,
    scan_app_dirs,
    write_pointer,
)


def _make_app_dir(root: Path, version: str) -> Path:
    d = root / f"{APP_DIR_PREFIX}{version}"
    d.mkdir(parents=True, exist_ok=True)
    (d / "version.txt").write_text(version, encoding="utf-8")
    return d


@pytest.fixture()
def _quiet_log():
    with patch.object(Logger, "warning"), patch.object(Logger, "info"):
        yield


class TestScanAppDirs:
    def test_sorted_oldest_first(self, tmp_path: Path) -> None:
        _make_app_dir(tmp_path, "1.0.0")
        _make_app_dir(tmp_path, "1.2.0")
        _make_app_dir(tmp_path, "1.1.0")
        pairs = scan_app_dirs(tmp_path)
        versions = [v for _, v in pairs]
        assert versions == [Version("1.0.0"), Version("1.1.0"), Version("1.2.0")]

    def test_ignores_invalid_and_unrelated_dirs(self, tmp_path: Path) -> None:
        (tmp_path / "app-notaversion").mkdir()
        (tmp_path / "config").mkdir()
        (tmp_path / "app-1.2.3").mkdir()
        pairs = scan_app_dirs(tmp_path)
        assert [p.name for p, _ in pairs] == ["app-1.2.3"]

    def test_missing_root_empty(self, tmp_path: Path) -> None:
        assert scan_app_dirs(tmp_path / "does-not-exist") == []


class TestPointerValidation:
    def test_valid_roundtrip(self) -> None:
        p = AppPointer("app-1.2.0", "1.2.0", previous_app_dir="app-1.1.0")
        assert AppPointer.from_dict(p.to_dict()) == p

    def test_rejects_path_traversal(self) -> None:
        with pytest.raises(PointerError):
            AppPointer.from_dict(
                {"active_app_dir": "app-1.0/../..", "tool_version": "1.0"}
            )

    def test_rejects_rejects_separator(self) -> None:
        with pytest.raises(PointerError):
            AppPointer.from_dict(
                {"active_app_dir": "app-1.0\\sub", "tool_version": "1.0"}
            )

    def test_rejects_non_version_suffix(self) -> None:
        with pytest.raises(PointerError):
            AppPointer.from_dict(
                {"active_app_dir": "app-nonsense", "tool_version": "1.0"}
            )

    def test_requires_required_fields(self) -> None:
        with pytest.raises(PointerError):
            AppPointer.from_dict({"active_app_dir": "app-1.0.0"})


class TestReadWrite:
    def test_roundtrip_file(self, tmp_path: Path) -> None:
        p = AppPointer("app-1.2.0", "1.2.0", previous_app_dir="app-1.1.0")
        write_pointer(tmp_path, p)
        assert read_pointer(tmp_path) == p
        assert pointer_path(tmp_path).name == "current.json"

    def test_atomic_write_removes_tmp(self, tmp_path: Path) -> None:
        p = AppPointer("app-1.2.0", "1.2.0")
        write_pointer(tmp_path, p)
        assert not (tmp_path / "current.json.tmp").exists()

    def test_read_returns_none_on_corrupt(self, tmp_path: Path, _quiet_log) -> None:
        (tmp_path / "current.json").write_text("{not json", encoding="utf-8")
        assert read_pointer(tmp_path) is None

    def test_read_returns_none_on_missing(self, tmp_path: Path) -> None:
        assert read_pointer(tmp_path) is None

    def test_read_returns_none_on_payload_violation(
        self, tmp_path: Path, _quiet_log
    ) -> None:
        (tmp_path / "current.json").write_text(
            json.dumps({"active_app_dir": "app-1.0/../../evil", "tool_version": "1"}),
            encoding="utf-8",
        )
        assert read_pointer(tmp_path) is None


class TestResolveActiveAppDir:
    def test_uses_pointer_when_valid(self, tmp_path: Path) -> None:
        older = _make_app_dir(tmp_path, "1.1.0")
        active = _make_app_dir(tmp_path, "1.2.0")
        write_pointer(tmp_path, AppPointer("app-1.2.0", "1.2.0"))
        assert resolve_active_app_dir(tmp_path) == active
        assert older != active

    def test_pointer_missing_dir_falls_back_to_newest(
        self, tmp_path: Path, _quiet_log
    ) -> None:
        _make_app_dir(tmp_path, "1.1.0")
        _make_app_dir(tmp_path, "1.2.0")
        write_pointer(tmp_path, AppPointer("app-9.9.9", "9.9.9"))
        resolved = resolve_active_app_dir(tmp_path)
        assert resolved is not None and resolved.name == "app-1.2.0"

    def test_corrupt_pointer_falls_back_to_newest(
        self, tmp_path: Path, _quiet_log
    ) -> None:
        _make_app_dir(tmp_path, "1.1.0")
        _make_app_dir(tmp_path, "1.2.0")
        (tmp_path / "current.json").write_text("}{", encoding="utf-8")
        resolved = resolve_active_app_dir(tmp_path)
        assert resolved is not None and resolved.name == "app-1.2.0"

    def test_no_layout_returns_none(self, tmp_path: Path) -> None:
        assert resolve_active_app_dir(tmp_path) is None


class TestPruneVersions:
    def test_keeps_active_and_previous(self, tmp_path: Path) -> None:
        _make_app_dir(tmp_path, "1.0.0")
        _make_app_dir(tmp_path, "1.1.0")
        _make_app_dir(tmp_path, "1.2.0")
        removed = prune_versions(tmp_path, "app-1.2.0", "app-1.1.0")
        assert removed == ["app-1.0.0"]
        assert (tmp_path / "app-1.1.0").is_dir()
        assert (tmp_path / "app-1.2.0").is_dir()

    def test_never_touches_unrelated_dirs(self, tmp_path: Path) -> None:
        _make_app_dir(tmp_path, "1.0.0")
        unrelated = tmp_path / "config"
        unrelated.mkdir()
        prune_versions(tmp_path, "app-1.0.0")
        assert unrelated.is_dir()
