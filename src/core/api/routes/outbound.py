"""Outbound channel endpoints (status + manual test dispatch).

Thin routes only — dispatch logic lives in
``core.api.outbound_dispatcher``.
"""

from fastapi import APIRouter, HTTPException

from core.api.outbound_dispatcher import get_outbound_dispatcher

router = APIRouter(tags=["Outbound"])


@router.get("/outbound/channels")
async def list_outbound_channels():
    """Return all configured outbound channels with breaker/counters."""
    return get_outbound_dispatcher().status()


@router.post("/outbound/channels/{name}/test")
async def test_outbound_channel(name: str):
    """Send a synthetic test message through one outbound channel."""
    try:
        ok, detail = await get_outbound_dispatcher().send_test(name)
    except LookupError:
        raise HTTPException(
            status_code=404, detail=f"Unknown outbound channel '{name}'"
        )
    return {"name": name, "ok": ok, "detail": detail}
