"""System control endpoints (restart signals)."""

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Request

from core.api.shutdown_signature import (
    HDR_IDENTITY,
    HDR_NONCE,
    HDR_SIGNATURE,
    HDR_TIMESTAMP,
    audit_shutdown_attempt,
    ensure_secret,
    verify_headers,
)
from core.lifecycle import SupervisorState, get_supervisor
from core.shutdown import ShutdownReason, get_shutdown_controller

log = logging.getLogger(__name__)

router = APIRouter(tags=["System"])


def _request_context(request: Request, *, reason: str = "") -> dict:
    """Collect every forensic detail about a shutdown request."""
    client = request.client.host if request.client else "unknown"
    ctx: dict = {
        "client": client,
        "method": request.method,
        "path": request.url.path,
        "query": str(request.url.query),
        "user_agent": request.headers.get("user-agent", ""),
        "origin": request.headers.get("origin", ""),
        "referer": request.headers.get("referer", ""),
        "x_shutdown_identity": request.headers.get(HDR_IDENTITY, ""),
        "x_shutdown_timestamp": request.headers.get(HDR_TIMESTAMP, ""),
        "x_shutdown_nonce": request.headers.get(HDR_NONCE, ""),
        "x_shutdown_signature_present": bool(request.headers.get(HDR_SIGNATURE, "")),
    }
    if reason:
        ctx["verdict"] = reason
    return ctx


def _log_and_audit(request: Request, reason: str, **extra: object) -> None:
    ctx = _request_context(request, reason=reason)
    ctx.update(extra)
    audit_shutdown_attempt(ctx)
    log.warning(
        "[SHUTDOWN-AUTH] %s client=%s method=%s path=%s identity=%r "
        "timestamp=%r user_agent=%r origin=%r signature_present=%s",
        reason,
        ctx["client"],
        ctx["method"],
        ctx["path"],
        ctx["x_shutdown_identity"],
        ctx["x_shutdown_timestamp"],
        ctx["user_agent"],
        ctx["origin"],
        ctx["x_shutdown_signature_present"],
    )


@router.post("/restart")
async def restart_system():
    """Request a clean restart of the backend services.

    The GUI shell survives the restart and reloads when the API comes back.
    """
    supervisor = get_supervisor()
    if supervisor.state not in {
        SupervisorState.IDLE,
        SupervisorState.STARTING,
        SupervisorState.RUNNING,
    }:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot restart while supervisor is in state {supervisor.state.value}",
        )
    try:
        asyncio.create_task(supervisor.restart())
        log.info("Restart requested via API")
        return {"status": "restart_requested"}
    except Exception as e:  # any unexpected error becomes an HTTP 500
        log.exception("Failed to request restart")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/shutdown/now")
async def shutdown_now(request: Request):
    """Trigger immediate shutdown of the entire application.

    Signed request required.  A valid HMAC signature over the canonical
    request must be present (``X-Shutdown-*`` headers) — the GUI signs
    with the per-install runtime secret.  Every attempt, accepted or
    rejected, is recorded in the shutdown audit log.

    Routes through the ShutdownController for proper diagnostics.
    The caller (GUI) gets an immediate response; the actual shutdown
    runs asynchronously with full logging and forensic state tracking.
    """
    ensure_secret()
    ok, reason = verify_headers(request.headers, method=request.method)
    if not ok:
        _log_and_audit(request, reason=f"rejected:{reason}")
        raise HTTPException(
            status_code=403,
            detail=f"Shutdown request rejected: {reason}",
        )

    identity = request.headers.get(HDR_IDENTITY, "unknown")
    ctrl = get_shutdown_controller()
    req = ctrl.request_shutdown(
        reason=ShutdownReason.USER_REQUEST,
        source=f"api:/api/v1/shutdown/now (identity={identity})",
        requester=_request_context(request),
    )
    if req is None:
        _log_and_audit(
            request,
            reason="rejected:shutdown_already_pending",
            shutdown_id=ctrl.accepted_request.id if ctrl.accepted_request else "",
        )
        return {
            "status": "shutdown_already_pending",
            "shutdown_id": (
                ctrl.accepted_request.id if ctrl.accepted_request else None
            ),
        }

    _log_and_audit(request, reason="accepted", shutdown_id=req.id, identity=identity)
    log.warning(
        "[SHUTDOWN] Request accepted (ID: %s) — authorized by signed "
        "identity %r from client %s",
        req.id,
        identity,
        request.client.host if request.client else "unknown",
    )
    return {"status": "shutdown_requested", "shutdown_id": req.id}
