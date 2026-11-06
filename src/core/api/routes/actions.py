"""REST endpoints for ``data/actions.mca`` and the gift catalog."""

import json
import logging
import re

from fastapi import APIRouter, HTTPException

import core.paths
from core.api.models import (
    ActionsResponse,
    ActionsUpdateRequest,
    GiftSyncRequest,
    RawActionsResponse,
    RawActionsUpdateRequest,
)
from core.api.services.actions import ActionsService
from core.validator import Severity

log = logging.getLogger(__name__)

router = APIRouter(tags=["Actions"])
_service: ActionsService | None = None


def _get_service() -> ActionsService:
    """Return the lazily created module-level ``ActionsService``."""
    global _service
    if _service is None:
        _service = ActionsService()
    return _service


def _normalize_name(name: str) -> str:
    """Normalise a display name for gift-image matching.

Lowercases, treats underscores and punctuation as spaces, and collapses
repeated whitespace."""

    name = name.lower().strip()
    name = name.replace("_", " ")
    name = re.sub(r"[^a-z0-9\s]", " ", name)
    name = re.sub(r"\s+", " ", name)
    return name.strip()


def _build_gift_image_map() -> dict[str, str]:
    """Map normalised gift names to served image URLs.

Checks the active versioned app directory first, then the install root.
Missing directories simply produce an empty map."""

    try:
        from core.paths import get_active_app_dir
        active = get_active_app_dir()
    except Exception:
        active = None
    root = core.paths.get_root_dir()
    candidates = []
    if active is not None:
        candidates.append(active / "core" / "assets" / "gifts_picture")
    candidates.append(root / "core" / "assets" / "gifts_picture")
    candidates.append(root / "assets" / "gifts_picture")
    pics_dir = next((p for p in candidates if p.exists()), None)
    if pics_dir is None:
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
    """Return all parsed action triggers (``GET /actions``)."""
    try:
        gifts = _load_gifts()
        triggers = _get_service().parse(gifts=gifts)
        return ActionsResponse(triggers=triggers)
    except Exception as e:  # any unexpected error becomes an HTTP 500
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/actions", response_model=ActionsResponse)
async def update_actions(body: ActionsUpdateRequest):
    """Validate, serialise and persist structured triggers (``PUT /actions``).

Raises 422 when validation reports errors; a backup is written before the
file is replaced."""

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
    """Return raw ``.mca`` content plus diagnostics (``GET /actions/raw``)."""
    try:
        content = _get_service().read_raw()
        diagnostics = _get_service().validate(content)
        return RawActionsResponse(content=content, diagnostics=diagnostics)
    except Exception as e:  # any unexpected error becomes an HTTP 500
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/actions/raw")
async def update_actions_raw(body: RawActionsUpdateRequest):
    """Validate and persist raw ``.mca`` content (``PUT /actions/raw``).

Content with error-severity diagnostics is rejected with 422."""

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
    """Validate the stored ``.mca`` file (``GET /actions/validate``)."""
    try:
        diagnostics = _get_service().validate()
        return {"diagnostics": diagnostics}
    except Exception as e:  # any unexpected error becomes an HTTP 500
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/actions/validate")
async def validate_actions_content(body: RawActionsUpdateRequest):
    """Validate the supplied ``.mca`` content (``POST /actions/validate``)."""
    try:
        diagnostics = _get_service().validate(body.content)
        return {"diagnostics": diagnostics}
    except Exception as e:  # any unexpected error becomes an HTTP 500
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/actions/validate-triggers")
async def validate_triggers_structured(body: ActionsUpdateRequest):
    """Validate structured triggers without saving (``POST /actions/validate-triggers``)."""
    try:
        diagnostics = _get_service().validate_triggers(
            [t.model_dump() for t in body.triggers]
        )
        return {"diagnostics": diagnostics}
    except Exception as e:  # any unexpected error becomes an HTTP 500
        raise HTTPException(status_code=500, detail=str(e))


def _load_gifts() -> list[dict]:
    """Load the gift catalog, returning an empty list when missing or unreadable."""
    from core.paths import get_gifts_file

    gifts_file = get_gifts_file()
    if not gifts_file.exists():
        return []
    try:
        return json.loads(gifts_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
        log.error("Failed to load gifts.json: %s", e)
        return []


@router.get("/gifts")
async def get_gifts():
    """Return the gift catalog enriched with image URLs (``GET /gifts``).

Entries are sorted by coin value and then name for stable display order."""

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


@router.post("/gifts/sync")
def sync_gifts_catalog(body: GiftSyncRequest | None = None):
    """Fetch and persist an updated gift catalog (``POST /gifts/sync``)."""
    import core.gift_sync as gift_sync

    if body is None:
        body = GiftSyncRequest()
    try:
        return gift_sync.sync_gifts(source=body.source)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/actions/scripts")
async def get_registered_scripts():
    """List script actions registered by hooks (``GET /actions/scripts``).

Lazily loads event hooks when the in-process registry is still empty, so the
actions editor can offer script completions before a live connection starts."""

    try:
        from core.hook_api import HOOK_ACTIONS
        from core.hook_loader import load_event_hooks

        if not HOOK_ACTIONS:
            try:
                from core.paths import get_base_dir, get_root_dir

                candidates = []
                base_dir = get_base_dir()
                root_dir = get_root_dir()
                try:
                    from core.paths import get_active_app_dir

                    active = get_active_app_dir()
                    if active is not None:
                        candidates.append(active / "hooks")
                except Exception:
                    pass
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
                            """Record a script action exposed by a hook.

                            Args:
                                name: Action name used in ``actions.mca`` scripts.
                                fn: Callable implementing the action.
                            """
                            HOOK_ACTIONS[name] = fn

                        def for_hook(self, name: str, **_kw) -> "_StubAPI":
                            """Return this stub for the requested hook name.

                            Hooks call ``for_hook`` while registering and expect the
                            same API object back; all other attributes resolve to
                            no-op callables.
                            """
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
