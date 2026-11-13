"""Tests for the analytics service and API endpoints."""

import json
import time
from types import SimpleNamespace

import pytest

from core.analytics.aggregator import SessionAggregator
from core.analytics.config import AnalyticsConfig
from core.analytics.store import AnalyticsStore, legacy_session_id
from core.api.services.analytics import AnalyticsService
from core.api.services.sessions import SessionService

SAMPLE_LEGACY = {
    "start": "2026-08-16T20:00:00+00:00",
    "end": "2026-08-16T21:30:00+00:00",
    "duration_seconds": 5400.0,
    "gifts": 12,
    "gift_value_usd": 4.5,
    "likes": 340,
    "follows": 5,
    "comments": 78,
    "shares": 2,
    "joins": 41,
}


def _user(user_id="1", unique_id="alice", nickname="Alice"):
    """Return a minimal TikTok-like user object."""
    return SimpleNamespace(id=user_id, unique_id=unique_id, nickname=nickname)


def _populate(tmp_path, sessions=1):
    """Create a store with finalised analytics sessions and return it."""
    store = AnalyticsStore(tmp_path / "analytics.sqlite3")
    config = AnalyticsConfig.from_mapping({"flush_interval_seconds": 3600})
    aggregator = SessionAggregator(config, store)
    base = time.time() - 3600
    for index in range(sessions):
        aggregator.start_session(base + index * 60, tiktok_user="streamer")
        aggregator.record_gift(
            _user(), 1, "Rose", 2 + index, 2 + index, 0.01 * (index + 1)
        )
        aggregator.record_like(_user(), raw_delta=10, counted_delta=4)
        aggregator.record_follow(_user())
        aggregator.record_comment(_user(), "hello")
        aggregator.record_share(_user())
        aggregator.record_join(_user())
        aggregator.finalize_session(base + index * 60 + 30, "live_end")
    return store, aggregator


@pytest.fixture
def analytics_service(tmp_path):
    store, _ = _populate(tmp_path, sessions=3)
    return AnalyticsService(
        store=store,
        session_service=SessionService(path=tmp_path / "data" / "sessions.jsonl"),
    )


class TestAnalyticsService:
    def test_summary_is_paginated_newest_first(self, analytics_service):
        page = analytics_service.summary_page(limit=2, offset=0)
        assert page["total"] == 3
        assert len(page["sessions"]) == 2
        assert page["total_gift_units"] == 2 + 3 + 4
        assert page["total_gift_events"] == 3
        assert page["total_likes_raw"] == 30
        assert page["total_likes_counted"] == 12
        starts = [entry["start"] for entry in page["sessions"]]
        assert starts == sorted(starts, reverse=True)

        second = analytics_service.summary_page(limit=2, offset=2)
        assert len(second["sessions"]) == 1

    def test_detail_maps_gift_stats_and_tops(self, analytics_service):
        page = analytics_service.summary_page()
        session_id = page["sessions"][0]["session_id"]
        detail = analytics_service.get_session(session_id)
        assert detail is not None
        assert detail["gifts"] == 4
        assert detail["gift_stats"][0]["gift_name"] == "Rose"
        assert detail["viewers"][0]["username"] == "alice"
        assert detail["tops"]["top_gifters_value"][0]["name"] == "Alice"
        assert detail["tops"]["top_gifts_units"][0]["name"] == "Rose"

    def test_unknown_session_returns_none(self, analytics_service):
        assert analytics_service.get_session("missing") is None

    def test_leaderboard_contains_all_groups(self, analytics_service):
        board = analytics_service.leaderboard(limit=5)
        assert board["top_gifters_value"][0]["username"] == "alice"
        assert board["top_gifters_value"][0]["value"] == pytest.approx(0.06)
        assert board["top_gifts_units"][0]["name"] == "Rose"
        assert board["top_gifts_units"][0]["units"] == 9
        assert board["top_likers"][0]["value"] == 12

    def test_markdown_includes_leaderboards(self, analytics_service):
        md = analytics_service.generate_markdown()
        assert "## All-time leaderboards" in md
        assert "Top gifters by value" in md
        assert "Top gifts by units" in md


