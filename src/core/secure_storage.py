"""Encrypted local storage for sensitive configuration values.

Uses Fernet symmetric encryption with a key persisted in
``data/.enc_key``.  The key itself is derived from random material
and is **not** tied to machine identifiers so that backups and
config migrations remain portable.

If the ``cryptography`` library is not installed a simple obfuscation
fallback is used with a logged warning.
"""

from __future__ import annotations

import base64
import logging
import os
from pathlib import Path
from typing import Self

log = logging.getLogger(__name__)

try:
    from cryptography.fernet import Fernet, InvalidToken
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    _HAS_CRYPTOGRAPHY = True
except ImportError:  # pragma: no cover
    _HAS_CRYPTOGRAPHY = False
    log.warning(
        "cryptography not installed — sensitive values will be obfuscated "
        "but NOT strongly encrypted.  Install 'cryptography' for real security."
    )


def _get_key_file() -> Path:
    from core.paths import get_root_dir

    return get_root_dir() / "data" / ".enc_key"


def _load_or_create_key() -> bytes:
    key_file = _get_key_file()
    if key_file.exists():
        return key_file.read_bytes()

    if _HAS_CRYPTOGRAPHY:
        # Generate a fresh random key via PBKDF2 so we have a
        # standard 32-byte base64-encoded Fernet key.
        salt = os.urandom(16)
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100_000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(os.urandom(32)))
    else:
        # Fallback: 32-byte key derived from randomness
        key = base64.urlsafe_b64encode(os.urandom(32))

    key_file.parent.mkdir(parents=True, exist_ok=True)
    key_file.write_bytes(key)
    # Restrict permissions: owner read/write only (best-effort)
    try:
        os.chmod(key_file, 0o600)
    except OSError:
        pass
    return key


class SecureStorage:
    """Encrypt and decrypt small strings (e.g. API secrets, tokens)."""

    _instance: Self | None = None

    def __new__(cls) -> Self:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self) -> None:
        key = _load_or_create_key()
        if _HAS_CRYPTOGRAPHY:
            self._fernet = Fernet(key)
        else:
            self._fernet = None
            self._key = base64.urlsafe_b64decode(key)

    def encrypt(self, value: str | None) -> str | None:
        if not value:
            return value
        if self._fernet is not None:
            return self._fernet.encrypt(value.encode("utf-8")).decode("utf-8")
        # Fallback XOR obfuscation
        data = value.encode("utf-8")
        key = self._key
        obf = bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
        return base64.urlsafe_b64encode(obf).decode("utf-8")

    def decrypt(self, value: str | None) -> str | None:
        if not value:
            return value
        if self._fernet is not None:
            try:
                return self._fernet.decrypt(value.encode("utf-8")).decode("utf-8")
            except (InvalidToken, ValueError):  # fall through to obfuscation fallback
                pass
        # Try fallback
        if hasattr(self, "_key") and self._key is not None:
            try:
                obf = base64.urlsafe_b64decode(value.encode("utf-8"))
                key = self._key
                data = bytes(b ^ key[i % len(key)] for i, b in enumerate(obf))
                return data.decode("utf-8")
            except ValueError:  # fall back to plaintext (backward compatibility)
                pass
        # Final fallback: assume plaintext (backward compatibility)
        return value


# Module-level singleton
secure_storage = SecureStorage()
