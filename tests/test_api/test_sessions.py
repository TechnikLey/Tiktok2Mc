"""Tests for the stream session service and API endpoints."""

import json

import pytest

from core.api.services.sessions import SessionService, _format_duration

SAMPLE_ENTRY = {
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


def _write_log(path, lines):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.fixture
def session_service(tmp_path):
    return SessionService(path=tmp_path / "data" / "sessions.jsonl")


class TestParseEntry:
    def test_parses_valid_line(self, session_service):
        entry = session_service._parse_entry(
            '{"start": "2026-08-16T20:00:00+00:00", "end": "2026-08-16T21:30:00+00:00"}'
        )
        assert entry["start"] == "2026-08-16T20:00:00+00:00"
        assert entry["end"] == "2026-08-16T21:30:00+00:00"

    def test_rejects_invalid_json(self, session_service):
        assert session_service._parse_entry("not json") is None

    def test_rejects_missing_start_or_end(self, session_service):
        assert (
            session_service._parse_entry('{"start": "2026-08-16T20:00:00+00:00"}')
            is None
        )
        assert (
            session_service._parse_entry('{"end": "2026-08-16T21:30:00+00:00"}') is None
        )

    def test_rejects_non_dict(self, session_service):
        assert session_service._parse_entry("[1, 2, 3]") is None

    def test_rejects_empty_line(self, session_service):
        assert session_service._parse_entry("") is None
        assert session_service._parse_entry("   ") is None


class TestReadEntries:
    def test_reads_and_sorts_entries(self, session_service):
        _write_log(
            session_service.sessions_path,
            [
                '{"start": "2026-08-16T21:00:00+00:00", "end": "2026-08-16T22:00:00+00:00"}',
                '{"start": "2026-08-16T20:00:00+00:00", "end": "2026-08-16T21:00:00+00:00"}',
            ],
        )
        entries = session_service.read_entries()
        assert [e["start"] for e in entries] == [
            "2026-08-16T20:00:00+00:00",
            "2026-08-16T21:00:00+00:00",
        ]

    def test_skips_malformed_lines(self, session_service):
        _write_log(
            session_service.sessions_path,
            [
                '{"start": "2026-08-16T20:00:00+00:00", "end": "2026-08-16T21:00:00+00:00"}',
                "garbage",
                "",
            ],
        )
        entries = session_service.read_entries()
        assert len(entries) == 1

    def test_empty_when_file_missing(self, session_service):
        assert session_service.read_entries() == []
        assert session_service.get_file_info()["exists"] is False


class TestSummary:
    def test_computes_totals(self, session_service):
        second = dict(SAMPLE_ENTRY)
        second["start"] = "2026-08-17T20:00:00+00:00"
        second["end"] = "2026-08-17T21:00:00+00:00"
        second["gifts"] = 8
        second["gift_value_usd"] = 2.25
        summary = session_service.summary([SAMPLE_ENTRY, second])
        assert summary["total"] == 2
        assert summary["total_gifts"] == 20
        assert summary["total_gift_value_usd"] == 6.75
        assert summary["total_likes"] == 680
        assert summary["total_follows"] == 10
        assert summary["total_comments"] == 156
        assert summary["total_shares"] == 4
        assert summary["total_joins"] == 82
        assert len(summary["sessions"]) == 2

    def test_empty_summary(self, session_service):
        summary = session_service.summary([])
        assert summary["total"] == 0
        assert summary["total_gifts"] == 0
        assert summary["total_gift_value_usd"] == 0.0
        assert summary["sessions"] == []

    def test_ignores_non_numeric_totals(self, session_service):
        bad = dict(SAMPLE_ENTRY, gifts="nope", gift_value_usd=None)
        summary = session_service.summary([bad])
        assert summary["total_gifts"] == 0
        assert summary["total_gift_value_usd"] == 0.0


class TestFormatDuration:
    def test_hours_minutes_seconds(self):
        assert _format_duration(3661) == "1h 01m 01s"

    def test_minutes_seconds(self):
        assert _format_duration(125) == "2m 05s"

    def test_seconds_only(self):
        assert _format_duration(42) == "42s"

    def test_negative_clamped(self):
        assert _format_duration(-5) == "0s"


class TestGenerateMarkdown:
    def test_report_contains_summary_and_sessions(self, session_service):
        md = session_service.generate_markdown([SAMPLE_ENTRY])
        assert md.startswith("# TikTok2Mc — Stream Session Report")
        assert "- Sessions: 1" in md
        assert "- Gifts: 12 (4.50 $)" in md
        assert "## Session 1" in md
        assert "- Duration: 1h 30m 00s" in md
        assert "- Likes: 340" in md
        assert "- Joins: 41" in md

    def test_report_empty(self, session_service):
        md = session_service.generate_markdown([])
        assert "No sessions recorded yet" in md


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


@pytest.fixture
def mocked_service(monkeypatch, tmp_path):
    import core.api.routes.sessions as sessions_route

    service = SessionService(path=tmp_path / "data" / "sessions.jsonl")
    monkeypatch.setattr(sessions_route, "_get_service", lambda: service)
    return service


class TestSessionsApi:
    def test_get_sessions_returns_entries(self, client, mocked_service):
        _write_log(
            mocked_service.sessions_path,
            [json.dumps(dict(SAMPLE_ENTRY, start="2026-08-16T20:00:00+00:00"))],
        )
        resp = client.get("/api/v1/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["total_gifts"] == 12
        assert data["total_gift_value_usd"] == 4.5
        assert data["sessions"][0]["likes"] == 340

    def test_get_sessions_empty_when_no_file(self, client, mocked_service):
        resp = client.get("/api/v1/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["sessions"] == []

    def test_get_report_markdown(self, client, mocked_service):
        _write_log(
            mocked_service.sessions_path,
            [json.dumps(dict(SAMPLE_ENTRY, start="2026-08-16T20:00:00+00:00"))],
        )
        resp = client.get("/api/v1/sessions/report")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/markdown")
        assert "Stream Session Report" in resp.text
        assert "## Session 1" in resp.text
