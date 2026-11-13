"""SQLite persistence for stream analytics.

The bridge writes aggregates through :class:`SessionAggregator`; this module
owns the schema, batched upserts, retention cleanup and read queries used by
the API.  All connections are short-lived so the writer thread and API
requests can safely use the same database file with WAL enabled.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from core.analytics.config import AnalyticsConfig, AnalyticsRetention
from core.paths import get_root_dir

log = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    duration_seconds REAL NOT NULL DEFAULT 0,
    tiktok_user TEXT NOT NULL DEFAULT '',
    room_id TEXT,
    reconnect_count INTEGER NOT NULL DEFAULT 0,
    end_reason TEXT,
    gift_events INTEGER NOT NULL DEFAULT 0,
    gift_units INTEGER NOT NULL DEFAULT 0,
    gift_diamonds INTEGER NOT NULL DEFAULT 0,
    gift_value_usd REAL NOT NULL DEFAULT 0,
    unique_gifters INTEGER NOT NULL DEFAULT 0,
    likes_raw INTEGER NOT NULL DEFAULT 0,
    likes_counted INTEGER NOT NULL DEFAULT 0,
    unique_likers INTEGER NOT NULL DEFAULT 0,
    follows INTEGER NOT NULL DEFAULT 0,
    unique_followers INTEGER NOT NULL DEFAULT 0,
    comments INTEGER NOT NULL DEFAULT 0,
    unique_commenters INTEGER NOT NULL DEFAULT 0,
    shares INTEGER NOT NULL DEFAULT 0,
    unique_sharers INTEGER NOT NULL DEFAULT 0,
    joins INTEGER NOT NULL DEFAULT 0,
    unique_joiners INTEGER NOT NULL DEFAULT 0,
    unique_viewers INTEGER NOT NULL DEFAULT 0,
    largest_gift_name TEXT,
    largest_gift_value_usd REAL NOT NULL DEFAULT 0,
    largest_gift_diamonds INTEGER NOT NULL DEFAULT 0,
    largest_combo_name TEXT,
    largest_combo_units INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS session_viewers (
    session_id TEXT NOT NULL,
    user_key TEXT NOT NULL,
    user_id TEXT,
    username TEXT NOT NULL DEFAULT '',
    display_name TEXT NOT NULL DEFAULT '',
    gift_events INTEGER NOT NULL DEFAULT 0,
    gift_units INTEGER NOT NULL DEFAULT 0,
    gift_diamonds INTEGER NOT NULL DEFAULT 0,
    gift_value_usd REAL NOT NULL DEFAULT 0,
    likes_raw INTEGER NOT NULL DEFAULT 0,
    likes_counted INTEGER NOT NULL DEFAULT 0,
    comments INTEGER NOT NULL DEFAULT 0,
    follows INTEGER NOT NULL DEFAULT 0,
    shares INTEGER NOT NULL DEFAULT 0,
    joins INTEGER NOT NULL DEFAULT 0,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    PRIMARY KEY (session_id, user_key)
);

CREATE TABLE IF NOT EXISTS session_gifts (
    session_id TEXT NOT NULL,
    gift_id TEXT NOT NULL,
    gift_name TEXT NOT NULL DEFAULT '',
    events INTEGER NOT NULL DEFAULT 0,
    units INTEGER NOT NULL DEFAULT 0,
    diamonds INTEGER NOT NULL DEFAULT 0,
    value_usd REAL NOT NULL DEFAULT 0,
    unique_gifters INTEGER NOT NULL DEFAULT 0,
    largest_combo_units INTEGER NOT NULL DEFAULT 0,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    PRIMARY KEY (session_id, gift_id)
);

CREATE TABLE IF NOT EXISTS session_tops (
    session_id TEXT NOT NULL,
    category TEXT NOT NULL,
    rank INTEGER NOT NULL,
    entry_key TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL DEFAULT '',
    value REAL NOT NULL DEFAULT 0,
    units INTEGER NOT NULL DEFAULT 0,
    diamonds INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (session_id, category, rank)
);

CREATE TABLE IF NOT EXISTS viewer_lifetime (
    user_key TEXT PRIMARY KEY,
    user_id TEXT,
    username TEXT NOT NULL DEFAULT '',
    display_name TEXT NOT NULL DEFAULT '',
    gift_events INTEGER NOT NULL DEFAULT 0,
    gift_units INTEGER NOT NULL DEFAULT 0,
    gift_diamonds INTEGER NOT NULL DEFAULT 0,
    gift_value_usd REAL NOT NULL DEFAULT 0,
    likes_raw INTEGER NOT NULL DEFAULT 0,
    likes_counted INTEGER NOT NULL DEFAULT 0,
    comments INTEGER NOT NULL DEFAULT 0,
    follows INTEGER NOT NULL DEFAULT 0,
    shares INTEGER NOT NULL DEFAULT 0,
    joins INTEGER NOT NULL DEFAULT 0,
    sessions_seen INTEGER NOT NULL DEFAULT 0,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS gift_lifetime (
    gift_id TEXT PRIMARY KEY,
    gift_name TEXT NOT NULL DEFAULT '',
    events INTEGER NOT NULL DEFAULT 0,
    units INTEGER NOT NULL DEFAULT 0,
    diamonds INTEGER NOT NULL DEFAULT 0,
    value_usd REAL NOT NULL DEFAULT 0,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS daily_rollup (
    day TEXT PRIMARY KEY,
    sessions INTEGER NOT NULL DEFAULT 0,
    gift_events INTEGER NOT NULL DEFAULT 0,
    gift_units INTEGER NOT NULL DEFAULT 0,
    gift_diamonds INTEGER NOT NULL DEFAULT 0,
    gift_value_usd REAL NOT NULL DEFAULT 0,
    likes_raw INTEGER NOT NULL DEFAULT 0,
    likes_counted INTEGER NOT NULL DEFAULT 0,
    follows INTEGER NOT NULL DEFAULT 0,
    comments INTEGER NOT NULL DEFAULT 0,
    shares INTEGER NOT NULL DEFAULT 0,
    joins INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS raw_events (
    event_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    ts TEXT NOT NULL,
    event_type TEXT NOT NULL,
    user_key TEXT NOT NULL DEFAULT '',
    gift_id TEXT,
    gift_name TEXT,
    units INTEGER NOT NULL DEFAULT 0,
    diamonds INTEGER NOT NULL DEFAULT 0,
    value_usd REAL NOT NULL DEFAULT 0,
    text TEXT
);

CREATE TABLE IF NOT EXISTS analytics_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sessions_started_at ON sessions(started_at);
CREATE INDEX IF NOT EXISTS idx_session_viewers_session ON session_viewers(session_id);
CREATE INDEX IF NOT EXISTS idx_session_viewers_user ON session_viewers(user_key);
CREATE INDEX IF NOT EXISTS idx_session_gifts_session ON session_gifts(session_id);
CREATE INDEX IF NOT EXISTS idx_session_gifts_gift ON session_gifts(gift_id);
CREATE INDEX IF NOT EXISTS idx_session_tops_session ON session_tops(session_id);
CREATE INDEX IF NOT EXISTS idx_viewer_lifetime_value ON viewer_lifetime(gift_value_usd);
CREATE INDEX IF NOT EXISTS idx_viewer_lifetime_units ON viewer_lifetime(gift_units);
CREATE INDEX IF NOT EXISTS idx_gift_lifetime_units ON gift_lifetime(units);
CREATE INDEX IF NOT EXISTS idx_gift_lifetime_value ON gift_lifetime(value_usd);
CREATE INDEX IF NOT EXISTS idx_raw_events_ts ON raw_events(ts);
"""


