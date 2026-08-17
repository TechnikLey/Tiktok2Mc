import logging

from fastapi import APIRouter, HTTPException

from core.api.models import (
    BackupCreateRequest,
    BackupCreateResponse,
    BackupListResponse,
    BackupRestoreRequest,
    BackupRestoreResponse,
)
from core.api.services.backups import BackupService

log = logging.getLogger(__name__)

router = APIRouter(tags=["Backups"])

_service: BackupService | None = None


def _get_service() -> BackupService:
    global _service
    if _service is None:
        _service = BackupService()
    return _service


@router.get("/backups", response_model=BackupListResponse)
async def list_backups():
    """List all backup categories with their files, newest first."""
    try:
        return BackupListResponse(**_get_service().list_backups())
    except Exception as e:  # any unexpected error becomes an HTTP 500
        log.exception("Failed to list backups")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/backups/restore", response_model=BackupRestoreResponse)
async def restore_backup(body: BackupRestoreRequest):
    """Restore a backup file back to its target (with a pre-restore snapshot)."""
    try:
        return BackupRestoreResponse(
            **_get_service().restore(body.category, body.filename, target=body.target)
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:  # any unexpected error becomes an HTTP 500
        log.exception("Failed to restore backup")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/backups/create", response_model=BackupCreateResponse)
async def create_backups(body: BackupCreateRequest):
    """Create backups of the requested targets immediately."""
    try:
        return BackupCreateResponse(**_get_service().create_now(body.targets))
    except Exception as e:  # any unexpected error becomes an HTTP 500
        log.exception("Failed to create backups")
        raise HTTPException(status_code=500, detail=str(e))
