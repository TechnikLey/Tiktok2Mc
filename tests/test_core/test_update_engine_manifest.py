"""Unit tests for ``core.update_engine.manifest`` (P3a signing/verification).

All fixtures live in ``tmp_path``; the temporary workspace is kept out of
git ``.gitignore`` guarded targets.
"""

from __future__ import annotations

import json
from logging import Logger
from pathlib import Path
from unittest.mock import patch

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core.update_engine.manifest import (
    Manifest,
    ManifestError,
    ManifestFile,
    generate_manifest,
    load_fs_signature,
    parse_manifest_bytes,
    serialize_manifest,
    verify_files,
    verify_signature,
    write_manifest,
)


def _make_app_tree(root: Path, files: dict[str, bytes]) -> Path:
    app_dir = root / "app-1.2.0"
    for name, content in files.items():
        target = app_dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    return app_dir


@pytest.fixture()
def keypair() -> tuple[Ed25519PrivateKey, Ed25519PrivateKey]:
    signer = Ed25519PrivateKey.generate()
    attacker = Ed25519PrivateKey.generate()
    return signer, attacker


class TestGenerateManifest:
    def test_covers_all_files_sorted(self, tmp_path: Path) -> None:
        app = _make_app_tree(
            tmp_path,
            {"b.bin": b"b", "core/main.exe": b"m", "version.txt": b"1.2.0"},
        )
        man = generate_manifest(
            app, tool_version="1.2.0", config_version_expected="1.1"
        )
        paths = [e.path for e in man.files]
        assert paths == sorted(paths)
        assert "app-1.2.0/core/main.exe" in paths and "app-1.2.0/b.bin" in paths

    def test_empty_app_dir_rejected(self, tmp_path: Path) -> None:
        (tmp_path / "app-empty").mkdir()
        with pytest.raises(ManifestError):
            generate_manifest(
                tmp_path / "app-empty",
                tool_version="0.1",
                config_version_expected="1.1",
            )


class TestSerialization:
    def test_deterministic_bytes(self, tmp_path: Path) -> None:
        app = _make_app_tree(tmp_path, {"a.txt": b"hi"})
        a = generate_manifest(app, tool_version="1", config_version_expected="1")
        b = generate_manifest(app, tool_version="1", config_version_expected="1")
        assert serialize_manifest(a) == serialize_manifest(b)

    def test_roundtrip(self, tmp_path: Path) -> None:
        app = _make_app_tree(tmp_path, {"core/m.exe": b"xyz"})
        man = generate_manifest(
            app, tool_version="1.2.0", config_version_expected="1.1"
        )
        again = parse_manifest_bytes(serialize_manifest(man))
        assert again == man

    def test_invalid_json_rejected(self) -> None:
        with pytest.raises(ManifestError):
            parse_manifest_bytes(b"{ nope")


class TestPathValidation:
    @pytest.mark.parametrize(
        "bad",
        ["../escape.txt", "/abs/path", "C:\\x.txt", "a\\b", "sub/../x"],
    )
    def test_rejects_unsafe_paths(self, bad: str) -> None:
        with pytest.raises(ManifestError):
            ManifestFile.from_dict({"path": bad, "sha256": "0" * 64, "size": 0})

    def test_rejects_bad_hash_length(self) -> None:
        with pytest.raises(ManifestError):
            ManifestFile.from_dict({"path": "x", "sha256": "dead", "size": 0})

    def test_rejects_nonhex_hash(self) -> None:
        with pytest.raises(ManifestError):
            ManifestFile.from_dict({"path": "x", "sha256": "z" * 64, "size": 0})


class TestSignAndVerify:
    def _write_signed(self, tmp_path: Path, keypair) -> tuple[Path, Ed25519PrivateKey]:
        signer, _ = keypair
        app = _make_app_tree(tmp_path, {"core/m.exe": b"payload"})
        man = generate_manifest(
            app, tool_version="1.2.0", config_version_expected="1.1"
        )
        man_path, _sig = write_manifest(tmp_path, man, signer)
        return man_path, signer

    def test_valid_signature_passes(self, tmp_path: Path, keypair) -> None:
        man_path, signer2 = self._write_signed(tmp_path, keypair)
        raw = man_path.read_bytes()
        sig = load_fs_signature(man_path)
        assert sig != b""
        pub = signer2.public_key()
        assert verify_signature(raw, sig, pub)

    def test_tampered_manifest_fails(self, tmp_path: Path, keypair) -> None:
        _, attacker = keypair
        man_path, _ = self._write_signed(tmp_path, keypair)
        raw = man_path.read_bytes()
        injected = json.loads(raw.decode())
        injected["tool_version"] = "9.9.9"
        tampered = (json.dumps(injected) + "\n").encode()
        sig = load_fs_signature(man_path)
        assert not verify_signature(tampered, sig, attacker.public_key())

    def test_wrong_key_fails(self, tmp_path: Path, keypair) -> None:
        _, attacker = keypair
        man_path, _ = self._write_signed(tmp_path, keypair)
        raw = man_path.read_bytes()
        sig = load_fs_signature(man_path)
        assert not verify_signature(raw, sig, attacker.public_key())
        with pytest.raises(InvalidSignature):
            attacker.public_key().verify(sig, raw)

    def test_missing_sig_fails_closed(self, tmp_path: Path, keypair) -> None:
        _, _attacker = keypair
        app = _make_app_tree(tmp_path, {"x.txt": b"x"})
        man = generate_manifest(app, tool_version="1", config_version_expected="1")
        man_path = tmp_path / "manifest.json"
        man_path.write_bytes(serialize_manifest(man))
        assert load_fs_signature(man_path) == b""


class TestVerifyFiles:
    def _manifest_for(self, tmp_path: Path, files: dict[str, bytes]) -> Manifest:
        app = _make_app_tree(tmp_path, files)
        return generate_manifest(app, tool_version="1", config_version_expected="1")

    def test_all_match(self, tmp_path: Path) -> None:
        man = self._manifest_for(tmp_path, {"a.bin": b"data", "core/x.exe": b"exe"})
        assert verify_files(tmp_path, man) == []

    def test_modified_file_detected(self, tmp_path: Path) -> None:
        man = self._manifest_for(tmp_path, {"a.bin": b"data"})
        (tmp_path / "app-1.2.0" / "a.bin").write_bytes(b"tampered")
        failing = verify_files(tmp_path, man)
        assert failing == ["app-1.2.0/a.bin"]

    def test_missing_file_detected(self, tmp_path: Path) -> None:
        man = self._manifest_for(tmp_path, {"a.bin": b"data", "b.bin": b"b"})
        (tmp_path / "app-1.2.0" / "b.bin").unlink()
        assert verify_files(tmp_path, man) == ["app-1.2.0/b.bin"]

    def test_malicious_manifest_path_rejected_at_verify(self, tmp_path: Path) -> None:
        # A crafted manifest attempting to check a path outside the root must
        # not be verifiable against files elsewhere in the filesystem.
        bad = Manifest(
            tool_version="1.0",
            config_version_expected="1.1",
            files=(ManifestFile(path="../../evil.txt", sha256="0" * 64, size=0),),
        )
        assert verify_files(tmp_path, bad) == ["../../evil.txt"]
        assert not (tmp_path.parent / "evil.txt").exists()

    def test_manifest_generation_quiet(self, tmp_path: Path) -> None:
        with patch.object(Logger, "info"):
            self._manifest_for(tmp_path, {"a.bin": b"data"})
