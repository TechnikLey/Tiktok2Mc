"""Stream analytics: configuration, in-memory aggregation and SQLite storage."""

from core.analytics.aggregator import SessionAggregator, get_analytics_aggregator
from core.analytics.config import (
    AnalyticsConfig,
    AnalyticsRetention,
    AnalyticsStoreFlags,
)
from core.analytics.store import AnalyticsStore

__all__ = [
    "AnalyticsConfig",
    "AnalyticsRetention",
    "AnalyticsStore",
    "AnalyticsStoreFlags",
    "SessionAggregator",
    "get_analytics_aggregator",
]
