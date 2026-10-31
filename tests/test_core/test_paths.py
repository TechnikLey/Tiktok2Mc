"""Baseline tests for ``core.paths`` root/layout resolution (P0).

These tests pin the *current* resolution semantics before the P3a layout
work (data home / versioned app dirs) changes them:

- Release marker: ``config/config.yaml`` anywhere up the tree from ``base``.
- Dev marker:     ``src/core/paths.py`` anywhere up the tree from ``base``.
- Fallback:       ``base.parent.parent`` when no marker exists.
- Every user-data path hangs off ``get_root_dir()``.

Note on test isolation:
- ``tests/conftest.py`` redirects all path functions to a per-test
  ``project_dir`` (autouse fixture) for API tests. These unit tests need the
  *real* resolution logic, so we snapshot pristine functions at module import
  time (collection) and drive them via attribute injection.
- The marker walk finds the *first* matching parent. Since this repo itself
  has a dev marker at ``D:/.../Tiktok2Mc/src/core/paths.py``, every fake
  ``base`` must live *below* its fake root, and the no-marker fallback must
  be probed outside the repo tree (nonexistent paths just fail the marker
  ``.exists()`` checks and fall through to the fallback).

All fixtures live in ``tmp_path`` (redirected into ``tests/workspace/``), so
the write guard is never triggered.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

import core.paths as paths_mod
from core.update_engine import pointer as pointer_mod

# Pristine originals captured at collection time (before the conftest
# autouse path-patching fixture has ever run this session).
_REAL = {
    name: getattr(paths_mod, name)
    for name in (
        "get_root_dir",
        "get_config_file",
        "get_runtime_dir",
        "get_plugin_data_dir",
        "get_base_file",
        "get_plugins_dir",
    )
}


class TestRootResolutionPins:
    """Pin the current "walk up and look for the marker" behavior."""

    def test_release_marker_found_from_nested_app_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``app-1.0/core`` style nesting still finds the root via config.yaml."""
        root = tmp_path / "release"
        (root / "config").mkdir(parents=True)
        (root / "config" / "config.yaml").write_text("", encoding="utf-8")
        base = root / "app-1.0.0" / "core"
        base.mkdir(parents=True)
        monkeypatch.setattr(paths_mod, "get_base_dir", lambda: base)

        assert _REAL["get_root_dir"]() == root.resolve()

    def test_dev_marker_found_from_src_tree(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Dev layout resolves via the ``src/core/paths.py`` marker."""
        root = tmp_path / "project"
        (root / "src" / "core").mkdir(parents=True)
        (root / "src" / "core" / "paths.py").write_text("", encoding="utf-8")
        monkeypatch.setattr(paths_mod, "get_base_dir", lambda: root / "src")

        assert _REAL["get_root_dir"]() == root.resolve()

    def test_no_marker_falls_back_two_levels(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Fallback returns ``base.parent.parent`` (current legacy semantics).

        Uses a nonexistent path *outside* the repo tree: no parent up to the
        drive root carries a project marker, so the walk falls through.
        """
        base = Path(tempfile.gettempdir()) / "t2mc_paths_baseline_walk" / "x" / "y"
        monkeypatch.setattr(paths_mod, "get_base_dir", lambda: base)

        assert _REAL["get_root_dir"]() == base.parent.parent.resolve()


class TestUserDataPathPins:
    """User-data paths are all derived from ``get_root_dir()`` today."""

    def test_config_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(paths_mod, "get_root_dir", lambda: tmp_path)
        assert (
            _REAL["get_config_file"]()
            == (tmp_path / "config" / "config.yaml").resolve()
        )

    def test_runtime_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(paths_mod, "get_root_dir", lambda: tmp_path)
        _got = _REAL["get_runtime_dir"]()
        assert _got == (tmp_path / "core" / "runtime").resolve()

    def test_plugin_data_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(paths_mod, "get_root_dir", lambda: tmp_path)
        _got = _REAL["get_plugin_data_dir"]()
        assert _got == (tmp_path / "data" / "plugin_data").resolve()


class TestSuffix:
    def test_base_file_suffix(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        expected = "main.exe" if paths_mod.SUFFIX == ".exe" else "main.bin"
        monkeypatch.setattr(paths_mod, "get_base_dir", lambda: tmp_path)
        assert Path(_REAL["get_base_file"]()).name == expected


# ---------------------------------------------------------------------------
# P3a: versioned layout / data home (new behavior, additive)
# ---------------------------------------------------------------------------


@pytest.fixture()
def isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralize LOCALAPPDATA-derived alt home for deterministic tests."""
    monkeypatch.delenv("LOCALAPPDATA", raising=False)


class TestVersionedLayout:
    def test_flat_layout_resolves_none(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_env
    ) -> None:
        monkeypatch.setattr(paths_mod, "get_root_dir", lambda: tmp_path)
        assert paths_mod.get_active_app_dir() is None

    def test_pointer_layout_resolves_active(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        active = tmp_path / "app-1.2.0"
        active.mkdir()
        previous = tmp_path / "app-1.1.0"
        previous.mkdir()
        pointer_mod.write_pointer(
            tmp_path, pointer_mod.AppPointer("app-1.2.0", "1.2.0")
        )
        monkeypatch.setattr(paths_mod, "get_root_dir", lambda: tmp_path)
        got = paths_mod.get_active_app_dir()
        assert got is not None and got.resolve() == active.resolve()


class TestDataHome:
    def test_versioned_layout_root_wins(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / "app-1.2.0").mkdir()
        pointer_mod.write_pointer(
            tmp_path, pointer_mod.AppPointer("app-1.2.0", "1.2.0")
        )
        monkeypatch.setattr(paths_mod, "get_root_dir", lambda: tmp_path)
        assert paths_mod.get_data_home_base() == tmp_path.resolve()

    def test_user_data_at_root_wins(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_env
    ) -> None:
        (tmp_path / "config").mkdir()
        monkeypatch.setattr(paths_mod, "get_root_dir", lambda: tmp_path)
        assert paths_mod.get_data_home_base() == tmp_path.resolve()

    def test_alt_home_when_it_exists(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(paths_mod, "get_root_dir", lambda: tmp_path)
        home = tmp_path / "var"
        monkeypatch.setenv("LOCALAPPDATA", str(home))
        (home / "Tiktok2Mc" / "config").mkdir(parents=True)
        assert paths_mod.get_data_home_base() == (home / "Tiktok2Mc").resolve()

    def test_empty_root_falls_back_to_root(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_env
    ) -> None:
        monkeypatch.setattr(paths_mod, "get_root_dir", lambda: tmp_path)
        assert paths_mod.get_data_home_base() == tmp_path.resolve()

    def test_config_file_follows_data_home(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(paths_mod, "get_root_dir", lambda: tmp_path)
        home = tmp_path / "var"
        monkeypatch.setenv("LOCALAPPDATA", str(home))
        (home / "Tiktok2Mc" / "config").mkdir(parents=True)
        assert (
            _REAL["get_config_file"]()
            == (home / "Tiktok2Mc" / "config" / "config.yaml").resolve()
        )


class TestLegacyPinsStillHold:
    """P3a must be additive: legacy layouts keep resolving exactly as before."""

    def test_base_file_unchanged_in_flat_layout(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_env
    ) -> None:
        monkeypatch.setattr(paths_mod, "get_base_dir", lambda: tmp_path)
        monkeypatch.setattr(paths_mod, "get_root_dir", lambda: tmp_path)
        expected = (tmp_path / f"main{paths_mod.SUFFIX}").resolve()
        assert paths_mod.get_base_file() == expected

    def test_base_file_prefers_active_core_nested(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        active = tmp_path / "app-1.2.0"
        (active / "core").mkdir(parents=True)
        (active / "core" / f"main{paths_mod.SUFFIX}").write_bytes(b"")
        pointer_mod.write_pointer(
            tmp_path, pointer_mod.AppPointer("app-1.2.0", "1.2.0")
        )
        monkeypatch.setattr(paths_mod, "get_root_dir", lambda: tmp_path)
        monkeypatch.setattr(paths_mod, "get_base_dir", lambda: tmp_path)
        assert (
            _REAL["get_base_file"]()
            == (active / "core" / f"main{paths_mod.SUFFIX}").resolve()
        )

    def test_plugins_dir_prefers_active_app_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        active = tmp_path / "app-1.2.0"
        (active / "plugins").mkdir(parents=True)
        pointer_mod.write_pointer(
            tmp_path, pointer_mod.AppPointer("app-1.2.0", "1.2.0")
        )
        monkeypatch.setattr(paths_mod, "get_root_dir", lambda: tmp_path)
        got = _REAL["get_plugins_dir"]()
        assert got.resolve() == (active / "plugins").resolve()
