import logging
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Response, UploadFile

from core.api.models import BundleImportResponse
from core.api.services.config_bundle import ConfigBundleService

log = logging.getLogger(__name__)

router = APIRouter(tags=["Config Bundle"])

_service: ConfigBundleService | None = None


def _get_service() -> ConfigBundleService:
    global _service
    if _service is None:
        _service = ConfigBundleService()
    return _service


@router.get("/config-bundle")
async def export_config_bundle():
    """Download a ZIP bundle of the current configuration."""
    try:
        content = _get_service().create_bundle()
        return Response(
            content=content,
            media_type="application/zip",
            headers={
                "Content-Disposition": (
                    'attachment; filename="tiktok2mc-config-bundle.zip"'
                )
            },
        )
    except Exception as e:  # any unexpected error becomes an HTTP 500
        log.exception("Failed to export config bundle")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/config-bundle/import", response_model=BundleImportResponse)
async def import_config_bundle(file: Annotated[UploadFile, File()]):
    """Validate and apply an uploaded config bundle ZIP."""
    try:
        content = file.file.read()
    finally:
        file.file.close()
    try:
        result = _get_service().import_bundle(content)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:  # any unexpected error becomes an HTTP 500
        log.exception("Failed to import config bundle")
        raise HTTPException(status_code=500, detail=str(e))
    return BundleImportResponse(**result)
