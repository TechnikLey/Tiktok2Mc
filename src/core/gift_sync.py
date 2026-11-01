"""Automatic gift catalog synchronization (TikTok gift ID → name database).

The gift catalog (``gifts.json``: ``name`` / ``coins`` / ``id`` entries)
powers the trigger editor's gift dropdown and the actions-parse context.
The shipped catalog is a static snapshot and drifts as TikTok adds or
renames gifts. This module keeps it current:

- **Primary source:** the official live-gift endpoint TikTok's own web
  client uses (``webcast.tiktok.com/webcast/gift/list/``) — the same
  endpoint the TikTokLive library hits. No auth or signature required;
  the full browser-like parameter set is needed (minimal requests may
  return an empty body on some edges).
- **Fallback source:** the ``antiops/tiktok-trending-data`` GitHub
  mirror of the same data (independent availability risk: a third-party
  scraper, freshness depends on its update schedule).

Update semantics (user decision, 2026-11-01): the fetched catalog
**overwrites** the runtime file completely (``core/gifts.json``) — the
factory template (``defaults/gifts.json``) is never touched, so the
shipped baseline always remains as fallback. A centralized backup of the
previous catalog is created before overwriting (best-effort).

The catalog file is a *runtime artifact* by design: the actions route
already resolves ``core/gifts.json`` with a ``defaults/gifts.json``
fallback, so visuals/consumers need no changes.
"""

from __future__ import annotations

import json
import os
import uuid
from logging import Logger, getLogger
from pathlib import Path

import requests

# NOTE: plain stdlib logger — no filesystem work at import time (tests).
log: Logger = getLogger(__name__)


class GiftSyncError(RuntimeError):
    """Raised when no configured source could provide a gift catalog."""


OFFICIAL_URL = "https://webcast.tiktok.com/webcast/gift/list/"
OFFICIAL_PARAMS = {
    "aid": "1988",
    "app_language": "en-US",
    "app_name": "tiktok_web",
    "browser_language": "en-US",
    "browser_name": "Mozilla",
    "browser_online": "true",
    "browser_platform": "Win32",
    "browser_version": "5.0 (Windows NT 10.0; Win64; x64)",
    "channel": "tiktok_web",
    "cookie_enabled": "true",
    "device_platform": "web_pc",
    "region": "US",
    "tz_name": "UTC",
    "webcast_language": "en-US",
}
OFFICIAL_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Encoding": "gzip",
    "Referer": "https://www.tiktok.com/",
}

FALLBACK_URL = (
    "https://raw.githubusercontent.com/antiops/tiktok-trending-data/"
    "main/live-gift-details.json"
)

_SYNC_ATTEMPTS = 3
_RETRY_DELAY_SECONDS = 2.0


# ---------------------------------------------------------------------------
# Fetchers — each returns a raw list of gift entries or raises GiftSyncError.
# ---------------------------------------------------------------------------
def fetch_official_gifts(timeout: float = 20.0) -> list[dict]:
    """Fetch and unwrap the official ``webcast/gift/list`` response.

    Retries a few times: some TikTok edges return HTTP 200 with an empty
    body intermittently.
    """
    import time

    last_error = "unknown error"
    for attempt in range(1, _SYNC_ATTEMPTS + 1):
        try:
            response = requests.get(
                OFFICIAL_URL,
                params=OFFICIAL_PARAMS,
                headers=OFFICIAL_HEADERS,
                timeout=timeout,
            )
            response.raise_for_status()
            if not response.content:
                # Observed edge behavior: HTTP 200 with an empty body.
                last_error = "official endpoint returned an empty body"
                log.debug("Gift catalog fetch: %s (attempt %d)", last_error, attempt)
            else:
                payload = response.json()
                gifts = (payload.get("data") or {}).get("gifts")
                if isinstance(gifts, list) and gifts:
                    return gifts
                last_error = "official endpoint payload has no gift list"
        except (requests.RequestException, ValueError) as exc:
            last_error = str(exc)
            log.debug("Gift catalog fetch failed (attempt %d): %s", attempt, exc)
        if attempt < _SYNC_ATTEMPTS:
            time.sleep(_RETRY_DELAY_SECONDS)
    raise GiftSyncError(f"Official gift endpoint failed: {last_error}")


