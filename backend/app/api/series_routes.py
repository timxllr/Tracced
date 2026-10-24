"""API-Routen für Messreihen (CRUD mit Optimistic Concurrency und Eigentümerprüfung)."""
import uuid
from typing import List
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from sqlalchemy.orm import selectinload
from app.database import get_db
from app.models import User, MeasurementSeries, Reading
from app.schemas import SeriesSummary, SeriesDetail, SeriesCreate, SeriesUpdate, ReadingRead
from app.api.deps import get_current_user

router = APIRouter(prefix="/series", tags=["Messreihen"])


@router.get("", response_model=List[SeriesSummary])
async def list_series(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Liefert alle Messreihen des angemeldeten Benutzers inkl. letztem Messwert."""
    query = (
        select(MeasurementSeries)
        .where(MeasurementSeries.user_id == current_user.id)
        .order_by(MeasurementSeries.name.asc())
    )
    result = await db.execute(query)
    series_list = result.scalars().all()
    
    summaries = []
    for s in series_list:
        # Zähle Messwerte und hole den neuesten
        count_res = await db.execute(
            select(func.count(Reading.id)).where(Reading.series_id == s.id)
        )
        count = count_res.scalar() or 0
        
        latest_res = await db.execute(
            select(Reading)
            .where(Reading.series_id == s.id)
            .order_by(desc(Reading.timestamp))
            .limit(1)
        )
        latest_reading = latest_res.scalar_one_or_none()
        
        summaries.append(SeriesSummary(
            id=s.id,
            name=s.name,
            unit=s.unit,
            description=s.description,
            series_type=s.series_type,
            allow_decimals=s.allow_decimals,
            created_at=s.created_at,
            updated_at=s.updated_at,
            readings_count=count,
            latest_reading=ReadingRead.model_validate(latest_reading) if latest_reading else None
        ))
        
    return summaries


@router.post("", response_model=SeriesSummary, status_code=status.HTTP_201_CREATED)
async def create_series(
    payload: SeriesCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Erstellt eine neue Messreihe für den aktuellen Benutzer."""
    # Namensduplikat für diesen Benutzer prüfen
    existing = await db.execute(
        select(MeasurementSeries).where(
            MeasurementSeries.user_id == current_user.id,
            func.lower(MeasurementSeries.name) == payload.name.strip().lower()
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Eine Messreihe mit dem Namen '{payload.name}' existiert bereits."
        )
        
    new_series = MeasurementSeries(
        user_id=current_user.id,
        name=payload.name.strip(),
        unit=payload.unit.strip(),
        description=payload.description,
        series_type=payload.series_type.value if hasattr(payload.series_type, "value") else str(payload.series_type),
        allow_decimals=payload.allow_decimals
    )
    db.add(new_series)
    await db.commit()
    await db.refresh(new_series)
    
    return SeriesSummary(
        id=new_series.id,
        name=new_series.name,
        unit=new_series.unit,
        description=new_series.description,
        series_type=new_series.series_type,
        allow_decimals=new_series.allow_decimals,
        created_at=new_series.created_at,
        updated_at=new_series.updated_at,
        readings_count=0,
        latest_reading=None
    )


@router.get("/{series_id}", response_model=SeriesDetail)
async def get_series_detail(
    series_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Liefert die Details einer Messreihe inklusive aller zugehörigen Messwerte."""
    result = await db.execute(
        select(MeasurementSeries)
        .options(selectinload(MeasurementSeries.readings))
        .where(MeasurementSeries.id == series_id, MeasurementSeries.user_id == current_user.id)
    )
    series = result.scalar_one_or_none()
    if not series:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Messreihe nicht gefunden.")
        
    readings = sorted(series.readings, key=lambda r: r.timestamp)
    latest = readings[-1] if readings else None
    
    return SeriesDetail(
        id=series.id,
        name=series.name,
        unit=series.unit,
        description=series.description,
        series_type=series.series_type,
        allow_decimals=series.allow_decimals,
        created_at=series.created_at,
        updated_at=series.updated_at,
        readings_count=len(readings),
        latest_reading=ReadingRead.model_validate(latest) if latest else None,
        readings=[ReadingRead.model_validate(r) for r in readings]
    )


@router.put("/{series_id}", response_model=SeriesSummary)
async def update_series(
    series_id: uuid.UUID,
    payload: SeriesUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Aktualisiert eine Messreihe mit Optimistic Concurrency Control (Konflikterkennung)."""
    result = await db.execute(
        select(MeasurementSeries).where(
            MeasurementSeries.id == series_id,
            MeasurementSeries.user_id == current_user.id
        )
    )
    series = result.scalar_one_or_none()
    if not series:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Messreihe nicht gefunden.")
        
    # Optimistic Concurrency Check: updated_at vergleichen
    # Im ISO-Format oder bis auf die Sekunde runden (Toleranz für Microseconds in SQLite)
    expected_iso = payload.expected_updated_at.isoformat()
    actual_iso = series.updated_at.isoformat()
    
    # Prüfe ob Zeitstempel abweichen
    expected_dt = payload.expected_updated_at.replace(microsecond=0)
    actual_dt = series.updated_at.replace(microsecond=0)
    
    if expected_dt != actual_dt and expected_iso != actual_iso:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Konflikt: Die Messreihe wurde zwischenzeitlich auf einem anderen Gerät geändert. Bitte Seite aktualisieren."
        )
        
    if payload.name is not None and payload.name.strip().lower() != series.name.lower():
        # Namensdopplung prüfen
        dup = await db.execute(
            select(MeasurementSeries).where(
                MeasurementSeries.user_id == current_user.id,
                MeasurementSeries.id != series_id,
                func.lower(MeasurementSeries.name) == payload.name.strip().lower()
            )
        )
        if dup.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Eine Messreihe mit dem Namen '{payload.name}' existiert bereits."
            )
        series.name = payload.name.strip()
        
    if payload.unit is not None:
        series.unit = payload.unit.strip()
    if payload.description is not None:
        series.description = payload.description
    if payload.series_type is not None:
        series.series_type = payload.series_type.value if hasattr(payload.series_type, "value") else str(payload.series_type)
    if payload.allow_decimals is not None:
        series.allow_decimals = payload.allow_decimals
        
    series.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(series)
    
    count_res = await db.execute(select(func.count(Reading.id)).where(Reading.series_id == series.id))
    count = count_res.scalar() or 0
    
    latest_res = await db.execute(
        select(Reading).where(Reading.series_id == series.id).order_by(desc(Reading.timestamp)).limit(1)
    )
    latest_reading = latest_res.scalar_one_or_none()
    
    return SeriesSummary(
        id=series.id,
        name=series.name,
        unit=series.unit,
        description=series.description,
        series_type=series.series_type,
        allow_decimals=series.allow_decimals,
        created_at=series.created_at,
        updated_at=series.updated_at,
        readings_count=count,
        latest_reading=ReadingRead.model_validate(latest_reading) if latest_reading else None
    )


@router.delete("/{series_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_series(
    series_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Löscht eine Messreihe kaskadierend samt aller zugehörigen Messwerte."""
    result = await db.execute(
        select(MeasurementSeries).where(
            MeasurementSeries.id == series_id,
            MeasurementSeries.user_id == current_user.id
        )
    )
    series = result.scalar_one_or_none()
    if not series:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Messreihe nicht gefunden.")
        
    await db.delete(series)
    await db.commit()
    return None
