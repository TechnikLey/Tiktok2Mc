"""In-memory session aggregation and background persistence.

Event handlers only mutate this object's in-memory counters.  A daemon writer
thread periodically flushes snapshots to :mod:`core.analytics.store`, so a
slow disk or a burst of TikTok events never blocks the bridge's event loop.
"""

from __future__ import annotations

import copy
import logging
import threading
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from core.analytics.config import AnalyticsConfig
from core.analytics.store import AnalyticsStore

log = logging.getLogger(__name__)

_OTHER_KEY = "__other__"
_UNKNOWN_KEY = "unknown"
_MAX_RAW_EVENTS = 5000


def _iso(timestamp: float) -> str:
    """Convert a Unix timestamp to an ISO 8601 UTC string."""
    return datetime.fromtimestamp(timestamp, UTC).isoformat(timespec="seconds")


def _normalise_username(value: object) -> str:
    """Return a lower-case username without a leading ``@``."""
    text = str(value or "").strip().lstrip("@").lower()
    return text


def _identity(
    user: object | None, fallback_username: str | None
) -> tuple[str, str | None, str, str]:
    """Derive ``(user_key, user_id, username, display_name)`` from a user object.

    A numeric account id is preferred because it survives username changes.
    Otherwise the normalised unique username is used.  Events without any
    identity land in the ``unknown`` bucket instead of being dropped.
    """
    user_id_raw = None
    unique_id = None
    nickname = None
    if user is not None:
        user_id_raw = getattr(user, "id", None) or getattr(user, "user_id", None)
        unique_id = getattr(user, "unique_id", None)
        nickname = getattr(user, "nickname", None)

    user_id = str(user_id_raw) if user_id_raw not in (None, "") else None
    username = str(unique_id or fallback_username or nickname or "").strip()
    display_name = str(nickname or username or "Unknown").strip()
    normalised = _normalise_username(username)
    if user_id:
        key = f"id:{user_id}"
    elif normalised and normalised != "unknown":
        key = f"user:{normalised}"
    else:
        key = _UNKNOWN_KEY
        username = username or "Unknown"
        display_name = display_name or "Unknown"
    return key, user_id, username or "Unknown", display_name or "Unknown"


def _empty_viewer(
    user_key: str,
    user_id: str | None,
    username: str,
    display_name: str,
    timestamp: str,
) -> dict[str, Any]:
    """Create a zeroed per-viewer aggregate."""
    return {
        "user_key": user_key,
        "user_id": user_id,
        "username": username,
        "display_name": display_name,
        "gift_events": 0,
        "gift_units": 0,
        "gift_diamonds": 0,
        "gift_value_usd": 0.0,
        "likes_raw": 0,
        "likes_counted": 0,
        "comments": 0,
        "follows": 0,
        "shares": 0,
        "joins": 0,
        "first_seen": timestamp,
        "last_seen": timestamp,
    }


