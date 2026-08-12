"""Revenue log endpoints (daily gift revenue viewer)."""

import logging

from fastapi import APIRouter, Query

from core.api.models import RevenueResponse, RevenueSummary
from core.api.services.revenue import RevenueService

log = logging.getLogger(__name__)

router = APIRouter(tags=["Revenue"])
_service: RevenueService | None = None


def _get_service() -> RevenueService:
    global _service
    if _service is None:
        _service = RevenueService()
    return _service


@router.get("/revenue", response_model=RevenueResponse)
async def get_revenue():
    """Return all revenue log entries plus metadata about the log file."""
    service = _get_service()
    return {
        "entries": service.read_entries(),
        "file": service.get_file_info(),
    }


@router.get("/revenue/summary", response_model=RevenueSummary)
async def get_revenue_summary(
    start: str | None = Query(None, description="Inclusive start date YYYY-MM-DD"),
    end: str | None = Query(None, description="Inclusive end date YYYY-MM-DD"),
):
    """Return summary statistics over the revenue log, optionally date-filtered."""
    service = _get_service()
    return service.summary(start_date=start, end_date=end)
