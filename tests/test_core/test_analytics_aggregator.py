"""Tests for the in-memory analytics aggregator and SQLite store."""

import json
import sqlite3
import time
from types import SimpleNamespace

from core.analytics.aggregator import SessionAggregator
from core.analytics.config import AnalyticsConfig, AnalyticsRetention
from core.analytics.store import AnalyticsStore


def _config(**overrides):
    """Build a config with a long flush interval so tests stay deterministic."""
    raw = {"enabled": True, "flush_interval_seconds": 3600}
    raw.update(overrides)
    return AnalyticsConfig.from_mapping(raw)


def _aggregator(tmp_path, config=None):
    """Create an aggregator backed by a temporary SQLite database."""
    store = AnalyticsStore(tmp_path / "analytics.sqlite3")
    return SessionAggregator(config or _config(), store, autostart=False), store


def _user(user_id="1", unique_id="alice", nickname="Alice"):
    """Return a minimal TikTok-like user object."""
    return SimpleNamespace(id=user_id, unique_id=unique_id, nickname=nickname)


class TestAggregatorSession:
    def test_combo_gift_units_and_likes(self, tmp_path):
        agg, store = _aggregator(tmp_path)
        alice = _user()
        agg.start_session(time.time() - 60, tiktok_user="streamer")
        agg.record_gift(alice, 1, "Rose", 5, 5, 0.02)
        agg.record_like(alice, raw_delta=10, counted_delta=4)
        agg.record_follow(alice)
        agg.record_comment(alice, "hello")
        agg.record_share(alice)
        agg.record_join(alice)
        assert agg.finalize_session(time.time(), "live_end") is True

        summary = store.summary()
        assert summary["total"] == 1
        assert summary["total_gift_events"] == 1
        assert summary["total_gift_units"] == 5
        assert summary["total_gift_diamonds"] == 5
        assert summary["total_gifts"] == 5
        assert summary["total_likes_raw"] == 10
        assert summary["total_likes_counted"] == 4
        assert summary["total_unique_gifters"] == 1
        assert summary["total_unique_likers"] == 1
        assert summary["total_unique_viewers"] == 1
        assert summary["total_follows"] == 1
        assert summary["total_comments"] == 1
        assert summary["total_shares"] == 1
        assert summary["total_joins"] == 1

        assert agg.session_id is not None
        detail = store.get_session(agg.session_id)
        assert detail is not None
        assert detail["gift_units"] == 5
        assert detail["viewers"][0]["username"] == "alice"
        assert detail["viewers"][0]["gift_units"] == 5
        assert detail["viewers"][0]["likes_raw"] == 10
        assert detail["viewers"][0]["likes_counted"] == 4
        assert detail["gifts"][0]["gift_name"] == "Rose"
        assert detail["gifts"][0]["unique_gifters"] == 1
        assert detail["tops"]["top_gifters_value"][0]["name"] == "Alice"
        assert detail["tops"]["top_gifts_units"][0]["name"] == "Rose"

    def test_unknown_user_is_kept(self, tmp_path):
        agg, store = _aggregator(tmp_path)
        agg.start_session()
        agg.record_gift(None, 7, "Rose", 1, 1, 0.01)
        agg.record_like(None, raw_delta=2, counted_delta=2)
        agg.finalize_session()

        assert agg.session_id is not None
        detail = store.get_session(agg.session_id)
        assert detail is not None
        assert detail["unique_viewers"] == 1
        assert detail["viewers"][0]["user_key"] == "unknown"
        assert detail["viewers"][0]["gift_units"] == 1

    def test_details_can_be_disabled_but_tops_remain(self, tmp_path):
        config = _config(
            store={
                "viewer_details": False,
                "gift_details": False,
                "top_lists": True,
            }
        )
        agg, store = _aggregator(tmp_path, config)
        agg.start_session()
        agg.record_gift(_user(), 1, "Rose", 2, 2, 0.01)
        agg.finalize_session()

        assert agg.session_id is not None
        detail = store.get_session(agg.session_id)
        assert detail is not None
        assert detail["viewers"] == []
        assert detail["gifts"] == []
        assert detail["tops"]["top_gifters_value"]

    def test_disabled_analytics_writes_nothing(self, tmp_path):
        agg, store = _aggregator(tmp_path, _config(enabled=False))
        agg.start_session()
        agg.record_gift(_user(), 1, "Rose", 1, 1, 0.01)
        agg.finalize_session()

        assert store.path.exists() is False

    def test_lifetime_accumulates_across_sessions(self, tmp_path):
        agg, store = _aggregator(tmp_path)
        alice = _user()
        for _ in range(2):
            agg.start_session()
            agg.record_gift(alice, 1, "Rose", 1, 1, 0.02)
            agg.finalize_session()

        board = store.leaderboard()
        assert board["top_gifters_value"][0]["username"] == "alice"
        assert board["top_gifters_value"][0]["value"] == 0.04
        assert board["top_gifts_units"][0]["units"] == 2
        rollups = store.daily_rollups()
        assert rollups[0]["sessions"] == 2
        assert rollups[0]["gift_units"] == 2

    def test_max_tracked_viewers_uses_overflow_bucket(self, tmp_path):
        agg, store = _aggregator(tmp_path, _config(max_tracked_viewers=1))
        agg.start_session()
        agg.record_gift(_user("1", "alice", "Alice"), 1, "Rose", 1, 1, 0.01)
        agg.record_gift(_user("2", "bob", "Bob"), 1, "Rose", 1, 1, 0.01)
        agg.finalize_session()

        assert agg.session_id is not None
        detail = store.get_session(agg.session_id)
        assert detail is not None
        assert detail["unique_viewers"] == 2
        keys = {viewer["user_key"] for viewer in detail["viewers"]}
        assert "user:bob" not in keys
        assert "__other__" in keys

    def test_pagination(self, tmp_path):
        agg, store = _aggregator(tmp_path)
        for _ in range(3):
            agg.start_session()
            agg.finalize_session()

        first = store.summary(limit=2, offset=0)
        second = store.summary(limit=2, offset=2)
        assert first["total"] == 3
        assert len(first["sessions"]) == 2
        assert len(second["sessions"]) == 1


