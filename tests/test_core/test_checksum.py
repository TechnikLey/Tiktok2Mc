"""Tests for core.checksum"""

import hashlib
from pathlib import Path

from core.checksum import (
    compute_sha256,
    find_checksum_asset_url,
    verify_checksum,
)


class TestComputeSha256:
    def test_empty_file(self, tmp_path: Path):
        empty = tmp_path / "empty.txt"
        empty.write_text("")
        assert compute_sha256(empty) == hashlib.sha256(b"").hexdigest()

    def test_known_content(self, tmp_path: Path):
        f = tmp_path / "hello.txt"
        f.write_text("hello")
        expected = hashlib.sha256(b"hello").hexdigest()
        assert compute_sha256(f) == expected


class TestVerifyChecksum:
    def test_no_expected_fails_closed(self, tmp_path: Path, caplog):
        import logging

        f = tmp_path / "a.txt"
        f.write_text("x")
        with caplog.at_level(logging.ERROR):
            assert verify_checksum(f, None) is False
            assert verify_checksum(f, "") is False
        assert "no expected digest" in caplog.text

    def test_matching_checksum(self, tmp_path: Path):
        f = tmp_path / "a.txt"
        f.write_text("hello")
        expected = hashlib.sha256(b"hello").hexdigest()
        assert verify_checksum(f, expected) is True

    def test_mismatching_checksum(self, tmp_path: Path, caplog):
        import logging

        f = tmp_path / "a.txt"
        f.write_text("hello")
        with caplog.at_level(logging.ERROR):
            result = verify_checksum(f, "a" * 64)
        assert result is False
        assert "Checksum mismatch" in caplog.text


class TestFindChecksumAssetUrl:
    def test_exact_match(self):
        assets = [{"name": "plugin.zip.sha256", "url": "http://example.com/c"}]
        assert find_checksum_asset_url(assets, "plugin.zip") == "http://example.com/c"

    def test_no_match(self):
        assets = [{"name": "other.txt", "url": "http://example.com/c"}]
        assert find_checksum_asset_url(assets, "plugin.zip") is None

    def test_sha256sums_fallback(self):
        assets = [{"name": "SHA256SUMS", "url": "http://example.com/s"}]
        assert find_checksum_asset_url(assets, "anything.zip") == "http://example.com/s"