class TestLegacyFallback:
    def _write_sessions(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(SAMPLE_LEGACY) + "\n", encoding="utf-8")

    def test_legacy_sessions_are_imported_and_readable(self, tmp_path):
        sessions_path = tmp_path / "data" / "sessions.jsonl"
        self._write_sessions(sessions_path)
        service = AnalyticsService(
            store=AnalyticsStore(tmp_path / "analytics.sqlite3"),
            sessions_path=sessions_path,
        )

        page = service.summary_page()
        assert page["total"] == 1
        assert page["sessions"][0]["start"] == SAMPLE_LEGACY["start"]
        assert page["sessions"][0]["gifts"] == 12

        legacy_id = legacy_session_id(SAMPLE_LEGACY)
        detail = service.get_session(legacy_id)
        assert detail is not None
        assert detail["gifts"] == 12
        assert detail["viewers"] == []
        assert detail["gift_stats"] == []
        assert detail["tops"] == {}

    def test_summary_falls_back_to_jsonl_when_store_fails(self, tmp_path, monkeypatch):
        sessions_path = tmp_path / "data" / "sessions.jsonl"
        self._write_sessions(sessions_path)
        store = AnalyticsStore(tmp_path / "analytics.sqlite3")
        service = AnalyticsService(store=store, sessions_path=sessions_path)

        def _fail():
            raise RuntimeError("database unavailable")

        monkeypatch.setattr(store, "ensure_schema", _fail)

        page = service.summary_page()
        assert page["total"] == 1
        assert page["sessions"][0]["gifts"] == 12
        assert service.leaderboard()["top_gifters_value"] == []


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


@pytest.fixture
def mocked_analytics(monkeypatch, tmp_path):
    import core.api.routes.analytics as analytics_route
    import core.api.routes.sessions as sessions_route

    store, _ = _populate(tmp_path, sessions=2)
    service = AnalyticsService(
        store=store,
        session_service=SessionService(path=tmp_path / "data" / "sessions.jsonl"),
    )
    monkeypatch.setattr(sessions_route, "_get_service", lambda: service)
    monkeypatch.setattr(analytics_route, "_get_service", lambda: service)
    return service


class TestAnalyticsApi:
    def test_sessions_support_pagination(self, client, mocked_analytics):
        resp = client.get("/api/v1/sessions", params={"limit": 1, "offset": 1})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["sessions"]) == 1
        assert data["total_gift_events"] == 2

    def test_session_detail_returns_viewers_and_tops(self, client, mocked_analytics):
        session_id = mocked_analytics.summary_page()["sessions"][0]["session_id"]
        resp = client.get(f"/api/v1/sessions/{session_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == session_id
        assert data["gift_stats"][0]["gift_name"] == "Rose"
        assert data["viewers"][0]["username"] == "alice"
        assert data["tops"]["top_gifters_value"][0]["name"] == "Alice"

    def test_unknown_session_returns_404(self, client, mocked_analytics):
        resp = client.get("/api/v1/sessions/does-not-exist")
        assert resp.status_code == 404

    def test_leaderboard_endpoint(self, client, mocked_analytics):
        resp = client.get("/api/v1/analytics/leaderboard", params={"limit": 5})
        assert resp.status_code == 200
        data = resp.json()
        assert data["generated_at"]
        assert data["top_gifters_value"][0]["username"] == "alice"
        assert data["top_gifts_units"][0]["name"] == "Rose"

    def test_report_contains_leaderboards(self, client, mocked_analytics):
        resp = client.get("/api/v1/sessions/report")
        assert resp.status_code == 200
        assert "## All-time leaderboards" in resp.text