class TestRetentionAndImport:
    def test_retention_deletes_details_before_summaries(self, tmp_path):
        agg, store = _aggregator(tmp_path)
        old_start = time.time() - 3 * 86400
        agg.start_session(old_start)
        agg.record_gift(_user(), 1, "Rose", 1, 1, 0.01)
        agg.finalize_session(old_start + 60)
        assert agg.session_id is not None
        old_id = agg.session_id

        agg.start_session()
        agg.record_gift(_user(), 1, "Rose", 1, 1, 0.01)
        agg.finalize_session()
        assert agg.session_id is not None
        new_id = agg.session_id

        store.prune(AnalyticsRetention(details_days=1))
        old_detail = store.get_session(old_id)
        assert old_detail is not None
        assert old_detail["viewers"] == []
        assert old_detail["gifts"] == []
        new_detail = store.get_session(new_id)
        assert new_detail is not None
        assert new_detail["viewers"]

        store.prune(AnalyticsRetention(summaries_days=1))
        assert store.get_session(old_id) is None
        assert store.get_session(new_id) is not None

    def test_legacy_sessions_are_imported_once(self, tmp_path):
        sessions_path = tmp_path / "sessions.jsonl"
        sessions_path.write_text(
            json.dumps(
                {
                    "start": "2026-01-01T10:00:00+00:00",
                    "end": "2026-01-01T11:00:00+00:00",
                    "duration_seconds": 3600,
                    "gifts": 4,
                    "gift_value_usd": 1.25,
                    "likes": 20,
                    "follows": 2,
                    "comments": 3,
                    "shares": 1,
                    "joins": 5,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        store = AnalyticsStore(tmp_path / "analytics.sqlite3")

        assert store.import_legacy_sessions(sessions_path) == 1
        assert store.import_legacy_sessions(sessions_path) == 0

        summary = store.summary()
        assert summary["total"] == 1
        assert summary["sessions"][0]["gift_units"] == 4
        assert summary["sessions"][0]["likes_counted"] == 20
        assert summary["sessions"][0]["end_reason"] == "legacy"

    def test_raw_events_and_comment_text_are_optional(self, tmp_path):
        config = _config(
            store={"raw_events": True, "comment_text": True},
        )
        agg, store = _aggregator(tmp_path, config)
        agg.start_session()
        agg.record_comment(_user(), "hello world")
        agg.finalize_session()

        with sqlite3.connect(store.path) as conn:
            rows = conn.execute(
                "SELECT event_type, text FROM raw_events WHERE session_id = ?",
                (agg.session_id,),
            ).fetchall()
        assert rows == [("comment", "hello world")]
