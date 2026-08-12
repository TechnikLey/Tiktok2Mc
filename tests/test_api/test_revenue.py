"""Tests for the revenue log service and API endpoints."""

import pytest

from core.api.services.revenue import RevenueService

# ---------------------------------------------------------------------------
# RevenueService unit tests
# ---------------------------------------------------------------------------


def _write_log(path, lines):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.fixture
def revenue_service(tmp_path):
    return RevenueService(path=tmp_path / "data" / "revenue_log.jsonl")


class TestParseEntry:
    def test_parses_valid_line(self, revenue_service):
        entry = revenue_service._parse_entry(
            '{"date": "2026-08-01", "estimated_revenue_usd": 12.34}'
        )
        assert entry == {"date": "2026-08-01", "estimated_revenue_usd": 12.34}

    def test_rounds_value(self, revenue_service):
        entry = revenue_service._parse_entry(
            '{"date": "2026-08-01", "estimated_revenue_usd": 12.345}'
        )
        assert entry["estimated_revenue_usd"] == 12.35

    def test_accepts_int_value(self, revenue_service):
        entry = revenue_service._parse_entry(
            '{"date": "2026-08-01", "estimated_revenue_usd": 5}'
        )
        assert entry["estimated_revenue_usd"] == 5.0

    def test_rejects_invalid_json(self, revenue_service):
        assert revenue_service._parse_entry("not json") is None

    def test_rejects_missing_fields(self, revenue_service):
        assert revenue_service._parse_entry('{"date": "2026-08-01"}') is None
        assert revenue_service._parse_entry('{"estimated_revenue_usd": 1}') is None

    def test_rejects_non_dict(self, revenue_service):
        assert revenue_service._parse_entry("[1, 2, 3]") is None

    def test_rejects_empty_line(self, revenue_service):
        assert revenue_service._parse_entry("") is None
        assert revenue_service._parse_entry("   ") is None


class TestReadEntries:
    def test_reads_and_sorts_entries(self, revenue_service):
        _write_log(
            revenue_service.revenue_path,
            [
                '{"date": "2026-08-02", "estimated_revenue_usd": 20.0}',
                '{"date": "2026-08-01", "estimated_revenue_usd": 10.0}',
            ],
        )
        entries = revenue_service.read_entries()
        assert [e["date"] for e in entries] == ["2026-08-01", "2026-08-02"]

    def test_skips_malformed_lines(self, revenue_service):
        _write_log(
            revenue_service.revenue_path,
            [
                '{"date": "2026-08-01", "estimated_revenue_usd": 10.0}',
                "garbage",
                "",
            ],
        )
        entries = revenue_service.read_entries()
        assert len(entries) == 1

    def test_empty_when_file_missing(self, revenue_service):
        assert revenue_service.read_entries() == []
        assert revenue_service.get_file_info()["exists"] is False


class TestSummary:
    def test_computes_statistics(self, revenue_service):
        entries = [
            {"date": "2026-08-01", "estimated_revenue_usd": 10.0},
            {"date": "2026-08-02", "estimated_revenue_usd": 20.0},
            {"date": "2026-08-03", "estimated_revenue_usd": 30.0},
        ]
        summary = revenue_service.summary(entries)
        assert summary["count"] == 3
        assert summary["total_usd"] == 60.0
        assert summary["average_usd"] == 20.0
        assert summary["min_usd"] == 10.0
        assert summary["max_usd"] == 30.0
        assert summary["days_with_revenue"] == 3
        assert summary["last_change_usd"] == 10.0
        assert summary["last_change_day"] == "2026-08-03"

    def test_date_range_filter(self, revenue_service):
        entries = [
            {"date": "2026-08-01", "estimated_revenue_usd": 10.0},
            {"date": "2026-08-02", "estimated_revenue_usd": 20.0},
            {"date": "2026-08-03", "estimated_revenue_usd": 30.0},
        ]
        summary = revenue_service.summary(
            entries, start_date="2026-08-02", end_date="2026-08-02"
        )
        assert summary["count"] == 1
        assert summary["total_usd"] == 20.0

    def test_empty_summary(self, revenue_service):
        summary = revenue_service.summary([])
        assert summary["count"] == 0
        assert summary["total_usd"] == 0.0
        assert summary["average_usd"] == 0.0
        assert summary["last_change_usd"] is None
        assert summary["last7_usd"] == 0.0

    def test_last7_vs_prev7(self, revenue_service):
        entries = [
            {"date": f"2026-07-{d:02d}", "estimated_revenue_usd": 1.0}
            for d in range(1, 31)
        ]
        summary = revenue_service.summary(entries)
        assert summary["last7_usd"] == 7.0
        assert summary["prev7_usd"] == 7.0
        assert summary["last7_delta_usd"] == 0.0


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


@pytest.fixture
def mocked_service(monkeypatch, tmp_path):
    import core.api.routes.revenue as revenue_route

    service = RevenueService(path=tmp_path / "data" / "revenue_log.jsonl")
    monkeypatch.setattr(revenue_route, "_get_service", lambda: service)
    return service


class TestRevenueApi:
    def test_get_revenue_returns_entries(self, client, mocked_service):
        _write_log(
            mocked_service.revenue_path,
            [
                '{"date": "2026-08-01", "estimated_revenue_usd": 10.0}',
                '{"date": "2026-08-02", "estimated_revenue_usd": 20.0}',
            ],
        )
        resp = client.get("/api/v1/revenue")
        assert resp.status_code == 200
        data = resp.json()
        assert data["entries"] == [
            {"date": "2026-08-01", "estimated_revenue_usd": 10.0},
            {"date": "2026-08-02", "estimated_revenue_usd": 20.0},
        ]
        assert data["file"]["exists"] is True
        assert data["file"]["path"] == str(mocked_service.revenue_path)

    def test_get_revenue_empty_when_no_file(self, client, mocked_service):
        resp = client.get("/api/v1/revenue")
        assert resp.status_code == 200
        data = resp.json()
        assert data["entries"] == []
        assert data["file"]["exists"] is False

    def test_get_summary(self, client, mocked_service):
        _write_log(
            mocked_service.revenue_path,
            [
                '{"date": "2026-08-01", "estimated_revenue_usd": 10.0}',
                '{"date": "2026-08-02", "estimated_revenue_usd": 20.0}',
            ],
        )
        resp = client.get("/api/v1/revenue/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2
        assert data["total_usd"] == 30.0
        assert data["last_change_usd"] == 10.0

    def test_get_summary_with_date_filter(self, client, mocked_service):
        _write_log(
            mocked_service.revenue_path,
            [
                '{"date": "2026-08-01", "estimated_revenue_usd": 10.0}',
                '{"date": "2026-08-02", "estimated_revenue_usd": 20.0}',
            ],
        )
        resp = client.get("/api/v1/revenue/summary?start=2026-08-02")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["total_usd"] == 20.0
