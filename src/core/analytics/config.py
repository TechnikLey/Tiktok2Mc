"""Configuration model for the analytics subsystem.

The bridge reads the ``analytics`` block from ``config.yaml`` and converts it
into an :class:`AnalyticsConfig`.  Parsing is intentionally tolerant: a
missing or malformed value falls back to the documented default instead of
preventing the bridge from starting.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _as_bool(value: object, default: bool) -> bool:
    """Return *value* as a boolean, falling back to *default*.

    YAML users may write ``yes``/``no`` or ``1``/``0``; both are accepted so a
    hand-edited config does not silently change the analytics scope.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def _as_int(value: object, default: int, *, minimum: int = 0) -> int:
    """Return *value* as an integer clamped to *minimum*, or *default*."""
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return max(minimum, value)
    if isinstance(value, float) and value.is_integer():
        return max(minimum, int(value))
    if isinstance(value, str):
        try:
            return max(minimum, int(value.strip()))
        except ValueError:
            return default
    return default


@dataclass(frozen=True)
class AnalyticsRetention:
    """Retention windows (in days) for the analytics database tiers."""

    details_days: int = 90
    summaries_days: int = 0
    raw_events_days: int = 7
    aggregates_days: int = 0

    @classmethod
    def from_mapping(cls, raw: object) -> AnalyticsRetention:
        """Build retention settings from a mapping, tolerating bad values."""
        data = raw if isinstance(raw, dict) else {}
        return cls(
            details_days=_as_int(data.get("details_days"), 90),
            summaries_days=_as_int(data.get("summaries_days"), 0),
            raw_events_days=_as_int(data.get("raw_events_days"), 7),
            aggregates_days=_as_int(data.get("aggregates_days"), 0),
        )

    def to_dict(self) -> dict[str, int]:
        """Return the retention settings as a plain mapping."""
        return {
            "details_days": self.details_days,
            "summaries_days": self.summaries_days,
            "raw_events_days": self.raw_events_days,
            "aggregates_days": self.aggregates_days,
        }


@dataclass(frozen=True)
class AnalyticsStoreFlags:
    """Which analytics tiers are persisted.

    Totals and unique counters are always kept in memory; these flags only
    control whether the detailed rows are written to SQLite.
    """

    viewer_details: bool = True
    gift_details: bool = True
    top_lists: bool = True
    lifetime_aggregates: bool = True
    comment_text: bool = False
    raw_events: bool = False

    @classmethod
    def from_mapping(cls, raw: object) -> AnalyticsStoreFlags:
        """Build store flags from a mapping, tolerating bad values."""
        data = raw if isinstance(raw, dict) else {}
        return cls(
            viewer_details=_as_bool(data.get("viewer_details"), True),
            gift_details=_as_bool(data.get("gift_details"), True),
            top_lists=_as_bool(data.get("top_lists"), True),
            lifetime_aggregates=_as_bool(data.get("lifetime_aggregates"), True),
            comment_text=_as_bool(data.get("comment_text"), False),
            raw_events=_as_bool(data.get("raw_events"), False),
        )

    def to_dict(self) -> dict[str, bool]:
        """Return the store flags as a plain mapping."""
        return {
            "viewer_details": self.viewer_details,
            "gift_details": self.gift_details,
            "top_lists": self.top_lists,
            "lifetime_aggregates": self.lifetime_aggregates,
            "comment_text": self.comment_text,
            "raw_events": self.raw_events,
        }


@dataclass(frozen=True)
class AnalyticsConfig:
    """Complete analytics configuration derived from ``config.yaml``."""

    enabled: bool = True
    store: AnalyticsStoreFlags = field(default_factory=AnalyticsStoreFlags)
    top_n: int = 10
    max_tracked_viewers: int = 50_000
    flush_interval_seconds: int = 30
    retention: AnalyticsRetention = field(default_factory=AnalyticsRetention)

    @classmethod
    def from_mapping(cls, raw: object) -> AnalyticsConfig:
        """Build the configuration from the ``analytics`` config section.

        Args:
            raw: The value of the ``analytics`` key. Non-mapping values are
                treated as an empty section so defaults apply.

        Returns:
            A validated configuration. Numeric values are clamped to safe
            minimums; booleans accept common YAML spellings.
        """
        data: dict[str, Any] = raw if isinstance(raw, dict) else {}
        return cls(
            enabled=_as_bool(data.get("enabled"), True),
            store=AnalyticsStoreFlags.from_mapping(data.get("store")),
            top_n=_as_int(data.get("top_n"), 10, minimum=1),
            max_tracked_viewers=_as_int(
                data.get("max_tracked_viewers"), 50_000, minimum=1
            ),
            flush_interval_seconds=_as_int(
                data.get("flush_interval_seconds"), 30, minimum=1
            ),
            retention=AnalyticsRetention.from_mapping(data.get("retention")),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return the configuration as a JSON-serialisable mapping."""
        return {
            "enabled": self.enabled,
            "store": self.store.to_dict(),
            "top_n": self.top_n,
            "max_tracked_viewers": self.max_tracked_viewers,
            "flush_interval_seconds": self.flush_interval_seconds,
            "retention": self.retention.to_dict(),
        }
