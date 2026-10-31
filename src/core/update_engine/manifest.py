"""Signed release manifests for the versioned update architecture.

A release ships a ``manifest.json`` next to ``manifest.json.sig``:

- ``manifest.json`` describes the version + per-file sha256/size entries.
- ``.sig`` is an Ed25519 *detached* signature over the exact bytes of the
  manifest file. Signing raw bytes avoids JSON canonicalization pitfalls.

Security model:

- The updater verifies the **signature first** using a public key embedded
  in the shipped code, then the **per-file checksums**. Any failure is
  fatal for the update (fail closed).
- All manifest paths are validated to be relative and contained in the
  install root, so a hostile manifest cannot direct file operations
  outside the target directory.

The public/private key pair is generated once by the release tooling
(``build.py``); the private key lives only in CI secrets, the public key is
embedded in the shipped updater/launcher code.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from logging import Logger, getLogger
from pathlib import Path, PurePosixPath

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

# NOTE: plain stdlib logger — see pointer.py for the import-time rationale.
from core.checksum import compute_sha256

log: Logger = getLogger(__name__)

MANIFEST_FILE: str = "manifest.json"
SIGNATURE_SUFFIX: str = ".sig"


class ManifestError(ValueError):
    """Raised when manifest data is structurally invalid."""


@dataclass(frozen=True)
class ManifestFile:
    """One file entry of a release manifest."""

    path: str
    sha256: str
    size: int

    def to_dict(self) -> dict[str, object]:
        """Return the JSON-friendly representation."""
        return {"path": self.path, "sha256": self.sha256, "size": self.size}

    @classmethod
    def from_dict(cls, data: object) -> ManifestFile:
        """Validate and build one entry from parsed JSON data."""
        if not isinstance(data, dict):
            msg = "manifest file entry must be an object"
            raise ManifestError(msg)
        path = data.get("path")
        sha256 = data.get("sha256")
        size = data.get("size")
        if not isinstance(path, str) or not path:
            msg = "manifest entry 'path' must be a non-empty string"
            raise ManifestError(msg)
        _validate_rel_path(path)
        if not isinstance(sha256, str) or len(sha256) != 64:
            msg = f"manifest entry 'sha256' invalid for {path!r}"
            raise ManifestError(msg)
        if not all(c in "0123456789abcdef" for c in sha256.lower()):
            msg = f"manifest entry 'sha256' not hex for {path!r}"
            raise ManifestError(msg)
        if not isinstance(size, int) or size < 0:
            msg = f"manifest entry 'size' must be a positive int for {path!r}"
            raise ManifestError(msg)
        return cls(path=path, sha256=sha256.lower(), size=size)


@dataclass(frozen=True)
class Manifest:
    """A validated release manifest."""

    tool_version: str
    config_version_expected: str
    files: tuple[ManifestFile, ...]
    updater_version: str = ""
    min_start_version: str = ""
    channel: str = "stable"
    created_utc: str = ""

    def to_dict(self) -> dict[str, object]:
        """Return the JSON-friendly representation."""
        return {
            "tool_version": self.tool_version,
            "updater_version": self.updater_version,
            "config_version_expected": self.config_version_expected,
            "min_start_version": self.min_start_version,
            "channel": self.channel,
            "created_utc": self.created_utc,
            "files": [entry.to_dict() for entry in self.files],
        }

    @classmethod
    def from_dict(cls, data: object) -> Manifest:
        """Validate and build a manifest from parsed JSON data."""
        if not isinstance(data, dict):
            msg = "manifest must be a JSON object"
            raise ManifestError(msg)

        def _require_str(name: str) -> str:
            value = data.get(name)
            if not isinstance(value, str) or not value:
                msg = f"manifest field '{name}' must be a non-empty string"
                raise ManifestError(msg)
            return value

        raw_files = data.get("files")
        if not isinstance(raw_files, list) or not raw_files:
            msg = "manifest field 'files' must be a non-empty list"
            raise ManifestError(msg)
        files = tuple(ManifestFile.from_dict(entry) for entry in raw_files)
        optional = {}
        for name in (
            "updater_version",
            "min_start_version",
            "channel",
            "created_utc",
        ):
            value = data.get(name)
            optional[name] = value if isinstance(value, str) else ""
        return cls(
            tool_version=_require_str("tool_version"),
            config_version_expected=_require_str("config_version_expected"),
            files=files,
            **optional,
        )


def _validate_rel_path(path: str) -> None:
    """Ensure *path* is a safe, relative POSIX-style path."""
    pure = PurePosixPath(path)
    if pure.is_absolute() or "\\" in path or ".." in pure.parts:
        msg = f"manifest path must be relative and POSIX-safe: {path!r}"
        raise ManifestError(msg)
    if len(PurePosixPath(path).parts) == 0:
        msg = "manifest path must not be empty"
        raise ManifestError(msg)


def serialize_manifest(manifest: Manifest) -> bytes:
    """Serialize *manifest* deterministically to the bytes that get signed."""
    text = json.dumps(manifest.to_dict(), indent=2, sort_keys=False)
    return (text + "\n").encode("utf-8")


def parse_manifest_bytes(raw: bytes) -> Manifest:
    """Parse and validate raw manifest bytes."""
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        msg = "manifest is not valid UTF-8 JSON"
        raise ManifestError(msg) from exc
    return Manifest.from_dict(data)


def generate_manifest(
    app_dir: Path,
    *,
    tool_version: str,
    config_version_expected: str,
    updater_version: str = "",
    min_start_version: str = "",
    channel: str = "stable",
    created_utc: str = "",
    prefix: str | None = None,
) -> Manifest:
    """Generate a manifest covering all files under *app_dir*.

    Paths are emitted **relative to the install root** using the directory
    name *prefix* (defaults to ``app_dir.name``, e.g. ``app-1.2.0``), with
    POSIX separators and sorted for reproducible output. This matches the
    verifier, which resolves entries against the install root.
    """
    app_dir = app_dir.resolve()
    base_prefix = prefix if prefix is not None else app_dir.name
    entries: list[ManifestFile] = []
    for file_path in sorted(app_dir.rglob("*")):
        if not file_path.is_file():
            continue
        rel = file_path.relative_to(app_dir)
        rel_posix = f"{base_prefix}/{PurePosixPath(*rel.parts).as_posix()}"
        _validate_rel_path(rel_posix)
        entries.append(
            ManifestFile(
                path=rel_posix,
                sha256=compute_sha256(file_path),
                size=file_path.stat().st_size,
            )
        )
    if not entries:
        msg = f"no files found under app dir to manifest: {app_dir}"
        raise ManifestError(msg)
    log.info(
        "Generated release manifest for app dir %s (%d files)",
        app_dir.name,
        len(entries),
    )
    return Manifest(
        tool_version=tool_version,
        config_version_expected=config_version_expected,
        files=tuple(entries),
        updater_version=updater_version,
        min_start_version=min_start_version,
        channel=channel,
        created_utc=created_utc,
    )


def sign_manifest_bytes(raw: bytes, private_key: Ed25519PrivateKey) -> bytes:
    """Return the detached Ed25519 signature over the exact manifest bytes."""
    return private_key.sign(raw)


def write_manifest(
    output_dir: Path, manifest: Manifest, private_key: Ed25519PrivateKey
) -> tuple[Path, Path]:
    """Write ``manifest.json`` and its detached signature under *output_dir*.

    Returns ``(manifest_path, signature_path)``.
    """
    raw = serialize_manifest(manifest)
    manifest_path = output_dir / MANIFEST_FILE
    sig_path = output_dir / (MANIFEST_FILE + SIGNATURE_SUFFIX)
    manifest_path.write_bytes(raw)
    sig_path.write_bytes(private_key.sign(raw))
    return manifest_path, sig_path


# ---------------------------------------------------------------------------
# Verification (updater side) — fail closed on anything unexpected.
# ---------------------------------------------------------------------------


def verify_signature(
    raw: bytes, signature: bytes, public_key: Ed25519PublicKey
) -> bool:
    """Check the detached signature of manifest bytes against *public_key*."""
    try:
        public_key.verify(signature, raw)
    except (InvalidSignature, ValueError) as exc:
        log.error("Manifest signature verification failed: %s", exc)
        return False
    return True


def load_fs_signature(manifest_path: Path) -> bytes:
    """Read the detached signature file belonging to *manifest_path*.

    Returns an empty ``bytes`` object when the signature file is missing so
    callers fail closed.
    """
    sig_path = manifest_path.with_name(manifest_path.name + SIGNATURE_SUFFIX)
    if not sig_path.is_file():
        log.error("Manifest signature file missing: %s", sig_path)
        return b""
    return sig_path.read_bytes()


def verify_files(root: Path, manifest: Manifest) -> list[str]:
    """Verify every manifest file under *root*.

    Returns the list of failing relative paths (missing file, size or
    sha256 mismatch). An empty list means all verified.
    """
    root = root.resolve()
    failing: list[str] = []
    for entry in manifest.files:
        target = (root / entry.path).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            log.error("Manifest path escapes target dir: %s", entry.path)
            failing.append(entry.path)
            continue
        if not target.is_file():
            log.error("Manifest file missing: %s", entry.path)
            failing.append(entry.path)
            continue
        if target.stat().st_size != entry.size:
            log.error("Manifest size mismatch: %s", entry.path)
            failing.append(entry.path)
            continue
        if compute_sha256(target) != entry.sha256:
            log.error("Manifest checksum mismatch: %s", entry.path)
            failing.append(entry.path)
    return failing
