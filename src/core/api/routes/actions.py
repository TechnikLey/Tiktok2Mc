from fastapi import APIRouter, HTTPException

from core.api.models import (
    ActionsResponse,
    ActionsUpdateRequest,
    RawActionsResponse,
    RawActionsUpdateRequest,
)
from core.api.services.actions import ActionsService

router = APIRouter(tags=["Actions"])
_service = ActionsService()


@router.get("/actions", response_model=ActionsResponse)
async def get_actions():
    """Return structured list of all triggers parsed from actions.mca."""
    try:
        triggers = _service.parse()
        return ActionsResponse(triggers=triggers)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/actions", response_model=ActionsResponse)
async def update_actions(body: ActionsUpdateRequest):
    """Save structured triggers back to actions.mca."""
    try:
        raw = _service.serialize([t.model_dump() for t in body.triggers])
        _service.write_raw(raw, backup=True)
        return ActionsResponse(triggers=_service.parse())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/actions/raw", response_model=RawActionsResponse)
async def get_actions_raw():
    """Return raw text of actions.mca with current diagnostics."""
    try:
        content = _service.read_raw()
        diagnostics = _service.validate(content)
        return RawActionsResponse(content=content, diagnostics=diagnostics)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/actions/raw", response_model=RawActionsResponse)
async def update_actions_raw(body: RawActionsUpdateRequest):
    """Save raw text directly to actions.mca."""
    try:
        _service.write_raw(body.content, backup=True)
        diagnostics = _service.validate(body.content)
        return RawActionsResponse(content=body.content, diagnostics=diagnostics)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/actions/validate")
async def validate_actions():
    """Validate current actions.mca and return diagnostics."""
    try:
        diagnostics = _service.validate()
        return {"diagnostics": diagnostics}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
