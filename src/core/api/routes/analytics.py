"""All-time analytics leaderboard endpoints."""

import logging

from fastapi import APIRouter, Query

from core.api.models import LeaderboardResponse
from core.api.services.analytics import AnalyticsService

log = logging.getLogger(__name__)

router = APIRouter(tags=["Analytics"])
_service: AnalyticsService | None = None


def _get_service() -> AnalyticsService:
    """Return the process-wide analytics service."""
    global _service
    if _service is None:
        _service = AnalyticsService()
    return _service


@router.get("/analytics/leaderboard", response_model=LeaderboardResponse)
async def get_analytics_leaderboard(
    limit: int = Query(10, ge=1, le=100, description="Entries per leaderboard"),
):
    """Return all-time gifters, likers, commenters and gift leaderboards."""
    service = _get_service()
    return {
        "generated_at": service.generated_at(),
        **service.leaderboard(limit=limit),
    }
