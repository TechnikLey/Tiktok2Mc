"""Tests for ``build.py`` P3a release assembly.

``build.py`` is a script without package layout — it is loaded via
``importlib.spec_from_file_location`` from the repo root. The tests exercise
``_assemble_versioned_release`` directly against a synthetic release tree in
the pytest ``tmp_path`` (WriteGuard-redirected into ``tests/workspace/``).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _load_build_module(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """Import ``build.py`` fresh (module-level state is read via sys.path)."""
    spec = importlib.util.spec_from_file_location(
        "build_assembly", REPO_ROOT / "build.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "build_assembly", module)
    spec.loader.exec_module(module)
    return module


def _make_release_tree(out_dir: Path, suffix: str) -> None:
    """Simulate the flat ``cmd_app`` output right before assembly."""
    (out_dir / "core").mkdir(parents=True)
    (out_dir / "core" / f"app{suffix}").write_bytes(b"app-binary")
    (out_dir / "core" / f"gui{suffix}").write_bytes(b"gui-binary")
    (out_dir / "core" / f"update_progress{suffix}").write_bytes(b"splash")
    (out_dir / "plugins").mkdir()
    (out_dir / "plugins" / "example").mkdir()
    (out_dir / "plugins" / "example" / "main.py").write_text(
        "# plugin", encoding="utf-8"
    )
    (out_dir / f"start{suffix}").write_bytes(b"start-binary")
    (out_dir / f"update{suffix}").write_bytes(b"update-binary")
    (out_dir / "config").mkdir()
    (out_dir / "config" / "config.default.yaml").write_text(
        "config_version: '1.1'\n", encoding="utf-8"
    )
    (out_dir / "hooks").mkdir()
    (out_dir / "hooks" / "example").mkdir()
    (out_dir / "hooks" / "example" / "hook.json").write_text("{}", encoding="utf-8")
    (out_dir / "version.txt").write_text(
        "ToolVersion: 1.0.0\nUpdaterVersion: 0.3.0\n", encoding="utf-8"
    )


class TestAssembleVersionedRelease:
    def test_full_assembly(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        build = _load_build_module(monkeypatch)
        suffix = build.SUFFIX if hasattr(build, "SUFFIX") else ".exe"
        out_dir = tmp_path / "release"
        _make_release_tree(out_dir, suffix)
        monkeypatch.delenv("T2M_SIGNING_PRIVATE_KEY", raising=False)

        info = build._assemble_versioned_release(out_dir, "1.0.0", "0.3.0", suffix)

        app_dir = out_dir / "app-1.0.0"
        # core/ + plugins/ moved, nothing left at the root.
        assert (app_dir / "core" / f"app{suffix}").read_bytes() == b"app-binary"
        assert (app_dir / "core" / f"gui{suffix}").is_file()
        assert (app_dir / "plugins" / "example" / "main.py").is_file()
        assert not (out_dir / "core").exists()
        assert not (out_dir / "plugins").exists()
        # Root keeps the deliverable shells and user-facing trees.
        assert (out_dir / f"start{suffix}").is_file()
        assert (out_dir / "config" / "config.default.yaml").is_file()
        assert (out_dir / "hooks" / "example" / "hook.json").is_file()
        assert info == {
            "app_dir": "app-1.0.0",
            "moved": ["core", "plugins"],
            "manifest": str(out_dir / "manifest.json"),
            "files": len(
                build.update_manifest.parse_manifest_bytes(
                    (out_dir / "manifest.json").read_bytes()
                ).files
            ),
            "key_source": "ephemeral (dev build)",
        }

    def test_pointer_written_for_fresh_install(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        build = _load_build_module(monkeypatch)
        suffix = ".exe"
        out_dir = tmp_path / "release"
        _make_release_tree(out_dir, suffix)
        monkeypatch.delenv("T2M_SIGNING_PRIVATE_KEY", raising=False)

        build._assemble_versioned_release(out_dir, "1.0.0", "0.3.0", suffix)

        from core.update_engine.pointer import read_pointer

        pointer = read_pointer(out_dir)
        assert pointer is not None
        assert pointer.active_app_dir == "app-1.0.0"
        assert pointer.tool_version == "1.0.0"
        assert pointer.previous_app_dir is None

    def test_manifest_covers_program_content_only(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        build = _load_build_module(monkeypatch)
        suffix = ".exe"
        out_dir = tmp_path / "release"
        _make_release_tree(out_dir, suffix)
        monkeypatch.delenv("T2M_SIGNING_PRIVATE_KEY", raising=False)

        build._assemble_versioned_release(out_dir, "1.0.0", "0.3.0", suffix)

        manifest = build.update_manifest.parse_manifest_bytes(
            (out_dir / "manifest.json").read_bytes()
        )
        covered = {entry.path for entry in manifest.files}
        assert "app-1.0.0/core/app.exe" in covered
        assert f"start{suffix}" in covered
        assert f"update{suffix}" in covered
        assert "current.json" in covered
        assert "version.txt" in covered
        # The per-version config template rides along in the app dir
        # (launcher first-start hook resolves it as candidate 1).
        assert "app-1.0.0/config/config.default.yaml" in covered
        # Templates/user trees are never part of an update.
        assert not any(p.startswith("config/") for p in covered)
        assert not any(p.startswith("hooks/") for p in covered)
        assert manifest.tool_version == "1.0.0"
        assert manifest.updater_version == "0.3.0"

    def test_signature_verifies_against_signing_key(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        build = _load_build_module(monkeypatch)
        suffix = ".exe"
        out_dir = tmp_path / "release"
        _make_release_tree(out_dir, suffix)
        private_key = Ed25519PrivateKey.generate()
        monkeypatch.setenv(
            "T2M_SIGNING_PRIVATE_KEY", private_key.private_bytes_raw().hex()
        )

        info = build._assemble_versioned_release(out_dir, "1.0.0", "0.3.0", suffix)
        assert info["key_source"] == "T2M_SIGNING_PRIVATE_KEY"

        raw = (out_dir / "manifest.json").read_bytes()
        sig = (out_dir / "manifest.json.sig").read_bytes()
        public_key = private_key.public_key()
        assert build.update_manifest.verify_signature(raw, sig, public_key) is True
        manifest = build.update_manifest.parse_manifest_bytes(raw)
        # The updater-side guarantee: every covered file verifies at the
        # release root with the exact bytes that are shipped.
        assert build.update_manifest.verify_files(out_dir, manifest) == []

    def test_wrong_key_fails_verification(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        build = _load_build_module(monkeypatch)
        suffix = ".exe"
        out_dir = tmp_path / "release"
        _make_release_tree(out_dir, suffix)
        monkeypatch.setenv(
            "T2M_SIGNING_PRIVATE_KEY",
            Ed25519PrivateKey.generate().private_bytes_raw().hex(),
        )
        build._assemble_versioned_release(out_dir, "1.0.0", "0.3.0", suffix)

        raw = (out_dir / "manifest.json").read_bytes()
        sig = (out_dir / "manifest.json.sig").read_bytes()
        attacker = Ed25519PrivateKey.generate().public_key()
        assert build.update_manifest.verify_signature(raw, sig, attacker) is False

    def test_invalid_private_key_hex_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        build = _load_build_module(monkeypatch)
        out_dir = tmp_path / "release"
        _make_release_tree(out_dir, ".exe")
        monkeypatch.setenv("T2M_SIGNING_PRIVATE_KEY", "zzzz")
        with pytest.raises(ValueError):
            build._assemble_versioned_release(out_dir, "1.0.0", "0.3.0", ".exe")

    def test_incremental_rerun_is_idempotent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``--only`` rebuilds run the finalizer against an already
        assembled tree — no crash, no duplicated content."""
        build = _load_build_module(monkeypatch)
        suffix = ".exe"
        out_dir = tmp_path / "release"
        _make_release_tree(out_dir, suffix)
        monkeypatch.delenv("T2M_SIGNING_PRIVATE_KEY", raising=False)
        build._assemble_versioned_release(out_dir, "1.0.0", "0.3.0", suffix)

        # Simulate an incremental rebuild refreshing one core binary inside
        # the (already versioned) app dir.
        (out_dir / "app-1.0.0" / "core" / f"app{suffix}").write_bytes(b"app-binary-v2")
        info = build._assemble_versioned_release(out_dir, "1.0.0", "0.3.0", suffix)

        assert info["moved"] == []
        assert (out_dir / "app-1.0.0" / "core" / f"app{suffix}").read_bytes() == (
            b"app-binary-v2"
        )
        manifest = build.update_manifest.parse_manifest_bytes(
            (out_dir / "manifest.json").read_bytes()
        )
        covered = {entry.path for entry in manifest.files}
        assert f"app-1.0.0/core/app{suffix}" in covered
        from core.update_engine.pointer import read_pointer

        assert read_pointer(out_dir) is not None

    def test_stale_app_core_replaced(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A leftover app dir from a crashed incremental build is freshened."""
        build = _load_build_module(monkeypatch)
        suffix = ".exe"
        out_dir = tmp_path / "release"
        # Stale leftover: app dir exists with an old core/, while the fresh
        # flat build produced a new core/ at the root.
        stale = out_dir / "app-1.0.0" / "core"
        stale.mkdir(parents=True)
        (stale / "app.exe").write_bytes(b"stale")
        _make_release_tree(out_dir, suffix)
        monkeypatch.delenv("T2M_SIGNING_PRIVATE_KEY", raising=False)

        build._assemble_versioned_release(out_dir, "1.0.0", "0.3.0", suffix)

        fresh = (out_dir / "app-1.0.0" / "core" / f"app{suffix}").read_bytes()
        assert fresh == b"app-binary"

    def test_missing_core_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        build = _load_build_module(monkeypatch)
        out_dir = tmp_path / "release"
        out_dir.mkdir()
        (out_dir / "start.exe").write_bytes(b"s")
        monkeypatch.delenv("T2M_SIGNING_PRIVATE_KEY", raising=False)
        with pytest.raises(RuntimeError, match="no program content"):
            build._assemble_versioned_release(out_dir, "1.0.0", "0.3.0", ".exe")

    def test_missing_root_pointer_inputs_raise(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        build = _load_build_module(monkeypatch)
        out_dir = tmp_path / "release"
        out_dir.mkdir()
        (out_dir / "core").mkdir()
        (out_dir / "core" / "app.exe").write_bytes(b"a")
        monkeypatch.delenv("T2M_SIGNING_PRIVATE_KEY", raising=False)
        with pytest.raises(RuntimeError, match="version.txt is missing"):
            build._assemble_versioned_release(out_dir, "1.0.0", "0.3.0", ".exe")