def fetch_fallback_gifts(timeout: float = 20.0) -> list[dict]:
    """Fetch the antiops GitHub mirror (same data, third-party source)."""
    try:
        response = requests.get(FALLBACK_URL, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise GiftSyncError(f"Fallback gift mirror failed: {exc}") from exc
    # The mirror has changed shape over time: current format is a
    # top-level list; accept the official ``data.gifts`` shape as well.
    if isinstance(payload, list):
        gifts = payload
    elif isinstance(payload, dict) and isinstance(payload.get("data"), dict):
        gifts = payload["data"].get("gifts")
    else:
        gifts = None
    if not isinstance(gifts, list) or not gifts:
        raise GiftSyncError("Fallback gift mirror: unexpected / no gift list")
    return gifts


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------
def normalize_entries(raw_entries: list) -> list[dict]:
    """Convert source entries into catalog rows ``{name, coins, id}``.

    Skips entries without an integer id or a non-empty name; later
    duplicates of the same id win (sources keep the last definition).
    Output is deterministically sorted by ``(coins, name, id)``.
    """
    catalog: dict[int, dict] = {}
    for entry in raw_entries:
        if not isinstance(entry, dict):
            continue
        try:
            gift_id = int(entry.get("id"))
        except (TypeError, ValueError):
            continue
        name = str(entry.get("name") or "").strip()
        if not name:
            continue
        try:
            coins = int(entry.get("diamond_count") or entry.get("coins") or 0)
        except (TypeError, ValueError):
            coins = 0
        catalog[gift_id] = {"name": name, "coins": coins, "id": gift_id}
    return sorted(
        catalog.values(), key=lambda g: (g["coins"], g["name"].lower(), g["id"])
    )


def read_catalog(catalog_file: Path) -> list[dict]:
    """Read a local gifts.json catalog; invalid/missing files read as ``[]``."""
    try:
        data = json.loads(catalog_file.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
        log.warning("Could not read gift catalog %s: %s", catalog_file, exc)
        return []
    return data if isinstance(data, list) else []


def diff_catalogs(old_entries: list[dict], new_entries: list[dict]) -> dict[str, int]:
    """Compare two catalogs by gift id for the sync summary."""
    old_ids = {g.get("id") for g in old_entries if isinstance(g, dict)}
    new_ids = {g.get("id") for g in new_entries if isinstance(g, dict)}
    old_names = {
        g.get("id"): g.get("name")
        for g in old_entries
        if isinstance(g, dict) and g.get("id") is not None
    }
    renamed = sum(
        1
        for g in new_entries
        if isinstance(g, dict)
        and old_names.get(g.get("id")) not in (None, g.get("name"))
    )
    return {
        "added": len(new_ids - old_ids),
        "removed": len(old_ids - new_ids),
        "renamed": renamed,
    }


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------
def write_catalog(catalog_file: Path, entries: list[dict]) -> None:
    """Atomically replace the catalog file (tmp sibling + ``os.replace``)."""
    catalog_file = Path(catalog_file)
    catalog_file.parent.mkdir(parents=True, exist_ok=True)
    tmp_file = catalog_file.with_name(f".{catalog_file.name}.{uuid.uuid4().hex}.tmp")
    try:
        with tmp_file.open("w", encoding="utf-8") as fh:
            json.dump(entries, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        os.replace(tmp_file, catalog_file)
    finally:
        if tmp_file.exists():
            try:
                tmp_file.unlink()
            except OSError:  # pragma: no cover - best-effort cleanup
                pass


def _backup_existing(catalog_file: Path) -> None:
    """Centralized backup of the previous catalog (best-effort, tolerated)."""
    try:
        from core.backup import get_backup_manager

        manager = get_backup_manager()
        if manager is not None:
            path = manager.create_backup(catalog_file, category="gifts")
            if path:
                log.info("Previous gift catalog backed up: %s", path)
    except Exception as exc:  # noqa: BLE001 - backup must never block a sync
        log.warning("Gift catalog backup skipped: %s", exc)


def sync_gifts(
    target_file: Path | None = None,
    *,
    source: str = "auto",
    timeout: float = 20.0,
) -> dict:
    """Refresh the gift catalog from the configured source chain.

    ``source``: ``auto`` (official → fallback), ``official`` or
    ``fallback``. The fetched catalog fully replaces the file at
    *target_file* (default: :func:`core.paths.get_gifts_file`); the
    factory template is never modified. A backup of the previous file is
    created through the centralized BackupManager (best-effort).

    Returns a summary dict: ``ok / source / total / added / removed /
    renamed / target``.
    """
    if target_file is None:
        from core.paths import get_gifts_file

        target_file = get_gifts_file()

    if source == "fallback":
        fetchers = [fetch_fallback_gifts]
    elif source == "official":
        fetchers = [fetch_official_gifts]
    else:
        fetchers = [fetch_official_gifts, fetch_fallback_gifts]

    used_source = None
    raw_entries = None
    errors: list[str] = []
    for fetcher, name in zip(fetchers, ("official", "fallback"), strict=False):
        try:
            raw_entries = fetcher(timeout=timeout)
            used_source = name
            break
        except GiftSyncError as exc:
            errors.append(str(exc))
            log.warning("Gift sync: %s", exc)
    if raw_entries is None:
        return {
            "ok": False,
            "error": " | ".join(errors),
            "source": source,
            "target": str(target_file),
        }

    new_entries = normalize_entries(raw_entries)
    if not new_entries:
        return {
            "ok": False,
            "error": "fetched payload contained no usable gift entries",
            "source": used_source,
            "target": str(target_file),
        }

    old_entries = read_catalog(target_file)
    diff = diff_catalogs(old_entries, new_entries)

    if target_file.exists():
        _backup_existing(target_file)
    write_catalog(target_file, new_entries)
    log.info(
        "Gift catalog synced from %s: %d gifts (+%d/-%d, %d renamed) → %s",
        used_source,
        len(new_entries),
        diff["added"],
        diff["removed"],
        diff["renamed"],
        target_file,
    )
    return {
        "ok": True,
        "source": used_source,
        "total": len(new_entries),
        "added": diff["added"],
        "removed": diff["removed"],
        "renamed": diff["renamed"],
        "target": str(target_file),
    }
