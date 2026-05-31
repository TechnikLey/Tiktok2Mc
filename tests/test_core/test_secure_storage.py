"""Tests for core.secure_storage"""

from pathlib import Path

import pytest

from core.secure_storage import SecureStorage, secure_storage


class TestSecureStorage:
    def test_singleton_identity(self):
        a = SecureStorage()
        b = SecureStorage()
        assert a is b

    def test_encrypt_decrypt_roundtrip(self):
        ss = SecureStorage()
        original = "my-super-secret-token"
        encrypted = ss.encrypt(original)
        assert encrypted != original
        decrypted = ss.decrypt(encrypted)
        assert decrypted == original

    def test_decrypt_plaintext_fallback(self):
        ss = SecureStorage()
        assert ss.decrypt("plain-text-value") == "plain-text-value"

    def test_encrypt_none_returns_none(self):
        ss = SecureStorage()
        assert ss.encrypt(None) is None
        assert ss.encrypt("") == ""

    def test_decrypt_none_returns_none(self):
        ss = SecureStorage()
        assert ss.decrypt(None) is None
        assert ss.decrypt("") == ""

    def test_key_file_created(self, tmp_path, monkeypatch):
        fake_root = tmp_path / "root"
        fake_root.mkdir()
        monkeypatch.setattr(
            "core.secure_storage._get_key_file",
            lambda: fake_root / "data" / ".enc_key",
        )
        ss = SecureStorage()
        ss._init()
        key_file = fake_root / "data" / ".enc_key"
        assert key_file.exists()
        assert key_file.stat().st_size > 0

    def test_module_singleton(self):
        assert secure_storage is SecureStorage()
