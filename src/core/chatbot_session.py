"""Encrypted storage for the TikTok chatbot session credentials.

The ``sessionid`` cookie is as valuable as a password (full account
takeover), so it is **never** written to a YAML file or log.  It is
stored Fernet-encrypted (via :mod:`core.secure_storage`) in
``data/chatbot_session.json`` together with the optional
``tt-target-idc`` data-center hint.

The bridge reads these credentials before each client connect and calls
``client.web.set_session(session_id, tt_target_idc)`` — see
:func:`TikTokChatbot.apply_session_to_client`.
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Iterable
from typing import Any

import core.paths
from core.crash_manager import get_crash_manager
from core.error_codes import CHATBOT_0004
from core.secure_storage import secure_storage

log = logging.getLogger(__name__)

# Reasonable bounds for the sessionid cookie value (TikTok uses ~32-64
# alphanumeric characters; the range is deliberately generous).
SESSION_ID_MIN_LEN = 10
SESSION_ID_MAX_LEN = 512

# tt-target-idc values look like "va", "maliva", "useast2a" or "eu-ttp2".
_TT_TARGET_IDC_RE = re.compile(r"^[A-Za-z0-9-]{0,64}$")
_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_%-]+$")

MASK_PREFIX = 4
MASK_SUFFIX = 4


class SessionValidationError(ValueError):
    """Raised when a user-supplied session credential is malformed."""


def validate_session_id(session_id: str) -> str:
    """Normalize and validate a raw session id; raises on bad input."""
    sid = str(session_id).strip()
    if not (SESSION_ID_MIN_LEN <= len(sid) <= SESSION_ID_MAX_LEN):
        raise SessionValidationError(
            f"session_id must be {SESSION_ID_MIN_LEN}-{SESSION_ID_MAX_LEN} characters"
        )
    if not _SESSION_ID_RE.fullmatch(sid):
        raise SessionValidationError("session_id contains invalid characters")
    return sid


def validate_tt_target_idc(tt_target_idc: str | None) -> str:
    """Normalize the optional data-center hint; raises on bad input."""
    idc = str(tt_target_idc or "").strip()
    if not _TT_TARGET_IDC_RE.fullmatch(idc):
        raise SessionValidationError("tt_target_idc contains invalid characters")
    return idc


def mask_session_id(session_id: str | None) -> str | None:
    """Return a display-safe preview like ``abcd…wxyz``."""
    if not session_id:
        return None
    if len(session_id) <= MASK_PREFIX + MASK_SUFFIX:
        return "…" + session_id[-MASK_SUFFIX:]
    return f"{session_id[:MASK_PREFIX]}…{session_id[-MASK_SUFFIX:]}"


def save_chatbot_session(
    session_id: str, tt_target_idc: str | None = None
) -> dict[str, Any]:
    """Encrypt and persist the credentials; returns the public info dict."""
    sid = validate_session_id(session_id)
    idc = validate_tt_target_idc(tt_target_idc)

    record: dict[str, Any] = {
        "sessionid": secure_storage.encrypt(sid),
        "tt_target_idc": idc,
        "updated": time.time(),
    }
    path = core.paths.get_chatbot_session_file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record), encoding="utf-8")
    except OSError as exc:
        get_crash_manager().report_error(
            CHATBOT_0004, detail=f"{type(exc).__name__}: {exc}"
        )
        raise

    log.info("[CHATBOT-SESSION] Stored session credentials (%s)", path.name)
    return get_chatbot_session_info()


def load_chatbot_session() -> tuple[str, str] | None:
    """Return ``(session_id, tt_target_idc)`` or ``None`` when absent/invalid."""
    path = core.paths.get_chatbot_session_file()
    if not path.exists():
        return None
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log.warning("[CHATBOT-SESSION] Unreadable session store: %s", exc)
        return None
    if not isinstance(record, dict):
        return None
    encrypted = record.get("sessionid")
    sid = secure_storage.decrypt(encrypted) if isinstance(encrypted, str) else None
    if not sid:
        return None
    return sid, str(record.get("tt_target_idc") or "")


def clear_chatbot_session() -> bool:
    """Delete stored credentials; returns True when something was removed."""
    path = core.paths.get_chatbot_session_file()
    try:
        existed = path.exists()
        path.unlink(missing_ok=True)
    except OSError as exc:
        get_crash_manager().report_error(
            CHATBOT_0004, detail=f"{type(exc).__name__}: {exc}"
        )
        raise
    if existed:
        log.info("[CHATBOT-SESSION] Cleared session credentials")
    return existed


def get_chatbot_session_info() -> dict[str, Any]:
    """Public (secret-free) view for the API/GUI."""
    path = core.paths.get_chatbot_session_file()
    if not path.exists():
        return {
            "configured": False,
            "masked_session_id": None,
            "tt_target_idc": "",
            "updated": None,
        }
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        record = {}
    if not isinstance(record, dict):
        record = {}
    encrypted = record.get("sessionid")
    sid = secure_storage.decrypt(encrypted) if isinstance(encrypted, str) else None
    updated = record.get("updated")
    return {
        "configured": bool(sid),
        "masked_session_id": mask_session_id(sid),
        "tt_target_idc": str(record.get("tt_target_idc") or ""),
        "updated": float(updated) if isinstance(updated, (int, float)) else None,
    }


def extract_session_cookies(cookies: Iterable[Any]) -> tuple[str, str] | None:
    """Extract ``(session_id, tt_target_idc)`` from webview cookies.

    Accepts :class:`http.cookiejar.Cookie` objects (what pywebview's
    ``Window.get_cookies()`` returns) or plain ``{"name", "value"}``
    dicts.  Returns None when no ``sessionid`` cookie is present —
    i.e. the user is not logged in yet.
    """
    session_id = ""
    tt_target_idc = ""
    for cookie in cookies:
        if isinstance(cookie, dict):
            name = str(cookie.get("name") or "")
            value = str(cookie.get("value") or "")
        else:
            name = str(getattr(cookie, "name", "") or "")
            value = str(getattr(cookie, "value", "") or "")
        if name == "sessionid" and value and not session_id:
            session_id = value
        elif name == "tt-target-idc" and value and not tt_target_idc:
            tt_target_idc = value
    if not session_id:
        return None
    return session_id, tt_target_idc


def request_bridge_reload() -> bool:
    """Drop the ``reload_chatbot`` runtime signal for the bridge.

    Shared by the API routes and the GUI process (webview login) so a
    saved session/config is picked up without a restart.
    """
    signal = core.paths.get_runtime_dir() / "reload_chatbot"
    try:
        signal.parent.mkdir(parents=True, exist_ok=True)
        signal.write_text("reload", encoding="utf-8")
        return True
    except OSError as exc:
        log.warning("[CHATBOT-SESSION] Failed to write reload signal: %s", exc)
        return False
