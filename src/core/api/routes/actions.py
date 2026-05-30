import json
import logging
import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from core.api.models import (
    ActionsResponse,
    ActionsUpdateRequest,
    RawActionsResponse,
    RawActionsUpdateRequest,
)
from core.api.services.actions import ActionsService
from core.paths import get_root_dir
from core.validator import Severity

log = logging.getLogger(__name__)

router = APIRouter(tags=["Actions"])
_service = ActionsService()

_IMAGE_RE = re.compile(r"[^a-zA-Z0-9 ]")


def _gift_image_path(gift: dict, index: int) -> str:
    """Build the image URL path for a gift based on its position in the file."""
    idx = index + 1
    name = gift.get("name", "")
    safe = _IMAGE_RE.sub("", name).strip()
    safe = re.sub(r"\s+", "_", safe)
    return f"/gifts-pictures/{str(idx).zfill(3)}_{safe}.png"


@router.get("/actions", response_model=ActionsResponse)
async def get_actions():
    """Return structured list of all triggers parsed from actions.mca."""
    try:
        gifts = _load_gifts()
        triggers = _service.parse(gifts=gifts)
        return ActionsResponse(triggers=triggers)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/actions", response_model=ActionsResponse)
async def update_actions(body: ActionsUpdateRequest):
    """Save structured triggers back to actions.mca."""
    try:
        # Validate triggers before saving
        validation_diags = _service.validate_triggers([t.model_dump() for t in body.triggers])
        errors = [d for d in validation_diags if d.get("severity") == "ERROR"]
        if errors:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid action configuration: {errors[0]['message']}"
            )
        
        raw = _service.serialize([t.model_dump() for t in body.triggers])
        _service.write_raw(raw, backup=True)
        gifts = _load_gifts()
        return ActionsResponse(triggers=_service.parse(gifts=gifts))
    except HTTPException:
        raise
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


@router.put("/actions/raw")
async def update_actions_raw(body: RawActionsUpdateRequest):
    """Save raw text directly to actions.mca — validates BEFORE writing.

    If the content has any ERROR-level diagnostics the save is rejected
    with 422 Unprocessable Entity and the diagnostics are returned.
    """
    try:
        diagnostics = _service.validate(body.content)
        errors = [d for d in diagnostics if d.get("severity") == Severity.ERROR.value]
        if errors:
            return JSONResponse(
                status_code=422,
                content={
                    "detail": "Cannot save — syntax errors detected.",
                    "diagnostics": diagnostics,
                },
            )
        _service.write_raw(body.content, backup=True)
        # Re-validate after write (should still be clean)
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


@router.post("/actions/validate")
async def validate_actions_content(body: RawActionsUpdateRequest):
    """Validate arbitrary actions.mca content and return diagnostics."""
    try:
        diagnostics = _service.validate(body.content)
        return {"diagnostics": diagnostics}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Gifts ──────────────────────────────────────────────────────────


def _load_gifts() -> list[dict]:
    """Load gifts from gifts.json (dev: defaults/, release: core/)."""
    root = get_root_dir()
    # Release layout: core/gifts.json  Dev layout: defaults/gifts.json
    gifts_file = root / "core" / "gifts.json"
    if not gifts_file.exists():
        gifts_file = root / "defaults" / "gifts.json"
    if not gifts_file.exists():
        log.warning("gifts.json not found at %s or %s",
                     root / "defaults" / "gifts.json",
                     root / "core" / "gifts.json")
        return []
    try:
        return json.loads(gifts_file.read_text(encoding="utf-8"))
    except Exception as e:
        log.error("Failed to load gifts.json: %s", e)
        return []


@router.get("/gifts")
async def get_gifts():
    """Return all gifts from defaults/gifts.json, sorted by coin cost."""
    try:
        gifts = _load_gifts()
        for i, g in enumerate(gifts):
            g["image_url"] = _gift_image_path(g, i)
        gifts.sort(key=lambda g: (g.get("coins", 0), g.get("name", "")))
        return {"gifts": gifts}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/actions/scripts")
async def get_registered_scripts():
    """Return list of all registered scripts from the hook registry.
    
    Format: [
        {"name": "script_name", "description": "optional description"},
        ...
    ]
    """
    try:
        from core.hook_api import HOOK_ACTIONS
        from core.hook_loader import load_event_hooks
        from pathlib import Path

        if not HOOK_ACTIONS:
            try:
                from core.paths import get_base_dir, get_root_dir

                candidates = []
                base_dir = get_base_dir()
                root_dir = get_root_dir()
                candidates.append((base_dir / ".." / "event_hooks").resolve())
                candidates.append(root_dir / "src" / "event_hooks")
                candidates.append(root_dir / "event_hooks")

                hooks_dir = None
                for p in candidates:
                    if p.is_dir():
                        hooks_dir = p
                        break

                if hooks_dir:
                    class _StubAPI:
                        def register_action(self, name: str, fn) -> None:
                            HOOK_ACTIONS[name] = fn
                        def __getattr__(self, _name: str):
                            return lambda *args, **kwargs: None
                    load_event_hooks(_StubAPI(), hooks_dir)
                    log.info(f"[SCRIPTS] Lazy-loaded {len(HOOK_ACTIONS)} hook(s) from {hooks_dir}")
                else:
                    log.warning(f"[SCRIPTS] No hooks directory found among: {candidates}")
            except Exception as e:
                log.warning(f"[SCRIPTS] Could not lazy-load hooks: {e}")

        scripts = [
            {"name": name}
            for name in sorted(HOOK_ACTIONS.keys())
        ]
        return {"scripts": scripts}
    except Exception as e:
        log.error(f"Failed to get registered scripts: {e}")
        raise HTTPException(status_code=500, detail=str(e))
