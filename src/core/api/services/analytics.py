"""AnalyticsService — read stream analytics with a JSONL fallback.

The bridge writes aggregates to ``data/analytics.sqlite3``.  This service reads
that database for the sessions view, session detail and all-time leaderboards.
If the database is missing, locked or corrupt, it transparently falls back to
the legacy ``data/sessions.jsonl`` summaries so the GUI keeps working.
"""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.analytics.store import AnalyticsStore, legacy_session_id
from core.api.services.sessions import SessionService

log = logging.getLogger(__name__)

_LEADERBOARD_KEYS = (
    "top_gifters_value",
    "top_gifters_units",
    "top_likers",
    "top_commenters",
    "top_gifts_units",
    "top_gifts_value",
)


class AnalyticsService:
    """Read analytics summaries, details and leaderboards."""

    def __init__(
        self,
        store: AnalyticsStore | None = None,
        session_service: SessionService | None = None,
        *,
        sessions_path: Path | None = None,
    ) -> None:
        """Create the service with optional injected dependencies.

        Args:
            store: Analytics database access. A default store is created on
                first use when omitted.
            session_service: Legacy JSONL reader used for fallback and for the
                Markdown report.
            sessions_path: Optional explicit ``sessions.jsonl`` path forwarded
                to a default :class:`SessionService`.
        """
        self._store = store
        self._sessions = session_service or SessionService(sessions_path)
        self._ready_lock = threading.Lock()
        self._ready = False

    @property
    def store(self) -> AnalyticsStore:
        """Return the analytics store, creating the default on first access."""
        if self._store is None:
            self._store = AnalyticsStore()
        return self._store

    def _ensure_ready(self) -> None:
        """Create the schema and import legacy sessions exactly once.

        The import is guarded by an ``analytics_meta`` marker inside
        :class:`AnalyticsStore`, so calling this repeatedly is safe. Errors are
        logged and the caller falls back to JSONL.
        """
        if self._ready:
            return
        with self._ready_lock:
            if self._ready:
                return
            self.store.ensure_schema()
            try:
                self.store.import_legacy_sessions(self._sessions.sessions_path)
            except Exception:
                log.exception("Legacy session import failed; continuing")
            self._ready = True

    @staticmethod
    def _entry_from_row(row: dict[str, Any]) -> dict[str, Any]:
        """Map a stored session row to the API-compatible entry shape."""
        data = dict(row)
        data["start"] = data.get("started_at") or data.get("start") or ""
        data["end"] = data.get("ended_at") or data.get("end") or ""
        return data

    def summary_page(self, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        """Return paginated session summaries, newest first.

        Falls back to ``sessions.jsonl`` when the analytics database cannot be
        read. In fallback mode the legacy totals are preserved and the entries
        are sorted newest first before pagination.
        """
        try:
            self._ensure_ready()
            data = self.store.summary(limit=limit, offset=offset)
            data["sessions"] = [
                self._entry_from_row(row) for row in data.get("sessions", [])
            ]
            return data
        except Exception:
            log.exception("Analytics summary failed; falling back to sessions.jsonl")
            return self._fallback_summary(limit, offset)

    def _fallback_summary(self, limit: int, offset: int) -> dict[str, Any]:
        """Build a paginated summary from the legacy JSONL log."""
        try:
            data = self._sessions.summary()
        except Exception:
            log.exception("Legacy session summary failed")
            return {
                "total": 0,
                "total_gifts": 0,
                "total_gift_value_usd": 0,
                "total_likes": 0,
                "total_follows": 0,
                "total_comments": 0,
                "total_shares": 0,
                "total_joins": 0,
                "sessions": [],
            }
        entries = list(data.get("sessions", []))
        entries.reverse()  # newest first, matching the SQLite summary order
        data["sessions"] = entries[offset : offset + limit]
        return data

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        """Return one session with viewer, gift and top-list detail.

        Returns ``None`` when the id is unknown. Legacy sessions imported from
        ``sessions.jsonl`` return empty detail lists (the old log only stored
        totals).
        """
        try:
            self._ensure_ready()
            detail = self.store.get_session(session_id)
            if detail is not None:
                # ``store.get_session`` reuses the ``gifts`` key for the gift
                # detail list; the API keeps ``gifts`` as the unit count and
                # exposes the list separately as ``gift_stats``.
                data = self._entry_from_row(
                    {key: value for key, value in detail.items() if key != "gifts"}
                )
                data["gifts"] = int(detail.get("gift_units", 0) or 0)
                data["gift_stats"] = detail.get("gifts", [])
                return data
        except Exception:
            log.exception("Analytics detail failed; falling back to sessions.jsonl")
        return self._fallback_detail(session_id)

    def _fallback_detail(self, session_id: str) -> dict[str, Any] | None:
        """Find a legacy session by its deterministic id."""
        try:
            for entry in self._sessions.read_entries():
                if legacy_session_id(entry) != session_id:
                    continue
                data = dict(entry)
                data["session_id"] = session_id
                data["viewers"] = []
                data["gift_stats"] = []
                data["tops"] = {}
                return data
        except Exception:
            log.exception("Legacy session detail lookup failed")
        return None

    def leaderboard(self, limit: int = 10) -> dict[str, list[dict[str, Any]]]:
        """Return all-time leaderboards, or empty lists when unavailable."""
        try:
            self._ensure_ready()
            return self.store.leaderboard(limit=limit)
        except Exception:
            log.exception("Analytics leaderboard failed")
            return {key: [] for key in _LEADERBOARD_KEYS}

    def daily_rollups(self, limit: int = 365) -> list[dict[str, Any]]:
        """Return daily aggregate rows, newest first (empty on failure)."""
        try:
            self._ensure_ready()
            return self.store.daily_rollups(limit=limit)
        except Exception:
            log.exception("Analytics daily rollups failed")
            return []

    def generate_markdown(self) -> str:
        """Render the legacy session report plus all-time leaderboards."""
        try:
            base = self._sessions.generate_markdown()
        except Exception:
            log.exception("Legacy session report failed")
            base = "# TikTok2Mc — Stream Session Report\n"
        board = self.leaderboard()
        if not any(board.get(key) for key in _LEADERBOARD_KEYS):
            return base

        lines = [base.rstrip(), "", "## All-time leaderboards", ""]

        def add_viewer_section(title: str, key: str, suffix: str) -> None:
            """Append one viewer leaderboard section."""
            entries = board.get(key) or []
            if not entries:
                return
            lines.append(f"### {title}")
            lines.append("")
            for rank, entry in enumerate(entries, start=1):
                name = entry.get("display_name") or entry.get("username") or "?"
                value = entry.get("value", 0)
                rendered = (
                    f"{value:.2f} $" if suffix == "$" else f"{int(value)} {suffix}"
                )
                lines.append(f"{rank}. {name} — {rendered}")
            lines.append("")

        def add_gift_section(title: str, key: str, suffix: str) -> None:
            """Append one gift leaderboard section."""
            entries = board.get(key) or []
            if not entries:
                return
            lines.append(f"### {title}")
            lines.append("")
            for rank, entry in enumerate(entries, start=1):
                name = entry.get("name") or entry.get("entry_key") or "?"
                value = entry.get("value", 0)
                rendered = (
                    f"{value:.2f} $" if suffix == "$" else f"{int(value)} {suffix}"
                )
                lines.append(f"{rank}. {name} — {rendered}")
            lines.append("")

        add_viewer_section("Top gifters by value", "top_gifters_value", "$")
        add_viewer_section("Top gifters by units", "top_gifters_units", "units")
        add_viewer_section("Top likers", "top_likers", "likes")
        add_viewer_section("Top commenters", "top_commenters", "comments")
        add_gift_section("Top gifts by units", "top_gifts_units", "units")
        add_gift_section("Top gifts by value", "top_gifts_value", "$")
        return "\n".join(lines).rstrip() + "\n"

    @staticmethod
    def generated_at() -> str:
        """Return the current UTC timestamp for API responses."""
        return datetime.now(UTC).isoformat(timespec="seconds")
