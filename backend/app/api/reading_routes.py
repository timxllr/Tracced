"""API-Routen für Messwerte (CRUD mit Optimistic Concurrency und Eigentümerprüfung)."""
import uuid
from typing import List
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models import User, MeasurementSeries, Reading
from app.schemas import ReadingRead, ReadingCreate, ReadingUpdate
from app.api.deps import get_current_user

router = APIRouter(tags=["Messwerte"])


@router.get("/series/{series_id}/readings", response_model=List[ReadingRead])
async def list_readings_for_series(
    series_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Liefert alle Messwerte einer bestimmten Messreihe chronologisch sortiert."""
    # Sicherstellen, dass die Reihe dem aktuellen Benutzer gehört
    series_res = await db.execute(
        select(MeasurementSeries).where(
            MeasurementSeries.id == series_id,
            MeasurementSeries.user_id == current_user.id
        )
    )
    if not series_res.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Messreihe nicht gefunden.")
        
    readings_res = await db.execute(
        select(Reading)
        .where(Reading.series_id == series_id)
        .order_by(Reading.timestamp.asc())
    )
    return [ReadingRead.model_validate(r) for r in readings_res.scalars().all()]


@router.post("/series/{series_id}/readings", response_model=ReadingRead, status_code=status.HTTP_201_CREATED)
async def create_reading(
    series_id: uuid.UUID,
    payload: ReadingCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Erfasst einen neuen datierten Messwert für die angegebene Reihe."""
    # Eigentümerprüfung
    series_res = await db.execute(
        select(MeasurementSeries).where(
            MeasurementSeries.id == series_id,
            MeasurementSeries.user_id == current_user.id
        )
    )
    series = series_res.scalar_one_or_none()
    if not series:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Messreihe nicht gefunden.")
        
    # Timestamp sicher mit Zeitzone versehen falls naiv
    ts = payload.timestamp
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
        
    new_reading = Reading(
        series_id=series_id,
        timestamp=ts,
        value=payload.value,
        note=payload.note
    )
    # Auch die Reihe als aktualisiert markieren (für Cache-Invalidierung & Sync)
    series.updated_at = datetime.now(timezone.utc)
    
    db.add(new_reading)
    await db.commit()
    await db.refresh(new_reading)
    
    return ReadingRead.model_validate(new_reading)


@router.put("/readings/{reading_id}", response_model=ReadingRead)
async def update_reading(
    reading_id: uuid.UUID,
    payload: ReadingUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Aktualisiert einen Messwert mit Konflikterkennung (Optimistic Concurrency)."""
    # Join über MeasurementSeries zur Eigentümerprüfung
    query = (
        select(Reading)
        .join(MeasurementSeries, Reading.series_id == MeasurementSeries.id)
        .where(Reading.id == reading_id, MeasurementSeries.user_id == current_user.id)
    )
    result = await db.execute(query)
    reading = result.scalar_one_or_none()
    
    if not reading:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Messwert nicht gefunden.")
        
    # Optimistic Concurrency Check
    expected_ts = payload.expected_updated_at.replace(microsecond=0)
    actual_ts = reading.updated_at.replace(microsecond=0)
    if expected_ts != actual_ts:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Konflikt: Der Messwert wurde zwischenzeitlich geändert. Bitte aktualisieren."
        )
        
    if payload.timestamp is not None:
        ts = payload.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        reading.timestamp = ts
        
    if payload.value is not None:
        reading.value = payload.value
    if payload.note is not None:
        reading.note = payload.note
        
    reading.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(reading)
    
    return ReadingRead.model_validate(reading)


@router.delete("/readings/{reading_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_reading(
    reading_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Löscht einen Messwert mit Eigentümerprüfung."""
    query = (
        select(Reading)
        .join(MeasurementSeries, Reading.series_id == MeasurementSeries.id)
        .where(Reading.id == reading_id, MeasurementSeries.user_id == current_user.id)
    )
    result = await db.execute(query)
    reading = result.scalar_one_or_none()
    
    if not reading:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Messwert nicht gefunden.")
        
    await db.delete(reading)
    await db.commit()
    return None
