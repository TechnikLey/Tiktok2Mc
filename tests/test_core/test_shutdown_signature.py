"""Tests for the shutdown signature module (HMAC signing of shutdown requests)."""

import json
import time

import pytest

from core.api.shutdown_signature import (
    HDR_IDENTITY,
    HDR_NONCE,
    HDR_SIGNATURE,
    HDR_TIMESTAMP,
    audit_shutdown_attempt,
    ensure_secret,
    make_headers,
    read_secret,
    verify_headers,
)


@pytest.fixture(autouse=True)
def _dummy_fixture():
    """Filler to keep pytest happy when the module has fixture imports."""


class TestSecret:
    def test_ensure_secret_persists(self, project_dir):
        secret = ensure_secret()
        assert len(secret) >= 32
        # Second call returns the same persisted secret
        assert ensure_secret() == secret
        stored = (
            (project_dir / "core" / "runtime" / "shutdown_secret")
            .read_text(encoding="utf-8")
            .strip()
        )
        assert stored == secret

    def test_read_secret_matches_ensured(self, project_dir):
        ensure_secret()
        assert read_secret() == ensure_secret()

    def test_read_secret_none_when_missing(self, project_dir):
        # project_dir has a fresh runtime dir per test; no secret yet
        assert read_secret() is None


class TestSigningAndVerify:
    def test_make_headers_empty_without_secret(self, project_dir):
        assert make_headers("gui.py:stop_system") == {}

    def test_make_headers_include_fields_after_secret(self, project_dir):
        ensure_secret()
        headers = make_headers("gui.py:stop_system")
        assert set(headers) == {
            HDR_TIMESTAMP,
            HDR_NONCE,
            HDR_IDENTITY,
            HDR_SIGNATURE,
        }

    def test_verify_ok_for_signed_request(self, project_dir):
        ensure_secret()
        headers = make_headers("gui.py:stop_system")
        ok, reason = verify_headers(headers, method="POST")
        assert ok is True
        assert reason == "ok"

    def test_verify_rejects_missing_headers(self, project_dir):
        ensure_secret()
        ok, reason = verify_headers({}, method="POST")
        assert ok is False
        assert reason == "missing timestamp"

    def test_verify_rejects_bad_signature(self, project_dir):
        ensure_secret()
        headers = make_headers("gui.py:stop_system")
        headers[HDR_SIGNATURE] = "0" * 64
        ok, reason = verify_headers(headers, method="POST")
        assert ok is False
        assert reason == "signature mismatch"

    def test_verify_rejects_replay(self, project_dir):
        ensure_secret()
        headers = make_headers("gui.py:stop_system")
        assert verify_headers(headers, method="POST") == (True, "ok")
        assert verify_headers(headers, method="POST") == (False, "nonce replay")

    def test_verify_rejects_fresh_nonce_after_window(self, project_dir):
        ensure_secret()
        base = make_headers("gui.py:stop_system")
        # artificially age the nonce out of the cache
        from core.api.shutdown_signature import _nonce_cache

        _nonce_cache.pop(base[HDR_NONCE], None)
        assert verify_headers(base, method="POST") == (True, "ok")

    def test_verify_rejects_expired_timestamp(self, project_dir):
        ensure_secret()
        headers = make_headers("gui.py:stop_system")
        headers[HDR_TIMESTAMP] = str(int(time.time()) - 7200)
        ok, reason = verify_headers(headers, method="POST")
        assert ok is False
        assert "timestamp" in reason

    def test_verify_rejects_wrong_path(self, project_dir):
        ensure_secret()
        headers = make_headers("gui.py:stop_system")
        ok, reason = verify_headers(headers, method="POST", path="/api/v1/other")
        assert ok is False
        assert reason == "signature mismatch"


class TestAudit:
    def test_audit_writes_jsonl_line(self, project_dir, tmp_path):
        audit_shutdown_attempt({"verdict": "accepted", "client": "127.0.0.1"})
        audit_path = project_dir / "data" / "diagnostics" / "shutdown_audit.jsonl"
        assert audit_path.exists()
        lines = audit_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["verdict"] == "accepted"
        assert "timestamp" in entry
