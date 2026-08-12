#!/usr/bin/env python3
"""RevenueService — read the daily gift revenue log.

The bridge persists one JSONL entry per day (``data/revenue_log.jsonl``)
with ``{"date": "YYYY-MM-DD", "estimated_revenue_usd": <float>}``.
This service reads that file, tolerates malformed lines, and computes
lightweight summaries used by the GUI revenue view.
"""

import json
import logging
from pathlib import Path
from typing import Any

from core.paths import get_root_dir

log = logging.getLogger(__name__)


class RevenueService:
    """Read and summarise the daily revenue log."""

    def __init__(self, path: Path | None = None) -> None:
        self._revenue_path: Path | None = path

    @property
    def revenue_path(self) -> Path:
        if self._revenue_path is None:
            self._revenue_path = (
                get_root_dir() / "data" / "revenue_log.jsonl"
            ).resolve()
        return self._revenue_path

    @staticmethod
    def _parse_entry(line: str) -> dict[str, Any] | None:
        """Parse one JSONL line into a revenue entry, or None if malformed."""
        line = line.strip()
        if not line:
            return None
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict):
            return None
        date = data.get("date")
        value = data.get("estimated_revenue_usd")
        if not isinstance(date, str) or not isinstance(value, (int, float)):
            return None
        return {"date": date, "estimated_revenue_usd": round(float(value), 2)}

    def read_entries(self) -> list[dict[str, Any]]:
        """Return all valid revenue entries, oldest first."""
        path = self.revenue_path
        if not path.exists():
            return []
        entries: list[dict[str, Any]] = []
        try:
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    entry = self._parse_entry(line)
                    if entry is not None:
                        entries.append(entry)
        except OSError as e:
            log.warning("Failed to read revenue log %s: %s", path, e)
            return []
        entries.sort(key=lambda e: e["date"])
        return entries

    def get_file_info(self) -> dict[str, Any]:
        """Return metadata about the revenue file itself."""
        path = self.revenue_path
        info: dict[str, Any] = {"exists": False, "path": str(path)}
        if path.exists():
            try:
                stat = path.stat()
                info["exists"] = True
                info["size"] = stat.st_size
                info["modified"] = stat.st_mtime
            except OSError as e:
                log.warning("Failed to stat revenue log %s: %s", path, e)
        return info

    def summary(
        self,
        entries: list[dict[str, Any]] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        """Compute summary statistics over ``entries`` (optionally date-filtered).

        ``start_date``/``end_date`` are inclusive ``YYYY-MM-DD`` bounds.
        """
        if entries is None:
            entries = self.read_entries()

        filtered = [e for e in entries if _in_range(e["date"], start_date, end_date)]
        filtered.sort(key=lambda e: e["date"])
        values = [e["estimated_revenue_usd"] for e in filtered]

        total = round(sum(values), 2)
        count = len(values)
        result: dict[str, Any] = {
            "count": count,
            "total_usd": total,
            "average_usd": round(total / count, 2) if count else 0.0,
            "min_usd": round(min(values), 2) if values else 0.0,
            "max_usd": round(max(values), 2) if values else 0.0,
            "min_day": min(e["date"] for e in filtered) if values else None,
            "max_day": max(e["date"] for e in filtered) if values else None,
            "days_with_revenue": sum(1 for v in values if v > 0),
        }

        # Day-over-day change between the two most recent days in range.
        result["last_change_usd"] = None
        result["last_change_day"] = None
        if count >= 2:
            result["last_change_usd"] = round(values[-1] - values[-2], 2)
            result["last_change_day"] = filtered[-1]["date"]

        # Last 7 days vs the 7 days before that.
        result["last7_usd"] = round(sum(values[-7:]), 2)
        result["prev7_usd"] = round(sum(values[-14:-7]), 2)
        result["last7_delta_usd"] = round(result["last7_usd"] - result["prev7_usd"], 2)

        return result


def _in_range(date: str, start_date: str | None, end_date: str | None) -> bool:
    if start_date and date < start_date:
        return False
    return not (end_date and date > end_date)