class AnalyticsStore:
    """Read/write access to ``data/analytics.sqlite3``."""

    def __init__(self, path: Path | None = None) -> None:
        """Create a store for *path* or the default analytics database."""
        self._path = path

    @property
    def path(self) -> Path:
        """Return the resolved database path."""
        if self._path is None:
            self._path = (get_root_dir() / "data" / "analytics.sqlite3").resolve()
        return self._path

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Yield a short-lived connection with WAL and a busy timeout."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA busy_timeout=10000")
            yield conn
        finally:
            conn.close()

    def ensure_schema(self) -> None:
        """Create all tables and indexes if they do not exist yet."""
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            conn.commit()

    @staticmethod
    def _upsert(
        conn: sqlite3.Connection,
        table: str,
        key_columns: tuple[str, ...],
        data: dict[str, Any],
    ) -> None:
        """Insert or update one row using an ``ON CONFLICT`` upsert."""
        columns = list(data)
        placeholders = ", ".join("?" for _ in columns)
        updates = [c for c in columns if c not in key_columns]
        sql = (
            f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders}) "
            f"ON CONFLICT ({', '.join(key_columns)}) "
        )
        if updates:
            sql += "DO UPDATE SET " + ", ".join(f"{c}=excluded.{c}" for c in updates)
        else:
            sql += "DO NOTHING"
        conn.execute(sql, [data[c] for c in columns])

    @staticmethod
    def _upsert_many(
        conn: sqlite3.Connection,
        table: str,
        key_columns: tuple[str, ...],
        rows: list[dict[str, Any]],
    ) -> None:
        """Insert or update many rows with the same column set."""
        if not rows:
            return
        columns = list(rows[0])
        placeholders = ", ".join("?" for _ in columns)
        updates = [c for c in columns if c not in key_columns]
        sql = (
            f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders}) "
            f"ON CONFLICT ({', '.join(key_columns)}) "
        )
        if updates:
            sql += "DO UPDATE SET " + ", ".join(f"{c}=excluded.{c}" for c in updates)
        else:
            sql += "DO NOTHING"
        conn.executemany(sql, [[row[c] for c in columns] for row in rows])

    def write_session(
        self,
        snapshot: dict[str, Any],
        config: AnalyticsConfig,
        *,
        final: bool = False,
    ) -> None:
        """Persist a session snapshot in one transaction.

        Periodic flushes upsert the session row plus optional detail rows.
        A final flush additionally writes top lists and lifetime/daily
        aggregates.  Callers must keep the snapshot JSON-serialisable.
        """
        self.ensure_schema()
        now = datetime.now(UTC).isoformat(timespec="seconds")
        session_row = {
            key: value
            for key, value in snapshot.items()
            if key
            not in {"viewers", "gifts", "tops", "raw_events", "final", "started_at"}
            and key
            not in {
                "started_at",
            }
        }
        session_row["session_id"] = snapshot["session_id"]
        session_row["started_at"] = snapshot["started_at"]
        session_row["created_at"] = snapshot.get("created_at", now)
        session_row["updated_at"] = now

        with self._connect() as conn:
            self._upsert(conn, "sessions", ("session_id",), session_row)

            if config.store.viewer_details:
                viewers = [
                    {
                        "session_id": snapshot["session_id"],
                        "user_key": v["user_key"],
                        "user_id": v.get("user_id"),
                        "username": v.get("username", ""),
                        "display_name": v.get("display_name", ""),
                        "gift_events": v.get("gift_events", 0),
                        "gift_units": v.get("gift_units", 0),
                        "gift_diamonds": v.get("gift_diamonds", 0),
                        "gift_value_usd": v.get("gift_value_usd", 0),
                        "likes_raw": v.get("likes_raw", 0),
                        "likes_counted": v.get("likes_counted", 0),
                        "comments": v.get("comments", 0),
                        "follows": v.get("follows", 0),
                        "shares": v.get("shares", 0),
                        "joins": v.get("joins", 0),
                        "first_seen": v.get("first_seen", snapshot["started_at"]),
                        "last_seen": v.get("last_seen", snapshot["started_at"]),
                    }
                    for v in snapshot.get("viewers", [])
                ]
                self._upsert_many(
                    conn,
                    "session_viewers",
                    ("session_id", "user_key"),
                    viewers,
                )

            if config.store.gift_details:
                gifts = [
                    {
                        "session_id": snapshot["session_id"],
                        "gift_id": g["gift_id"],
                        "gift_name": g.get("gift_name", ""),
                        "events": g.get("events", 0),
                        "units": g.get("units", 0),
                        "diamonds": g.get("diamonds", 0),
                        "value_usd": g.get("value_usd", 0),
                        "unique_gifters": g.get("unique_gifters", 0),
                        "largest_combo_units": g.get("largest_combo_units", 0),
                        "first_seen": g.get("first_seen", snapshot["started_at"]),
                        "last_seen": g.get("last_seen", snapshot["started_at"]),
                    }
                    for g in snapshot.get("gifts", [])
                ]
                self._upsert_many(
                    conn,
                    "session_gifts",
                    ("session_id", "gift_id"),
                    gifts,
                )

            if final and config.store.top_lists:
                conn.execute(
                    "DELETE FROM session_tops WHERE session_id = ?",
                    (snapshot["session_id"],),
                )
                top_rows = []
                for category, entries in snapshot.get("tops", {}).items():
                    for rank, entry in enumerate(entries, start=1):
                        top_rows.append(
                            {
                                "session_id": snapshot["session_id"],
                                "category": category,
                                "rank": rank,
                                "entry_key": entry.get("entry_key", ""),
                                "name": entry.get("name", ""),
                                "value": entry.get("value", 0),
                                "units": entry.get("units", 0),
                                "diamonds": entry.get("diamonds", 0),
                            }
                        )
                self._upsert_many(
                    conn,
                    "session_tops",
                    ("session_id", "category", "rank"),
                    top_rows,
                )

            if final and config.store.lifetime_aggregates:
                self._update_lifetime(conn, snapshot)

            raw_events = snapshot.get("raw_events", [])
            if raw_events:
                conn.executemany(
                    "INSERT OR IGNORE INTO raw_events "
                    "(event_id, session_id, ts, event_type, user_key, gift_id, "
                    "gift_name, units, diamonds, value_usd, text) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        (
                            e.get("event_id", ""),
                            snapshot["session_id"],
                            e.get("ts", snapshot["started_at"]),
                            e.get("event_type", ""),
                            e.get("user_key", ""),
                            e.get("gift_id"),
                            e.get("gift_name"),
                            e.get("units", 0),
                            e.get("diamonds", 0),
                            e.get("value_usd", 0),
                            e.get("text"),
                        )
                        for e in raw_events
                    ],
                )

            conn.commit()

    def _update_lifetime(
        self, conn: sqlite3.Connection, snapshot: dict[str, Any]
    ) -> None:
        """Add a finalised session to lifetime and daily aggregates."""
        day = str(snapshot.get("started_at", ""))[:10]
        for viewer in snapshot.get("viewers", []):
            conn.execute(
                "INSERT INTO viewer_lifetime ("
                "user_key, user_id, username, display_name, gift_events, "
                "gift_units, gift_diamonds, gift_value_usd, likes_raw, "
                "likes_counted, comments, follows, shares, joins, sessions_seen, "
                "first_seen, last_seen"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?) "
                "ON CONFLICT (user_key) DO UPDATE SET "
                "user_id = COALESCE(excluded.user_id, viewer_lifetime.user_id), "
                "username = excluded.username, "
                "display_name = excluded.display_name, "
                "gift_events = viewer_lifetime.gift_events + excluded.gift_events, "
                "gift_units = viewer_lifetime.gift_units + excluded.gift_units, "
                "gift_diamonds = viewer_lifetime.gift_diamonds + excluded.gift_diamonds, "
                "gift_value_usd = viewer_lifetime.gift_value_usd + excluded.gift_value_usd, "
                "likes_raw = viewer_lifetime.likes_raw + excluded.likes_raw, "
                "likes_counted = viewer_lifetime.likes_counted + excluded.likes_counted, "
                "comments = viewer_lifetime.comments + excluded.comments, "
                "follows = viewer_lifetime.follows + excluded.follows, "
                "shares = viewer_lifetime.shares + excluded.shares, "
                "joins = viewer_lifetime.joins + excluded.joins, "
                "sessions_seen = viewer_lifetime.sessions_seen + 1, "
                "first_seen = MIN(viewer_lifetime.first_seen, excluded.first_seen), "
                "last_seen = MAX(viewer_lifetime.last_seen, excluded.last_seen)",
                (
                    viewer["user_key"],
                    viewer.get("user_id"),
                    viewer.get("username", ""),
                    viewer.get("display_name", ""),
                    viewer.get("gift_events", 0),
                    viewer.get("gift_units", 0),
                    viewer.get("gift_diamonds", 0),
                    viewer.get("gift_value_usd", 0),
                    viewer.get("likes_raw", 0),
                    viewer.get("likes_counted", 0),
                    viewer.get("comments", 0),
                    viewer.get("follows", 0),
                    viewer.get("shares", 0),
                    viewer.get("joins", 0),
                    viewer.get("first_seen", snapshot["started_at"]),
                    viewer.get("last_seen", snapshot["started_at"]),
                ),
            )
        for gift in snapshot.get("gifts", []):
            conn.execute(
                "INSERT INTO gift_lifetime ("
                "gift_id, gift_name, events, units, diamonds, value_usd, "
                "first_seen, last_seen"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT (gift_id) DO UPDATE SET "
                "gift_name = excluded.gift_name, "
                "events = gift_lifetime.events + excluded.events, "
                "units = gift_lifetime.units + excluded.units, "
                "diamonds = gift_lifetime.diamonds + excluded.diamonds, "
                "value_usd = gift_lifetime.value_usd + excluded.value_usd, "
                "first_seen = MIN(gift_lifetime.first_seen, excluded.first_seen), "
                "last_seen = MAX(gift_lifetime.last_seen, excluded.last_seen)",
                (
                    gift["gift_id"],
                    gift.get("gift_name", ""),
                    gift.get("events", 0),
                    gift.get("units", 0),
                    gift.get("diamonds", 0),
                    gift.get("value_usd", 0),
                    gift.get("first_seen", snapshot["started_at"]),
                    gift.get("last_seen", snapshot["started_at"]),
                ),
            )
        conn.execute(
            "INSERT INTO daily_rollup ("
            "day, sessions, gift_events, gift_units, gift_diamonds, "
            "gift_value_usd, likes_raw, likes_counted, follows, comments, "
            "shares, joins"
            ") VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (day) DO UPDATE SET "
            "sessions = daily_rollup.sessions + 1, "
            "gift_events = daily_rollup.gift_events + excluded.gift_events, "
            "gift_units = daily_rollup.gift_units + excluded.gift_units, "
            "gift_diamonds = daily_rollup.gift_diamonds + excluded.gift_diamonds, "
            "gift_value_usd = daily_rollup.gift_value_usd + excluded.gift_value_usd, "
            "likes_raw = daily_rollup.likes_raw + excluded.likes_raw, "
            "likes_counted = daily_rollup.likes_counted + excluded.likes_counted, "
            "follows = daily_rollup.follows + excluded.follows, "
            "comments = daily_rollup.comments + excluded.comments, "
            "shares = daily_rollup.shares + excluded.shares, "
            "joins = daily_rollup.joins + excluded.joins",
            (
                day,
                snapshot.get("gift_events", 0),
                snapshot.get("gift_units", 0),
                snapshot.get("gift_diamonds", 0),
                snapshot.get("gift_value_usd", 0),
                snapshot.get("likes_raw", 0),
                snapshot.get("likes_counted", 0),
                snapshot.get("follows", 0),
                snapshot.get("comments", 0),
                snapshot.get("shares", 0),
                snapshot.get("joins", 0),
            ),
        )

    @staticmethod
    def _session_entry(row: sqlite3.Row) -> dict[str, Any]:
        """Convert a ``sessions`` row to the API-compatible entry shape."""
        data = dict(row)
        data["gifts"] = data.get("gift_units", 0)
        data["likes"] = data.get("likes_counted", 0)
        return data

    def summary(self, limit: int = 50, offset: int = 0) -> dict[str, Any]:
        """Return paginated session summaries plus aggregate totals."""
        self.ensure_schema()
        with self._connect() as conn:
            total = int(conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0])
            rows = conn.execute(
                "SELECT * FROM sessions ORDER BY started_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
            totals = conn.execute(
                "SELECT "
                "COALESCE(SUM(gift_events),0) AS gift_events, "
                "COALESCE(SUM(gift_units),0) AS gift_units, "
                "COALESCE(SUM(gift_diamonds),0) AS gift_diamonds, "
                "COALESCE(SUM(gift_value_usd),0) AS gift_value_usd, "
                "COALESCE(SUM(unique_gifters),0) AS unique_gifters, "
                "COALESCE(SUM(likes_raw),0) AS likes_raw, "
                "COALESCE(SUM(likes_counted),0) AS likes_counted, "
                "COALESCE(SUM(unique_likers),0) AS unique_likers, "
                "COALESCE(SUM(follows),0) AS follows, "
                "COALESCE(SUM(unique_followers),0) AS unique_followers, "
                "COALESCE(SUM(comments),0) AS comments, "
                "COALESCE(SUM(unique_commenters),0) AS unique_commenters, "
                "COALESCE(SUM(shares),0) AS shares, "
                "COALESCE(SUM(unique_sharers),0) AS unique_sharers, "
                "COALESCE(SUM(joins),0) AS joins, "
                "COALESCE(SUM(unique_joiners),0) AS unique_joiners, "
                "COALESCE(SUM(unique_viewers),0) AS unique_viewers "
                "FROM sessions"
            ).fetchone()
        total_data = dict(totals)
        return {
            "total": total,
            "total_gifts": int(total_data["gift_units"]),
            "total_gift_events": int(total_data["gift_events"]),
            "total_gift_units": int(total_data["gift_units"]),
            "total_gift_diamonds": int(total_data["gift_diamonds"]),
            "total_gift_value_usd": round(float(total_data["gift_value_usd"]), 2),
            "total_unique_gifters": int(total_data["unique_gifters"]),
            "total_likes": int(total_data["likes_counted"]),
            "total_likes_raw": int(total_data["likes_raw"]),
            "total_likes_counted": int(total_data["likes_counted"]),
            "total_unique_likers": int(total_data["unique_likers"]),
            "total_follows": int(total_data["follows"]),
            "total_unique_followers": int(total_data["unique_followers"]),
            "total_comments": int(total_data["comments"]),
            "total_unique_commenters": int(total_data["unique_commenters"]),
            "total_shares": int(total_data["shares"]),
            "total_unique_sharers": int(total_data["unique_sharers"]),
            "total_joins": int(total_data["joins"]),
            "total_unique_joiners": int(total_data["unique_joiners"]),
            "total_unique_viewers": int(total_data["unique_viewers"]),
            "sessions": [self._session_entry(row) for row in rows],
        }

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        """Return one session with its stored detail rows and top lists."""
        self.ensure_schema()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
            if row is None:
                return None
            viewers = conn.execute(
                "SELECT * FROM session_viewers WHERE session_id = ? "
                "ORDER BY gift_value_usd DESC, gift_units DESC, username ASC",
                (session_id,),
            ).fetchall()
            gifts = conn.execute(
                "SELECT * FROM session_gifts WHERE session_id = ? "
                "ORDER BY units DESC, value_usd DESC, gift_name ASC",
                (session_id,),
            ).fetchall()
            tops = conn.execute(
                "SELECT * FROM session_tops WHERE session_id = ? "
                "ORDER BY category ASC, rank ASC",
                (session_id,),
            ).fetchall()
        top_map: dict[str, list[dict[str, Any]]] = {}
        for top in tops:
            item = dict(top)
            category = item.pop("category")
            item.pop("session_id", None)
            top_map.setdefault(category, []).append(item)
        result = self._session_entry(row)
        result["viewers"] = [dict(v) for v in viewers]
        result["gifts"] = [dict(g) for g in gifts]
        result["tops"] = top_map
        return result

    def leaderboard(self, limit: int = 10) -> dict[str, list[dict[str, Any]]]:
        """Return all-time leaderboards from the lifetime tables."""
        self.ensure_schema()
        with self._connect() as conn:
            gifters_value = conn.execute(
                "SELECT user_key, username, display_name, sessions_seen, "
                "gift_value_usd AS value, gift_units AS units, "
                "gift_diamonds AS diamonds "
                "FROM viewer_lifetime WHERE user_key != '__other__' "
                "AND gift_value_usd > 0 "
                "ORDER BY gift_value_usd DESC, gift_units DESC, username ASC LIMIT ?",
                (limit,),
            ).fetchall()
            gifters_units = conn.execute(
                "SELECT user_key, username, display_name, sessions_seen, "
                "gift_units AS value, gift_units AS units, "
                "gift_diamonds AS diamonds "
                "FROM viewer_lifetime WHERE user_key != '__other__' "
                "AND gift_units > 0 "
                "ORDER BY gift_units DESC, gift_value_usd DESC, username ASC LIMIT ?",
                (limit,),
            ).fetchall()
            likers = conn.execute(
                "SELECT user_key, username, display_name, sessions_seen, "
                "likes_counted AS value, likes_raw AS units, 0 AS diamonds "
                "FROM viewer_lifetime WHERE user_key != '__other__' "
                "AND likes_counted > 0 "
                "ORDER BY likes_counted DESC, likes_raw DESC, username ASC LIMIT ?",
                (limit,),
            ).fetchall()
            commenters = conn.execute(
                "SELECT user_key, username, display_name, sessions_seen, "
                "comments AS value, 0 AS units, 0 AS diamonds "
                "FROM viewer_lifetime WHERE user_key != '__other__' "
                "AND comments > 0 "
                "ORDER BY comments DESC, username ASC LIMIT ?",
                (limit,),
            ).fetchall()
            gifts_units = conn.execute(
                "SELECT gift_id AS entry_key, gift_name AS name, units AS value, "
                "units, diamonds FROM gift_lifetime WHERE units > 0 "
                "ORDER BY units DESC, value_usd DESC, gift_name ASC LIMIT ?",
                (limit,),
            ).fetchall()
            gifts_value = conn.execute(
                "SELECT gift_id AS entry_key, gift_name AS name, value_usd AS value, "
                "units, diamonds FROM gift_lifetime WHERE value_usd > 0 "
                "ORDER BY value_usd DESC, units DESC, gift_name ASC LIMIT ?",
                (limit,),
            ).fetchall()
        return {
            "top_gifters_value": [dict(r) for r in gifters_value],
            "top_gifters_units": [dict(r) for r in gifters_units],
            "top_likers": [dict(r) for r in likers],
            "top_commenters": [dict(r) for r in commenters],
            "top_gifts_units": [dict(r) for r in gifts_units],
            "top_gifts_value": [dict(r) for r in gifts_value],
        }

    def daily_rollups(self, limit: int = 365) -> list[dict[str, Any]]:
        """Return daily aggregate rows, newest first."""
        self.ensure_schema()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM daily_rollup ORDER BY day DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    def prune(self, retention: AnalyticsRetention) -> None:
        """Delete expired detail, summary, raw-event and aggregate rows."""
        self.ensure_schema()
        now = datetime.now(UTC)

        def cutoff(days: int) -> str | None:
            if days <= 0:
                return None
            return (now - timedelta(days=days)).isoformat(timespec="seconds")

        with self._connect() as conn:
            details_cutoff = cutoff(retention.details_days)
            if details_cutoff is not None:
                for table in ("session_viewers", "session_gifts", "session_tops"):
                    self._delete_batched(
                        conn,
                        table,
                        "session_id IN (SELECT session_id FROM sessions "
                        "WHERE started_at < ?)",
                        (details_cutoff,),
                    )

            summaries_cutoff = cutoff(retention.summaries_days)
            if summaries_cutoff is not None:
                for table in ("session_viewers", "session_gifts", "session_tops"):
                    self._delete_batched(
                        conn,
                        table,
                        "session_id IN (SELECT session_id FROM sessions "
                        "WHERE started_at < ?)",
                        (summaries_cutoff,),
                    )
                self._delete_batched(
                    conn, "sessions", "started_at < ?", (summaries_cutoff,)
                )

            raw_cutoff = cutoff(retention.raw_events_days)
            if raw_cutoff is not None:
                self._delete_batched(conn, "raw_events", "ts < ?", (raw_cutoff,))

            aggregates_cutoff = cutoff(retention.aggregates_days)
            if aggregates_cutoff is not None:
                self._delete_batched(
                    conn, "viewer_lifetime", "last_seen < ?", (aggregates_cutoff,)
                )
                self._delete_batched(
                    conn, "gift_lifetime", "last_seen < ?", (aggregates_cutoff,)
                )
                self._delete_batched(
                    conn,
                    "daily_rollup",
                    "day < ?",
                    (aggregates_cutoff[:10],),
                )

            conn.commit()
            conn.execute("PRAGMA incremental_vacuum")
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    @staticmethod
    def _delete_batched(
        conn: sqlite3.Connection,
        table: str,
        where: str,
        params: tuple[Any, ...],
    ) -> None:
        """Delete matching rows in batches of at most 1000."""
        while True:
            cursor = conn.execute(
                f"DELETE FROM {table} WHERE rowid IN "
                f"(SELECT rowid FROM {table} WHERE {where} LIMIT 1000)",
                params,
            )
            if cursor.rowcount <= 0:
                break

    def import_legacy_sessions(self, sessions_path: Path) -> int:
        """Import old ``sessions.jsonl`` summaries once.

        Legacy entries only contain totals, so detail tables stay empty.  The
        import is guarded by ``analytics_meta`` and is safe to call repeatedly.
        """
        self.ensure_schema()
        with self._connect() as conn:
            marker = conn.execute(
                "SELECT value FROM analytics_meta WHERE key = 'legacy_imported'"
            ).fetchone()
            if marker is not None:
                return 0
            imported = 0
            if sessions_path.exists():
                try:
                    with sessions_path.open("r", encoding="utf-8") as handle:
                        for line in handle:
                            entry = self._parse_legacy_line(line)
                            if entry is None:
                                continue
                            session_id = self._legacy_session_id(entry)
                            self._upsert(
                                conn,
                                "sessions",
                                ("session_id",),
                                {
                                    "session_id": session_id,
                                    "started_at": entry["start"],
                                    "ended_at": entry["end"],
                                    "duration_seconds": entry.get(
                                        "duration_seconds", 0
                                    ),
                                    "tiktok_user": "",
                                    "room_id": None,
                                    "reconnect_count": 0,
                                    "end_reason": "legacy",
                                    "gift_events": int(entry.get("gifts", 0) or 0),
                                    "gift_units": int(entry.get("gifts", 0) or 0),
                                    "gift_diamonds": 0,
                                    "gift_value_usd": float(
                                        entry.get("gift_value_usd", 0) or 0
                                    ),
                                    "unique_gifters": 0,
                                    "likes_raw": int(entry.get("likes", 0) or 0),
                                    "likes_counted": int(entry.get("likes", 0) or 0),
                                    "unique_likers": 0,
                                    "follows": int(entry.get("follows", 0) or 0),
                                    "unique_followers": 0,
                                    "comments": int(entry.get("comments", 0) or 0),
                                    "unique_commenters": 0,
                                    "shares": int(entry.get("shares", 0) or 0),
                                    "unique_sharers": 0,
                                    "joins": int(entry.get("joins", 0) or 0),
                                    "unique_joiners": 0,
                                    "unique_viewers": 0,
                                    "largest_gift_name": None,
                                    "largest_gift_value_usd": 0,
                                    "largest_gift_diamonds": 0,
                                    "largest_combo_name": None,
                                    "largest_combo_units": 0,
                                    "created_at": entry["start"],
                                    "updated_at": entry["end"],
                                },
                            )
                            imported += 1
                except OSError as exc:
                    log.warning("Failed to import legacy sessions: %s", exc)
            conn.execute(
                "INSERT OR REPLACE INTO analytics_meta (key, value) "
                "VALUES ('legacy_imported', ?)",
                (datetime.now(UTC).isoformat(timespec="seconds"),),
            )
            conn.commit()
        return imported

    @staticmethod
    def _parse_legacy_line(line: str) -> dict[str, Any] | None:
        """Parse one legacy JSONL session line."""
        line = line.strip()
        if not line:
            return None
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict):
            return None
        if not isinstance(data.get("start"), str) or not isinstance(
            data.get("end"), str
        ):
            return None
        return data

    @staticmethod
    def _legacy_session_id(entry: dict[str, Any]) -> str:
        """Derive a stable id for a legacy session entry."""
        return legacy_session_id(entry)


def legacy_session_id(entry: dict[str, Any]) -> str:
    """Derive the stable analytics id for a ``sessions.jsonl`` entry.

    Args:
        entry: Parsed legacy session line containing ``start`` and ``end``.

    Returns:
        A deterministic ``legacy-<hash>`` id shared by the importer and the
        JSONL fallback so detail URLs keep working when SQLite is unavailable.
    """
    raw = f"{entry.get('start', '')}|{entry.get('end', '')}".encode()
    return "legacy-" + hashlib.sha1(raw).hexdigest()[:16]