class SessionAggregator:
    """Collect one stream session in memory and flush it in the background."""

    def __init__(
        self,
        config: AnalyticsConfig | None = None,
        store: AnalyticsStore | None = None,
        *,
        autostart: bool = False,
    ) -> None:
        """Create an aggregator with optional config/store and writer thread."""
        self.config = config or AnalyticsConfig()
        self.store = store or AnalyticsStore()
        self._lock = threading.RLock()
        self._writer_stop: threading.Event | None = None
        self._writer_thread: threading.Thread | None = None
        self._active = False
        self._finalized = False
        self._session_id: str | None = None
        self._started_at: float = 0.0
        self._ended_at: float | None = None
        self._created_at: str = ""
        self._tiktok_user = ""
        self._room_id: str | None = None
        self._reconnect_count = 0
        self._end_reason: str | None = None
        self._totals: dict[str, Any] = {}
        self._viewers: dict[str, dict[str, Any]] = {}
        self._gifts: dict[str, dict[str, Any]] = {}
        self._gift_gifters: dict[str, set[str]] = {}
        self._unique: dict[str, set[str]] = {}
        self._largest_gift: dict[str, Any] | None = None
        self._largest_combo: dict[str, Any] | None = None
        self._pending_raw_events: list[dict[str, Any]] = []
        self._dirty = False
        self._reset_state(0.0, "", None)
        if autostart and self.config.enabled:
            self._start_writer()

    def configure(self, config: AnalyticsConfig) -> None:
        """Apply a new configuration and start/stop the writer accordingly."""
        with self._lock:
            self.config = config
        if config.enabled:
            self._start_writer()
        else:
            self._stop_writer()

    def _reset_state(
        self, started_at: float, tiktok_user: str, room_id: str | None
    ) -> None:
        """Initialise all counters for a fresh session."""
        self._active = False
        self._finalized = False
        self._session_id = None
        self._started_at = started_at
        self._ended_at = None
        self._created_at = _iso(time.time())
        self._tiktok_user = tiktok_user
        self._room_id = room_id
        self._reconnect_count = 0
        self._end_reason = None
        self._totals = {
            "gift_events": 0,
            "gift_units": 0,
            "gift_diamonds": 0,
            "gift_value_usd": 0.0,
            "likes_raw": 0,
            "likes_counted": 0,
            "follows": 0,
            "comments": 0,
            "shares": 0,
            "joins": 0,
        }
        self._viewers = {}
        self._gifts = {}
        self._gift_gifters = {}
        self._unique = {
            "gifters": set(),
            "likers": set(),
            "followers": set(),
            "commenters": set(),
            "sharers": set(),
            "joiners": set(),
            "viewers": set(),
        }
        self._largest_gift = None
        self._largest_combo = None
        self._pending_raw_events = []
        self._dirty = False

    @property
    def active(self) -> bool:
        """Whether a session is currently collecting events."""
        return self._active

    @property
    def session_id(self) -> str | None:
        """Return the current (or most recent) session id."""
        return self._session_id

    def start_session(
        self,
        started_at: float | None = None,
        *,
        tiktok_user: str = "",
        room_id: str | None = None,
    ) -> str:
        """Start a new session and return its id.

        An unfinished previous session is finalised first so a reconnect that
        starts a new stream cannot silently discard its aggregates.
        """
        timestamp = time.time() if started_at is None else started_at
        with self._lock:
            if self._active and not self._finalized:
                self._finalize_locked(timestamp, "replaced")
            self._reset_state(timestamp, tiktok_user, room_id)
            self._session_id = f"{int(timestamp * 1000)}-{uuid.uuid4().hex[:10]}"
            self._active = True
            self._finalized = False
            self._dirty = True
        self._start_writer()
        return self._session_id

    def record_reconnect(self) -> None:
        """Increment the reconnect counter for the active session."""
        with self._lock:
            if self._active:
                self._reconnect_count += 1

    def _touch_viewer(
        self,
        user_key: str,
        user_id: str | None,
        username: str,
        display_name: str,
        timestamp: str,
    ) -> dict[str, Any]:
        """Return the viewer aggregate, creating it (or the overflow bucket)."""
        if (
            user_key not in self._viewers
            and len(self._viewers) >= self.config.max_tracked_viewers
        ):
            user_key = _OTHER_KEY
            user_id = None
            username = _OTHER_KEY
            display_name = _OTHER_KEY
        viewer = self._viewers.get(user_key)
        if viewer is None:
            viewer = _empty_viewer(user_key, user_id, username, display_name, timestamp)
            self._viewers[user_key] = viewer
        else:
            viewer["last_seen"] = max(viewer["last_seen"], timestamp)
        self._unique["viewers"].add(user_key)
        return viewer

    def _add_raw_event(
        self,
        event_type: str,
        user_key: str,
        timestamp: str,
        *,
        gift_id: str | None = None,
        gift_name: str | None = None,
        units: int = 0,
        diamonds: int = 0,
        value_usd: float = 0.0,
        text: str | None = None,
    ) -> None:
        """Buffer an optional raw event, bounded to avoid unbounded memory."""
        if not self.config.store.raw_events:
            return
        if len(self._pending_raw_events) >= _MAX_RAW_EVENTS:
            self._pending_raw_events.pop(0)
        self._pending_raw_events.append(
            {
                "event_id": uuid.uuid4().hex,
                "ts": timestamp,
                "event_type": event_type,
                "user_key": user_key,
                "gift_id": gift_id,
                "gift_name": gift_name,
                "units": units,
                "diamonds": diamonds,
                "value_usd": value_usd,
                "text": text if self.config.store.comment_text else None,
            }
        )

    def record_gift(
        self,
        user: object | None,
        gift_id: object,
        gift_name: str,
        units: int,
        diamonds: int,
        value_usd: float,
        *,
        timestamp: float | None = None,
        fallback_username: str | None = None,
    ) -> None:
        """Record one gift event, including combo units and diamonds."""
        if units <= 0:
            units = 1
        with self._lock:
            if not self._active or self._finalized:
                return
            ts = time.time() if timestamp is None else timestamp
            iso = _iso(ts)
            key, user_id, username, display_name = _identity(user, fallback_username)
            viewer = self._touch_viewer(key, user_id, username, display_name, iso)
            key = viewer["user_key"]
            gift_key = str(gift_id or gift_name or "unknown")
            gift = self._gifts.get(gift_key)
            if gift is None:
                gift = {
                    "gift_id": gift_key,
                    "gift_name": gift_name or gift_key,
                    "events": 0,
                    "units": 0,
                    "diamonds": 0,
                    "value_usd": 0.0,
                    "unique_gifters": 0,
                    "largest_combo_units": 0,
                    "first_seen": iso,
                    "last_seen": iso,
                }
                self._gifts[gift_key] = gift
            gift["events"] += 1
            gift["units"] += units
            gift["diamonds"] += diamonds
            gift["value_usd"] += value_usd
            gift["last_seen"] = max(gift["last_seen"], iso)
            gift["largest_combo_units"] = max(gift["largest_combo_units"], units)
            gift_gifters = self._gift_gifters.setdefault(gift_key, set())
            gift_gifters.add(key)
            gift["unique_gifters"] = len(gift_gifters)

            viewer["gift_events"] += 1
            viewer["gift_units"] += units
            viewer["gift_diamonds"] += diamonds
            viewer["gift_value_usd"] += value_usd
            self._unique["gifters"].add(key)

            self._totals["gift_events"] += 1
            self._totals["gift_units"] += units
            self._totals["gift_diamonds"] += diamonds
            self._totals["gift_value_usd"] += value_usd

            if self._largest_gift is None or value_usd > self._largest_gift["value"]:
                self._largest_gift = {
                    "name": gift_name or gift_key,
                    "value": value_usd,
                    "diamonds": diamonds,
                }
            if self._largest_combo is None or units > self._largest_combo["units"]:
                self._largest_combo = {
                    "name": gift_name or gift_key,
                    "units": units,
                }
            self._add_raw_event(
                "gift",
                key,
                iso,
                gift_id=gift_key,
                gift_name=gift_name,
                units=units,
                diamonds=diamonds,
                value_usd=value_usd,
            )
            self._dirty = True

    def record_like(
        self,
        user: object | None,
        raw_delta: int,
        counted_delta: int,
        *,
        timestamp: float | None = None,
        fallback_username: str | None = None,
    ) -> None:
        """Record likes, keeping the raw and rate-limited deltas separate."""
        if raw_delta <= 0 and counted_delta <= 0:
            return
        with self._lock:
            if not self._active or self._finalized:
                return
            ts = time.time() if timestamp is None else timestamp
            iso = _iso(ts)
            key, user_id, username, display_name = _identity(user, fallback_username)
            viewer = self._touch_viewer(key, user_id, username, display_name, iso)
            key = viewer["user_key"]
            viewer["likes_raw"] += max(0, raw_delta)
            viewer["likes_counted"] += max(0, counted_delta)
            self._totals["likes_raw"] += max(0, raw_delta)
            self._totals["likes_counted"] += max(0, counted_delta)
            self._unique["likers"].add(key)
            self._add_raw_event(
                "like",
                key,
                iso,
                units=max(0, counted_delta),
            )
            self._dirty = True

    def _record_simple(
        self,
        event_type: str,
        user: object | None,
        counter: str,
        unique_key: str,
        *,
        timestamp: float | None = None,
        fallback_username: str | None = None,
        text: str | None = None,
    ) -> None:
        """Record a follow/comment/share/join event."""
        with self._lock:
            if not self._active or self._finalized:
                return
            ts = time.time() if timestamp is None else timestamp
            iso = _iso(ts)
            key, user_id, username, display_name = _identity(user, fallback_username)
            viewer = self._touch_viewer(key, user_id, username, display_name, iso)
            key = viewer["user_key"]
            self._totals[counter] += 1
            viewer[counter] += 1
            self._unique[unique_key].add(key)
            self._add_raw_event(event_type, key, iso, text=text)
            self._dirty = True

    def record_follow(
        self,
        user: object | None,
        *,
        timestamp: float | None = None,
        fallback_username: str | None = None,
    ) -> None:
        """Record one follow event."""
        self._record_simple(
            "follow",
            user,
            "follows",
            "followers",
            timestamp=timestamp,
            fallback_username=fallback_username,
        )

    def record_comment(
        self,
        user: object | None,
        text: str | None = None,
        *,
        timestamp: float | None = None,
        fallback_username: str | None = None,
    ) -> None:
        """Record one comment event (text only when explicitly enabled)."""
        self._record_simple(
            "comment",
            user,
            "comments",
            "commenters",
            timestamp=timestamp,
            fallback_username=fallback_username,
            text=text,
        )

    def record_share(
        self,
        user: object | None,
        *,
        timestamp: float | None = None,
        fallback_username: str | None = None,
    ) -> None:
        """Record one share event."""
        self._record_simple(
            "share",
            user,
            "shares",
            "sharers",
            timestamp=timestamp,
            fallback_username=fallback_username,
        )

    def record_join(
        self,
        user: object | None,
        *,
        timestamp: float | None = None,
        fallback_username: str | None = None,
    ) -> None:
        """Record one join event."""
        self._record_simple(
            "join",
            user,
            "joins",
            "joiners",
            timestamp=timestamp,
            fallback_username=fallback_username,
        )

    def _snapshot_locked(self, *, final: bool) -> dict[str, Any] | None:
        """Build a snapshot; caller must hold the lock."""
        if self._session_id is None or self._started_at <= 0:
            return None
        ended = self._ended_at
        duration = max(0.0, (ended or time.time()) - self._started_at)
        snapshot: dict[str, Any] = {
            "session_id": self._session_id,
            "started_at": _iso(self._started_at),
            "ended_at": _iso(ended) if ended is not None else None,
            "duration_seconds": duration,
            "tiktok_user": self._tiktok_user,
            "room_id": self._room_id,
            "reconnect_count": self._reconnect_count,
            "end_reason": self._end_reason,
            "created_at": self._created_at,
            "viewers": [copy.deepcopy(v) for v in self._viewers.values()],
            "gifts": [copy.deepcopy(g) for g in self._gifts.values()],
            "raw_events": list(self._pending_raw_events),
        }
        for counter, value in self._totals.items():
            snapshot[counter] = value
        snapshot["unique_gifters"] = len(self._unique["gifters"])
        snapshot["unique_likers"] = len(self._unique["likers"])
        snapshot["unique_followers"] = len(self._unique["followers"])
        snapshot["unique_commenters"] = len(self._unique["commenters"])
        snapshot["unique_sharers"] = len(self._unique["sharers"])
        snapshot["unique_joiners"] = len(self._unique["joiners"])
        snapshot["unique_viewers"] = len(self._unique["viewers"])
        snapshot["largest_gift_name"] = (
            self._largest_gift["name"] if self._largest_gift else None
        )
        snapshot["largest_gift_value_usd"] = (
            self._largest_gift["value"] if self._largest_gift else 0.0
        )
        snapshot["largest_gift_diamonds"] = (
            self._largest_gift["diamonds"] if self._largest_gift else 0
        )
        snapshot["largest_combo_name"] = (
            self._largest_combo["name"] if self._largest_combo else None
        )
        snapshot["largest_combo_units"] = (
            self._largest_combo["units"] if self._largest_combo else 0
        )
        snapshot["tops"] = self._compute_tops_locked() if final else {}
        return snapshot

    def _compute_tops_locked(self) -> dict[str, list[dict[str, Any]]]:
        """Compute final top lists from the in-memory aggregates."""
        limit = self.config.top_n
        viewers = [v for v in self._viewers.values() if v["user_key"] != _OTHER_KEY]
        gifts = list(self._gifts.values())

        def viewer_entry(viewer: dict[str, Any], value: float) -> dict[str, Any]:
            return {
                "entry_key": viewer["user_key"],
                "name": viewer["display_name"] or viewer["username"],
                "value": value,
                "units": viewer["gift_units"],
                "diamonds": viewer["gift_diamonds"],
            }

        def gift_entry(gift: dict[str, Any], value: float) -> dict[str, Any]:
            return {
                "entry_key": gift["gift_id"],
                "name": gift["gift_name"],
                "value": value,
                "units": gift["units"],
                "diamonds": gift["diamonds"],
            }

        def viewer_ranking(value_getter, secondary_getter) -> list[dict[str, Any]]:
            """Rank viewers that actually have the category's value.

            Viewers are created for every interaction, so a like-only viewer
            must not appear in the gift leaderboard with a zero value.
            """
            ranked = [v for v in viewers if value_getter(v) > 0]
            ranked.sort(
                key=lambda v: (value_getter(v), secondary_getter(v)),
                reverse=True,
            )
            return [viewer_entry(v, value_getter(v)) for v in ranked[:limit]]

        def gift_ranking(value_getter, secondary_getter) -> list[dict[str, Any]]:
            """Rank gifts that actually have the category's value."""
            ranked = [g for g in gifts if value_getter(g) > 0]
            ranked.sort(
                key=lambda g: (value_getter(g), secondary_getter(g)),
                reverse=True,
            )
            return [gift_entry(g, value_getter(g)) for g in ranked[:limit]]

        tops: dict[str, list[dict[str, Any]]] = {
            "top_gifters_value": viewer_ranking(
                lambda v: v["gift_value_usd"], lambda v: v["gift_units"]
            ),
            "top_gifters_units": viewer_ranking(
                lambda v: v["gift_units"], lambda v: v["gift_value_usd"]
            ),
            "top_likers": viewer_ranking(
                lambda v: v["likes_counted"], lambda v: v["likes_raw"]
            ),
            "top_commenters": viewer_ranking(lambda v: v["comments"], lambda v: 0),
            "top_gifts_units": gift_ranking(
                lambda g: g["units"], lambda g: g["value_usd"]
            ),
            "top_gifts_value": gift_ranking(
                lambda g: g["value_usd"], lambda g: g["units"]
            ),
        }
        if self._largest_gift is not None:
            tops["largest_gift"] = [
                {
                    "entry_key": "",
                    "name": self._largest_gift["name"],
                    "value": self._largest_gift["value"],
                    "units": 1,
                    "diamonds": self._largest_gift["diamonds"],
                }
            ]
        if self._largest_combo is not None:
            tops["largest_combo"] = [
                {
                    "entry_key": "",
                    "name": self._largest_combo["name"],
                    "value": self._largest_combo["units"],
                    "units": self._largest_combo["units"],
                    "diamonds": 0,
                }
            ]
        return tops

    def flush(self) -> None:
        """Write the current snapshot without blocking event handlers."""
        with self._lock:
            if not self._active or self._finalized or not self.config.enabled:
                return
            snapshot = self._snapshot_locked(final=False)
            if snapshot is None:
                return
            raw_count = len(self._pending_raw_events)
            config = self.config
            self._dirty = False
        try:
            self.store.write_session(snapshot, config, final=False)
        except Exception:  # analytics must never break the bridge
            log.exception("Analytics flush failed; will retry on next interval")
            with self._lock:
                self._dirty = True
            return
        with self._lock:
            del self._pending_raw_events[:raw_count]

    def finalize_session(
        self, ended_at: float | None = None, end_reason: str | None = None
    ) -> bool:
        """Finalise and persist the active session, including lifetime data.

        Returns:
            ``True`` when a session was written, ``False`` when there was
            nothing to finalise or persistence failed.
        """
        with self._lock:
            if not self._active or self._finalized:
                return False
            return self._finalize_locked(ended_at or time.time(), end_reason)

    def _finalize_locked(self, ended_at: float, end_reason: str | None) -> bool:
        """Finalise while the caller holds the lock."""
        self._ended_at = ended_at
        self._end_reason = end_reason
        snapshot = self._snapshot_locked(final=True)
        if snapshot is None:
            return False
        raw_count = len(self._pending_raw_events)
        config = self.config
        self._active = False
        self._finalized = True
        try:
            if config.enabled:
                self.store.write_session(snapshot, config, final=True)
        except Exception:  # analytics must never break the bridge
            log.exception("Analytics final flush failed")
            self._active = True
            self._finalized = False
            return False
        del self._pending_raw_events[:raw_count]
        return True

    def snapshot(self) -> dict[str, Any] | None:
        """Return a deep copy of the current snapshot (for diagnostics/tests)."""
        with self._lock:
            return self._snapshot_locked(final=False)

    def _start_writer(self) -> None:
        """Start the daemon writer thread if it is not already running."""
        if not self.config.enabled:
            return
        with self._lock:
            if self._writer_thread is not None and self._writer_thread.is_alive():
                return
            stop = threading.Event()
            self._writer_stop = stop
            thread = threading.Thread(
                target=self._writer_loop,
                args=(stop,),
                name="analytics-writer",
                daemon=True,
            )
            self._writer_thread = thread
            thread.start()

    def _stop_writer(self) -> None:
        """Stop and join the writer thread."""
        with self._lock:
            stop = self._writer_stop
            thread = self._writer_thread
            self._writer_stop = None
            self._writer_thread = None
        if stop is not None:
            stop.set()
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)

    def _writer_loop(self, stop: threading.Event) -> None:
        """Periodically flush the active session until stopped."""
        last_prune = 0.0
        while not stop.wait(self.config.flush_interval_seconds):
            try:
                self.flush()
            except Exception:  # analytics must never break the bridge
                log.exception("Analytics writer flush failed")
            now = time.monotonic()
            if now - last_prune >= 86400:
                last_prune = now
                try:
                    self.store.prune(self.config.retention)
                except Exception:  # retention is best-effort
                    log.exception("Analytics retention cleanup failed")

    def close(self) -> None:
        """Stop the writer and flush any remaining aggregates."""
        self._stop_writer()
        try:
            self.flush()
        except Exception:  # shutdown must not raise
            log.exception("Analytics close flush failed")


_aggregator: SessionAggregator | None = None
_aggregator_lock = threading.Lock()


def get_analytics_aggregator() -> SessionAggregator:
    """Return the process-wide analytics aggregator singleton."""
    global _aggregator
    with _aggregator_lock:
        if _aggregator is None:
            _aggregator = SessionAggregator()
        return _aggregator
