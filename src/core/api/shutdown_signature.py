"""Signature-protected shutdown endpoint support.

The GUI signs shutdown requests with an HMAC-SHA256 MAC derived from a
per-install secret that the API writes to the runtime directory at
startup.  Every attempt — accepted *and* rejected — is recorded in a
persistent JSONL audit file (``data/diagnostics/shutdown_audit.jsonl``)
and logged with the full request context, so the actual caller can always
be identified afterwards, even if the request is refused.

Request headers
---------------
``X-Shutdown-Timestamp`` : unix epoch seconds (window ±600 s)
``X-Shutdown-Nonce``     : random hex, replay-protection
``X-Shutdown-Identity``  : self-identified caller, e.g. ``gui.py:stop_system``
``X-Shutdown-Signature`` : hex HMAC-SHA256 over a canonical string

The canonical string signed is::

    <METHOD>\n<path>\n<timestamp>\n<nonce>\n<identity>
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
import threading
import time
from pathlib import Path
from typing import Any

from core.paths import get_root_dir, get_runtime_dir

log = logging.getLogger(__name__)

HDR_TIMESTAMP = "X-Shutdown-Timestamp"
HDR_NONCE = "X-Shutdown-Nonce"
HDR_IDENTITY = "X-Shutdown-Identity"
HDR_SIGNATURE = "X-Shutdown-Signature"

SECRET_FILE = "shutdown_secret"
AUDIT_FILE = "shutdown_audit.jsonl"

# Requests must be signed within this window (seconds).
TIMESTAMP_WINDOW_S = 600

# Replay cache: keep nonces for the timestamp window.
_nonce_cache: dict[str, float] = {}
_nonce_lock = threading.Lock()

# The identity header is only meaningful inside the signed payload; the
# canonical string makes it impossible to claim a foreign identity without
# knowing the shared secret.
_SERVICE_PATH = "/api/v1/shutdown/now"


def _secret_path() -> Path:
    return get_runtime_dir() / SECRET_FILE


def _audit_path() -> Path:
    return get_root_dir() / "data" / "diagnostics" / AUDIT_FILE


# ---------------------------------------------------------------------------
# Secret management
# ---------------------------------------------------------------------------


def ensure_secret() -> str:
    """Return the per-install shutdown secret, creating it when missing."""
    path = _secret_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        log.warning(
            "[SHUTDOWN-AUTH] Could not create secret dir (%s); "
            "ephemeral secret used — restart may invalidate signatures.",
            exc,
        )
        return secrets.token_hex(32)

    try:
        existing = path.read_text(encoding="utf-8").strip()
        if len(existing) >= 32:
            return existing
    except FileNotFoundError:
        pass
    except OSError as exc:
        log.warning(
            "[SHUTDOWN-AUTH] Could not read shutdown secret (%s); "
            "ephemeral secret used.",
            exc,
        )
        return secrets.token_hex(32)

    secret = secrets.token_hex(32)
    try:
        path.write_text(secret, encoding="utf-8")
        _restrict_permissions(path)
        return secret
    except OSError as exc:
        log.warning(
            "[SHUTDOWN-AUTH] Could not persist shutdown secret (%s); "
            "ephemeral secret used — restart may invalidate signatures.",
            exc,
        )
        return secrets.token_hex(32)


def read_secret() -> str | None:
    """Read the persisted shutdown secret (used by the GUI to sign)."""
    try:
        return _secret_path().read_text(encoding="utf-8").strip() or None
    except OSError as exc:
        log.debug("[SHUTDOWN-AUTH] Secret not available yet: %s", exc)
        return None


def _restrict_permissions(path: Path) -> None:
    if os.name == "posix":
        try:
            path.chmod(0o600)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Signing
# ---------------------------------------------------------------------------


def _canonical(
    method: str, path: str, timestamp: str, nonce: str, identity: str
) -> str:
    return "\n".join((method.upper(), path, timestamp, nonce, identity))


def _sign(
    secret: str, *, method: str, path: str, timestamp: str, nonce: str, identity: str
) -> str:
    mac = hmac.new(
        secret.encode("utf-8"),
        _canonical(method, path, timestamp, nonce, identity).encode("utf-8"),
        hashlib.sha256,
    )
    return mac.hexdigest()


def make_headers(
    identity: str, *, method: str = "POST", path: str = ""
) -> dict[str, str]:
    """Build the signature headers for a shutdown request (GUI side)."""
    secret = read_secret()
    if secret is None:
        return {}
    path = path or _SERVICE_PATH
    timestamp = str(int(time.time()))
    nonce = secrets.token_hex(16)
    signature = _sign(
        secret,
        method=method,
        path=path,
        timestamp=timestamp,
        nonce=nonce,
        identity=identity,
    )
    return {
        HDR_TIMESTAMP: timestamp,
        HDR_NONCE: nonce,
        HDR_IDENTITY: identity,
        HDR_SIGNATURE: signature,
    }


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


def _consume_nonce(nonce: str) -> bool:
    """Return True if the nonce is fresh (and now consumed)."""
    now = time.time()
    with _nonce_lock:
        expiry = now - TIMESTAMP_WINDOW_S
        stale = [n for n, t in _nonce_cache.items() if t < expiry]
        for n in stale:
            del _nonce_cache[n]
        if nonce in _nonce_cache:
            return False
        _nonce_cache[nonce] = now
        return True


def verify_headers(
    headers: Any,
    *,
    method: str = "POST",
    path: str = "",
) -> tuple[bool, str]:
    """Verify the signature headers on a shutdown request.

    Returns ``(ok, reason)``.  *headers* is any mapping with a ``get``
    method (FastAPI ``Request.headers``, plain dict).
    """
    path = path or _SERVICE_PATH

    ts_raw = headers.get(HDR_TIMESTAMP, "")
    nonce = headers.get(HDR_NONCE, "")
    identity = headers.get(HDR_IDENTITY, "")
    signature = headers.get(HDR_SIGNATURE, "")

    if not ts_raw:
        return False, "missing timestamp"
    if not nonce:
        return False, "missing nonce"
    if not identity:
        return False, "missing identity"
    if not signature:
        return False, "missing signature"

    try:
        ts = int(ts_raw)
    except (TypeError, ValueError):
        return False, "invalid timestamp"
    now = int(time.time())
    if abs(now - ts) > TIMESTAMP_WINDOW_S:
        return False, "timestamp out of window"

    secret = read_secret()
    if secret is None:
        return False, "no persisted secret available"

    expected = _sign(
        secret,
        method=method,
        path=path,
        timestamp=ts_raw,
        nonce=nonce,
        identity=identity,
    )
    if not hmac.compare_digest(expected, signature.lower()):
        return False, "signature mismatch"

    if not _consume_nonce(nonce):
        return False, "nonce replay"

    return True, "ok"


# ---------------------------------------------------------------------------
# Persistent audit log
# ---------------------------------------------------------------------------


def audit_shutdown_attempt(record: dict[str, Any]) -> None:
    """Append a JSON line for one shutdown attempt (accepted or rejected).

    Never raises — a failed audit write must not disturb the shutdown flow.
    """
    if "timestamp" not in record:
        record["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    try:
        path = _audit_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    except OSError as exc:
        log.debug("[SHUTDOWN-AUTH] Audit write failed: %s", exc)
