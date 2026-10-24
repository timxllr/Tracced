"""API-Routen für Backup (Export JSON/CSV, Validierung und atomarer Import)."""
from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models import User
from app.schemas import (
    BackupPayload,
    ImportValidationReport,
    ImportExecutionRequest,
)
from app.services.backup_service import (
    export_json_backup,
    export_csv_backup,
    validate_import_payload,
    execute_atomic_import,
)
from app.api.deps import get_current_user

router = APIRouter(prefix="/backup", tags=["Backup & Restore"])


@router.get("/export/json", response_model=BackupPayload)
async def export_json(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Exportiert alle Messreihen und Messwerte als versioniertes JSON-Backup."""
    return await export_json_backup(current_user.id, db)


@router.get("/export/csv")
async def export_csv(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Exportiert alle Messreihen und Messwerte als CSV (UTF-8 mit BOM)."""
    csv_data = await export_csv_backup(current_user.id, db)
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=tracced_backup.csv"
        }
    )


@router.post("/validate", response_model=ImportValidationReport)
async def validate_import(
    payload: BackupPayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Prüft eine Backup-Datei vorab und liefert einen detaillierten Prüfbericht."""
    return await validate_import_payload(current_user.id, payload, db)


@router.post("/execute")
async def execute_import(
    request: ImportExecutionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Führt den Import atomar in einer einzigen Transaktion aus."""
    try:
        result = await execute_atomic_import(current_user.id, request, db)
        return result
    except ValueError as val_err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(val_err))
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fehler beim Import: {str(err)}"
        )
