"""Tests for analytics configuration parsing."""

from core.analytics.config import AnalyticsConfig


class TestAnalyticsConfig:
    def test_defaults(self):
        cfg = AnalyticsConfig.from_mapping(None)

        assert cfg.enabled is True
        assert cfg.store.viewer_details is True
        assert cfg.store.gift_details is True
        assert cfg.store.top_lists is True
        assert cfg.store.lifetime_aggregates is True
        assert cfg.store.comment_text is False
        assert cfg.store.raw_events is False
        assert cfg.top_n == 10
        assert cfg.max_tracked_viewers == 50_000
        assert cfg.flush_interval_seconds == 30
        assert cfg.retention.details_days == 90
        assert cfg.retention.summaries_days == 0
        assert cfg.retention.raw_events_days == 7
        assert cfg.retention.aggregates_days == 0

    def test_yaml_style_values_and_clamping(self):
        cfg = AnalyticsConfig.from_mapping(
            {
                "enabled": "no",
                "store": {"viewer_details": "false", "comment_text": "yes"},
                "top_n": 0,
                "max_tracked_viewers": -5,
                "flush_interval_seconds": "15",
                "retention": {"details_days": "7", "summaries_days": -1},
            }
        )

        assert cfg.enabled is False
        assert cfg.store.viewer_details is False
        assert cfg.store.comment_text is True
        assert cfg.top_n == 1
        assert cfg.max_tracked_viewers == 1
        assert cfg.flush_interval_seconds == 15
        assert cfg.retention.details_days == 7
        assert cfg.retention.summaries_days == 0

    def test_non_mapping_section_uses_defaults(self):
        cfg = AnalyticsConfig.from_mapping(["not", "a", "mapping"])

        assert cfg.enabled is True
        assert cfg.top_n == 10

    def test_to_dict_round_trip(self):
        cfg = AnalyticsConfig.from_mapping({"top_n": 3, "store": {"raw_events": True}})

        data = cfg.to_dict()

        assert data["top_n"] == 3
        assert data["store"]["raw_events"] is True
        assert data["retention"]["details_days"] == 90
