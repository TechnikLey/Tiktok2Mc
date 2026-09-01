import json
import logging
import re

from fastapi import APIRouter, HTTPException

import core.paths
from core.api.models import (
    ActionsResponse,
    ActionsUpdateRequest,
    RawActionsResponse,
    RawActionsUpdateRequest,
)
from core.api.services.actions import ActionsService
from core.validator import Severity

log = logging.getLogger(__name__)

router = APIRouter(tags=["Actions"])
_service: ActionsService | None = None


def _get_service() -> ActionsService:
    global _service
    if _service is None:
        _service = ActionsService()
    return _service


def _normalize_name(name: str) -> str:
    name = name.lower().strip()
    name = name.replace("_", " ")
    name = re.sub(r"[^a-z0-9\s]", " ", name)
    name = re.sub(r"\s+", " ", name)
    return name.strip()


def _build_gift_image_map() -> dict[str, str]:
    root = core.paths.get_root_dir()
    pics_dir = root / "assets" / "gifts_picture"
    if not pics_dir.exists():
        pics_dir = root / "core" / "assets" / "gifts_picture"
    if not pics_dir.exists():
        return {}
    mapping = {}
    for f in pics_dir.iterdir():
        if f.suffix.lower() != ".png":
            continue
        normalized = _normalize_name(f.stem)
        mapping[normalized] = f"/gifts-pictures/{f.name}"
    return mapping


@router.get("/actions", response_model=ActionsResponse)
async def get_actions():
    try:
        gifts = _load_gifts()
        triggers = _get_service().parse(gifts=gifts)
        return ActionsResponse(triggers=triggers)
    except Exception as e:  # any unexpected error becomes an HTTP 500
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/actions", response_model=ActionsResponse)
async def update_actions(body: ActionsUpdateRequest):
    try:
        validation_diags = _get_service().validate_triggers(
            [t.model_dump() for t in body.triggers]
        )
        errors = [d for d in validation_diags if d.get("severity") == "ERROR"]
        if errors:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid action configuration: {errors[0]['message']}",
            )

        raw = _get_service().serialize([t.model_dump() for t in body.triggers])
        _get_service().write_raw(raw, backup=True)
        gifts = _load_gifts()
        return ActionsResponse(triggers=_get_service().parse(gifts=gifts))
    except HTTPException:
        raise
    except Exception as e:  # any unexpected error becomes an HTTP 500
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/actions/raw", response_model=RawActionsResponse)
async def get_actions_raw():
    try:
        content = _get_service().read_raw()
        diagnostics = _get_service().validate(content)
        return RawActionsResponse(content=content, diagnostics=diagnostics)
    except Exception as e:  # any unexpected error becomes an HTTP 500
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/actions/raw")
async def update_actions_raw(body: RawActionsUpdateRequest):
    try:
        diagnostics = _get_service().validate(body.content)
        errors = [d for d in diagnostics if d.get("severity") == Severity.ERROR.value]
        if errors:
            raise HTTPException(
                status_code=422,
                detail=f"Cannot save — syntax errors detected: {diagnostics[0]['message']}",
            )
        _get_service().write_raw(body.content, backup=True)
        diagnostics = _get_service().validate(body.content)
        return RawActionsResponse(content=body.content, diagnostics=diagnostics)
    except Exception as e:  # any unexpected error becomes an HTTP 500
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/actions/validate")
async def validate_actions():
    try:
        diagnostics = _get_service().validate()
        return {"diagnostics": diagnostics}
    except Exception as e:  # any unexpected error becomes an HTTP 500
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/actions/validate")
async def validate_actions_content(body: RawActionsUpdateRequest):
    try:
        diagnostics = _get_service().validate(body.content)
        return {"diagnostics": diagnostics}
    except Exception as e:  # any unexpected error becomes an HTTP 500
        raise HTTPException(status_code=500, detail=str(e))


def _load_gifts() -> list[dict]:
    root = core.paths.get_root_dir()
    gifts_file = root / "core" / "gifts.json"
    if not gifts_file.exists():
        gifts_file = root / "defaults" / "gifts.json"
    if not gifts_file.exists():
        log.warning(
            "gifts.json not found at %s or %s",
            root / "defaults" / "gifts.json",
            root / "core" / "gifts.json",
        )
        return []
    try:
        return json.loads(gifts_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
        log.error("Failed to load gifts.json: %s", e)
        return []


@router.get("/gifts")
async def get_gifts():
    try:
        gifts = _load_gifts()
        image_map = _build_gift_image_map()
        for g in gifts:
            normalized = _normalize_name(g.get("name", ""))
            g["image_url"] = image_map.get(normalized, "")
        gifts.sort(key=lambda g: (g.get("coins", 0), g.get("name", "")))
        return {"gifts": gifts}
    except Exception as e:  # any unexpected error becomes an HTTP 500
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/actions/scripts")
async def get_registered_scripts():
    try:
        from core.hook_api import HOOK_ACTIONS
        from core.hook_loader import load_event_hooks

        if not HOOK_ACTIONS:
            try:
                from core.paths import get_base_dir, get_root_dir

                candidates = []
                base_dir = get_base_dir()
                root_dir = get_root_dir()
                candidates.append((base_dir / ".." / "hooks").resolve())
                candidates.append(root_dir / "src" / "hooks")
                candidates.append(root_dir / "hooks")

                hooks_dir = None
                for p in candidates:
                    if p.is_dir():
                        hooks_dir = p
                        break

                if hooks_dir:

                    class _StubAPI:
                        def register_action(self, name: str, fn) -> None:
                            HOOK_ACTIONS[name] = fn

                        def for_hook(self, name: str, **_kw) -> "_StubAPI":
                            return self

                        def __getattr__(self, _name: str):
                            return lambda *args, **kwargs: None

                    load_event_hooks(_StubAPI(), hooks_dir)
                    log.info(
                        f"[SCRIPTS] Lazy-loaded {len(HOOK_ACTIONS)} hook(s) from {hooks_dir}"
                    )
                else:
                    log.warning(
                        f"[SCRIPTS] No hooks directory found among: {candidates}"
                    )
            except Exception as e:  # script listing must survive lazy-load failures
                log.warning(f"[SCRIPTS] Could not lazy-load hooks: {e}")

        scripts = [{"name": name} for name in sorted(HOOK_ACTIONS.keys())]
        return {"scripts": scripts}
    except Exception as e:  # any unexpected error becomes an HTTP 500
        log.error(f"Failed to get registered scripts: {e}")
        raise HTTPException(status_code=500, detail=str(e))
