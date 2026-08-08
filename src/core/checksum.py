"""Checksum verification helpers for downloaded artifacts.

Provides SHA-256 computation, verification, and fetching of companion
``.sha256`` files so that updates and plugin downloads can be
integrity-checked before extraction.
"""

from __future__ import annotations

import hashlib
import logging
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_USER_AGENT = "Tiktok2Mc-Updater/1.0"


def compute_sha256(path: Path) -> str:
    """Return the lower-case SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_checksum(path: Path, expected: str | None) -> bool:
    """Verify *path* against an expected SHA-256 hex digest.

    Returns ``True`` when the checksum matches or when *expected* is
    ``None``/empty.  Logs a warning and returns ``False`` on mismatch.
    """
    if not expected:
        return True
    actual = compute_sha256(path)
    if actual == expected.lower().strip():
        log.info("Checksum verified for %s", path.name)
        return True
    log.error(
        "Checksum mismatch for %s: expected %s, got %s",
        path.name,
        expected,
        actual,
    )
    return False


def fetch_checksum(url: str) -> str | None:
    """Try to fetch a SHA-256 checksum from a companion URL.

    Tries ``{url}.sha256`` first, then ``{url}.checksum``.
    Returns the expected hex digest or ``None``.
    """
    for suffix in (".sha256", ".checksum"):
        try:
            req = urllib.request.Request(
                url + suffix,
                headers={"User-Agent": _USER_AGENT},
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = resp.read().decode("utf-8").strip()
                for line in body.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split()
                    if parts:
                        candidate = parts[0].lower()
                        if len(candidate) == 64 and all(
                            c in "0123456789abcdef" for c in candidate
                        ):
                            return candidate
                return None
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                log.debug("Checksum fetch failed for %s: %s", url + suffix, exc)
        except urllib.error.URLError as exc:
            log.debug("Checksum fetch failed for %s: %s", url + suffix, exc)
    return None


def find_checksum_asset_url(assets: list[dict[str, Any]], filename: str) -> str | None:
    """Search a GitHub release asset list for a matching ``.sha256`` file.

    Returns the download URL of the checksum asset, or ``None``.
    """
    name_lower = filename.lower()
    for asset in assets:
        aname = asset.get("name", "").lower()
        if aname == name_lower + ".sha256":
            return asset.get("url", "")
        if aname in ("sha256sums", "sha256sums.txt"):
            return asset.get("url", "")
    return None
