"""SessionService — read and summarise the stream session log.

The bridge appends one JSONL line per completed live stream to
``data/sessions.jsonl`` with session start/end, duration and event totals.
This service reads that file, tolerates malformed lines, and produces the
data + markdown report used by the GUI sessions view.
"""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.paths import get_root_dir

log = logging.getLogger(__name__)

_TOTAL_FIELDS = (
    "gifts",
    "gift_value_usd",
    "likes",
    "follows",
    "comments",
    "shares",
    "joins",
)


class SessionService:
    """Read and summarise the stream session log."""

    def __init__(self, path: Path | None = None) -> None:
        self._sessions_path: Path | None = path

    @property
    def sessions_path(self) -> Path:
        if self._sessions_path is None:
            self._sessions_path = (get_root_dir() / "data" / "sessions.jsonl").resolve()
        return self._sessions_path

    @staticmethod
    def _parse_entry(line: str) -> dict[str, Any] | None:
        """Parse one JSONL line into a session entry, or None if malformed."""
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

    def read_entries(self) -> list[dict[str, Any]]:
        """Return all valid session entries, oldest first."""
        path = self.sessions_path
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
            log.warning("Failed to read sessions log %s: %s", path, e)
            return []
        entries.sort(key=lambda e: e["start"])
        return entries

    def get_file_info(self) -> dict[str, Any]:
        """Return metadata about the sessions file itself."""
        path = self.sessions_path
        info: dict[str, Any] = {"exists": False, "path": str(path)}
        if path.exists():
            try:
                stat = path.stat()
                info["exists"] = True
                info["size"] = stat.st_size
                info["modified"] = stat.st_mtime
            except OSError as e:
                log.warning("Failed to stat sessions log %s: %s", path, e)
        return info

    def summary(self, entries: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        """Compute totals over ``entries`` and return them alongside the list."""
        if entries is None:
            entries = self.read_entries()

        totals: dict[str, float] = {field: 0 for field in _TOTAL_FIELDS}
        for entry in entries:
            for field in _TOTAL_FIELDS:
                value = entry.get(field, 0)
                if isinstance(value, (int, float)):
                    totals[field] += value

        return {
            "total": len(entries),
            "total_gifts": int(totals["gifts"]),
            "total_gift_value_usd": round(totals["gift_value_usd"], 2),
            "total_likes": int(totals["likes"]),
            "total_follows": int(totals["follows"]),
            "total_comments": int(totals["comments"]),
            "total_shares": int(totals["shares"]),
            "total_joins": int(totals["joins"]),
            "sessions": entries,
        }

    def generate_markdown(self, entries: list[dict[str, Any]] | None = None) -> str:
        """Render a human-readable Markdown report of all sessions."""
        if entries is None:
            entries = self.read_entries()
        summary = self.summary(entries)

        lines = [
            "# TikTok2Mc — Stream Session Report",
            "",
            f"- Generated: {datetime.now(UTC).isoformat(timespec='seconds')}",
            f"- Sessions: {summary['total']}",
            (
                f"- Gifts: {summary['total_gifts']} "
                f"({summary['total_gift_value_usd']:.2f} $)"
            ),
            f"- Likes: {summary['total_likes']}",
            f"- Follows: {summary['total_follows']}",
            f"- Comments: {summary['total_comments']}",
            f"- Shares: {summary['total_shares']}",
            f"- Joins: {summary['total_joins']}",
            "",
        ]

        if not entries:
            lines.append("_No sessions recorded yet._")
            lines.append("")
            return "\n".join(lines)

        for index, entry in enumerate(reversed(entries), start=1):
            lines += [
                f"## Session {index}",
                "",
                f"- Start: {entry.get('start', '?')}",
                f"- End: {entry.get('end', '?')}",
                f"- Duration: {_format_duration(entry.get('duration_seconds', 0))}",
                (
                    f"- Gifts: {entry.get('gifts', 0)} "
                    f"({entry.get('gift_value_usd', 0):.2f} $)"
                ),
                f"- Likes: {entry.get('likes', 0)}",
                f"- Follows: {entry.get('follows', 0)}",
                f"- Comments: {entry.get('comments', 0)}",
                f"- Shares: {entry.get('shares', 0)}",
                f"- Joins: {entry.get('joins', 0)}",
                "",
            ]
        return "\n".join(lines)


def _format_duration(seconds: float) -> str:
    """Format a duration in seconds as ``Xh Ym Zs`` / ``Ym Zs`` / ``Zs``."""
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes:02d}m {secs:02d}s"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"
