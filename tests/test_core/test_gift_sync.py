"""Tests for core.gift_sync (TikTok gift catalog auto-sync)."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from core.gift_sync import (
    GiftSyncError,
    diff_catalogs,
    fetch_fallback_gifts,
    normalize_entries,
    read_catalog,
    sync_gifts,
    write_catalog,
)


class TestNormalizeEntries:
    def test_official_shape(self):
        raw = [
            {"id": 1, "name": "Rose", "diamond_count": 1},
            {"id": 2, "name": "Lion", "diamond_count": 1000},
        ]
        out = normalize_entries(raw)
        assert [(e["id"], e["name"], e["coins"]) for e in out] == [
            (1, "Rose", 1),
            (2, "Lion", 1000),
        ]

    def test_skips_bad_entries(self):
        raw = [
            {"id": "x", "name": "bad"},
            {"id": 1, "name": ""},
            {"id": 2, "name": "ok", "diamond_count": None},
        ]
        assert normalize_entries(raw) == [{"name": "ok", "coins": 0, "id": 2}]

    def test_dedupe_id_later_wins(self):
        raw = [
            {"id": 1, "name": "a", "diamond_count": 1},
            {"id": 1, "name": "b", "diamond_count": 2},
        ]
        assert normalize_entries(raw) == [{"name": "b", "coins": 2, "id": 1}]

    def test_fallback_coins_key(self):
        raw = [{"id": 3, "name": "x", "coins": 5}]
        assert normalize_entries(raw)[0]["coins"] == 5

    def test_sorted_deterministic(self):
        raw = [
            {"id": 1, "name": "b", "diamond_count": 5},
            {"id": 2, "name": "a", "diamond_count": 1},
        ]
        out = normalize_entries(raw)
        assert [e["coins"] for e in out] == [1, 5]


class TestDiffCatalogs:
    def test_added_removed_renamed(self):
        old = [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]
        new = [{"id": 1, "name": "a2"}, {"id": 3, "name": "c"}]
        assert diff_catalogs(old, new) == {"added": 1, "removed": 1, "renamed": 1}


class TestReadCatalog:
    def test_missing(self, tmp_path):
        assert read_catalog(tmp_path / "nope.json") == []

    def test_invalid(self, tmp_path):
        p = tmp_path / "x.json"
        p.write_text("{bad", encoding="utf-8")
        assert read_catalog(p) == []

    def test_valid(self, tmp_path):
        p = tmp_path / "x.json"
        p.write_text(json.dumps([{"id": 1, "name": "a", "coins": 1}]), encoding="utf-8")
        assert read_catalog(p) == [{"id": 1, "name": "a", "coins": 1}]


class TestWriteCatalog:
    def test_atomic(self, tmp_path):
        p = tmp_path / "sub" / "gifts.json"
        write_catalog(p, [{"id": 1, "name": "a", "coins": 1}])
        assert p.exists()
        assert json.loads(p.read_text(encoding="utf-8")) == [
            {"id": 1, "name": "a", "coins": 1}
        ]
        assert not list((tmp_path / "sub").glob(".*tmp"))

    def test_overwrites(self, tmp_path):
        p = tmp_path / "g.json"
        write_catalog(p, [{"id": 1, "name": "a", "coins": 1}])
        write_catalog(p, [{"id": 2, "name": "b", "coins": 2}])
        assert json.loads(p.read_text(encoding="utf-8")) == [
            {"id": 2, "name": "b", "coins": 2}
        ]


class TestFetchFallback:
    def test_top_level_list(self):
        resp = type("R", (), {})()
        resp.raise_for_status = lambda: None
        resp.json = lambda: [{"id": 1, "name": "Rose", "diamond_count": 1}]
        with patch("core.gift_sync.requests.get", return_value=resp):
            assert fetch_fallback_gifts() == [
                {"id": 1, "name": "Rose", "diamond_count": 1}
            ]

    def test_failure(self):
        resp = type("R", (), {})()
        resp.raise_for_status = lambda: None
        resp.json = lambda: {"data": {"gifts": []}}
        with patch("core.gift_sync.requests.get", return_value=resp), pytest.raises(GiftSyncError):
            fetch_fallback_gifts()


class TestSyncGifts:
    def test_success_overwrites_and_backs_up(self, tmp_path):
        target = tmp_path / "core" / "gifts.json"
        target.parent.mkdir()
        target.write_text(
            json.dumps([{"id": 99, "name": "old", "coins": 1}]), encoding="utf-8"
        )

        raw = [
            {"id": 1, "name": "Rose", "diamond_count": 1},
            {"id": 2, "name": "Lion", "diamond_count": 1000},
        ]

        with (
            patch("core.gift_sync.fetch_official_gifts", return_value=raw),
            patch("core.gift_sync._backup_existing") as backup,
        ):
            summary = sync_gifts(target_file=target, source="official")

        assert summary["ok"] is True
        assert summary["total"] == 2
        assert summary["added"] == 2
        assert summary["removed"] == 1
        backup.assert_called_once()
        data = json.loads(target.read_text(encoding="utf-8"))
        assert [e["id"] for e in data] == [1, 2]

    def test_fallback_chain(self, tmp_path):
        target = tmp_path / "g.json"
        raw = [{"id": 1, "name": "Rose", "diamond_count": 1}]
        with (
            patch(
                "core.gift_sync.fetch_official_gifts", side_effect=GiftSyncError("boom")
            ),
            patch("core.gift_sync.fetch_fallback_gifts", return_value=raw),
        ):
            summary = sync_gifts(target_file=target, source="auto")
        assert summary["ok"] is True
        assert summary["source"] == "fallback"

    def test_all_fail(self, tmp_path):
        target = tmp_path / "g.json"
        with (
            patch(
                "core.gift_sync.fetch_official_gifts", side_effect=GiftSyncError("boom")
            ),
            patch(
                "core.gift_sync.fetch_fallback_gifts",
                side_effect=GiftSyncError("boom2"),
            ),
        ):
            summary = sync_gifts(target_file=target, source="auto")
        assert summary["ok"] is False
        assert "boom" in summary["error"]

    def test_empty_payload(self, tmp_path):
        target = tmp_path / "g.json"
        with patch("core.gift_sync.fetch_official_gifts", return_value=[]):
            summary = sync_gifts(target_file=target, source="official")
        assert summary["ok"] is False

    def test_unknown_source_no_fail(self, tmp_path):
        target = tmp_path / "g.json"
        with patch(
            "core.gift_sync.fetch_official_gifts",
            return_value=[{"id": 1, "name": "x", "diamond_count": 1}],
        ):
            summary = sync_gifts(target_file=target, source="official")
        assert summary["ok"] is True
