"""API-Routen für Messwerte (CRUD mit Optimistic Concurrency und Eigentümerprüfung)."""
import csv
import io
import uuid
from typing import List, Optional
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from app.database import get_db
from app.models import User, MeasurementSeries, Reading
from app.schemas import (
    ReadingRead,
    ReadingCreate,
    ReadingUpdate,
    CsvImportRequest,
    CsvImportValidationReport,
    CsvImportPreviewRow,
    CsvImportExecutionResult,
)
from app.api.deps import get_current_user


def _parse_timestamp_flexible(val: str) -> Optional[datetime]:
    """Parst einen Zeitstempel-String flexibel (ISO, mit Leerzeichen, Datum nur)."""
    val = val.strip()
    if not val:
        return None
    formats = [
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%d.%m.%Y %H:%M:%S",
        "%d.%m.%Y %H:%M",
        "%d.%m.%Y",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(val, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


router = APIRouter(tags=["Messwerte"])

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


# ---------------------------------------------------------------------------
# CSV-Import pro Messreihe
# ---------------------------------------------------------------------------

@router.post(
    "/series/{series_id}/readings/import/validate",
    response_model=CsvImportValidationReport,
)
async def validate_csv_import(
    series_id: uuid.UUID,
    request: CsvImportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Prüft eine CSV vor dem Import und liefert eine Vorschau der gültigen / ungültigen Zeilen."""
    # Eigentümerprüfung
    series_res = await db.execute(
        select(MeasurementSeries).where(
            MeasurementSeries.id == series_id,
            MeasurementSeries.user_id == current_user.id
        )
    )
    if not series_res.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Messreihe nicht gefunden.")

    # Bestehende Timestamps der Reihe laden (für Duplikat-Erkennung im Merge-Modus)
    existing_ts: set = set()
    if request.mode == "merge":
        res = await db.execute(
            select(Reading.timestamp).where(Reading.series_id == series_id)
        )
        for r in res.scalars().all():
            existing_ts.add(int(r.timestamp()))

    delimiter = request.delimiter
    if delimiter == "\\t":
        delimiter = "\t"

    reader = csv.reader(io.StringIO(request.csv_data), delimiter=delimiter)
    rows = list(reader)

    if not rows:
        return CsvImportValidationReport(
            total_rows=0,
            valid_rows=0,
            invalid_rows=0,
            preview=[],
            errors=["Die CSV-Datei ist leer."],
        )

    start_idx = 1 if request.has_header else 0
    cm = request.column_mapping

    preview: List[CsvImportPreviewRow] = []
    valid_count = 0
    invalid_count = 0
    errors: List[str] = []

    for i in range(start_idx, len(rows)):
        row = rows[i]
        row_number = i + 1  # 1-basiert für Anzeige

        # Spalten-Indizes prüfen
        max_col = max(cm.timestamp_col, cm.value_col)
        if cm.note_col is not None:
            max_col = max(max_col, cm.note_col)

        if len(row) <= max_col:
            preview.append(CsvImportPreviewRow(
                row_number=row_number,
                timestamp="",
                value="",
                note=None,
                valid=False,
                error=f"Nicht genug Spalten (erwartet mindestens {max_col + 1}, vorhanden {len(row)}).",
            ))
            invalid_count += 1
            continue

        raw_ts = row[cm.timestamp_col].strip()
        raw_val = row[cm.value_col].strip()
        raw_note = row[cm.note_col].strip() if cm.note_col is not None and cm.note_col < len(row) else ""

        ts = _parse_timestamp_flexible(raw_ts)
        if ts is None:
            preview.append(CsvImportPreviewRow(
                row_number=row_number,
                timestamp=raw_ts,
                value=raw_val,
                note=raw_note or None,
                valid=False,
                error=f"Ungültiger Zeitstempel: '{raw_ts}'",
            ))
            invalid_count += 1
            continue

        try:
            val = Decimal(raw_val)
        except (InvalidOperation, ValueError):
            preview.append(CsvImportPreviewRow(
                row_number=row_number,
                timestamp=raw_ts,
                value=raw_val,
                note=raw_note or None,
                valid=False,
                error=f"Ungültiger Messwert: '{raw_val}'",
            ))
            invalid_count += 1
            continue

        # Duplikat-Check (gleicher Zeitstempel bereits vorhanden)
        ts_epoch = int(ts.timestamp())
        is_duplicate = ts_epoch in existing_ts

        preview.append(CsvImportPreviewRow(
            row_number=row_number,
            timestamp=ts.isoformat(),
            value=str(val),
            note=raw_note or None,
            valid=not is_duplicate,
            error="Zeitstempel bereits vorhanden (wird übersprungen)." if is_duplicate else None,
        ))

        if is_duplicate:
            invalid_count += 1
        else:
            valid_count += 1
            existing_ts.add(ts_epoch)

    return CsvImportValidationReport(
        total_rows=len(rows) - start_idx,
        valid_rows=valid_count,
        invalid_rows=invalid_count,
        preview=preview,
        errors=errors,
    )


@router.post(
    "/series/{series_id}/readings/import/execute",
    response_model=CsvImportExecutionResult,
)
async def execute_csv_import(
    series_id: uuid.UUID,
    request: CsvImportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Führt den CSV-Import für die angegebene Messreihe aus."""
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

    # Replace-Modus: Alle bestehenden Werte der Reihe löschen
    imported = 0
    skipped = 0

    if request.mode == "replace":
        await db.execute(delete(Reading).where(Reading.series_id == series_id))
        await db.flush()

    # Bestehende Timestamps laden (für Merge-Duplikat-Erkennung)
    existing_ts: set = set()
    if request.mode == "merge":
        res = await db.execute(
            select(Reading.timestamp).where(Reading.series_id == series_id)
        )
        for r in res.scalars().all():
            existing_ts.add(int(r.timestamp()))

    delimiter = request.delimiter
    if delimiter == "\\t":
        delimiter = "\t"

    reader = csv.reader(io.StringIO(request.csv_data), delimiter=delimiter)
    rows = list(reader)

    if not rows:
        return CsvImportExecutionResult(
            status="error",
            message="Die CSV-Datei ist leer.",
            readings_imported=0,
            readings_skipped=0,
        )

    start_idx = 1 if request.has_header else 0
    cm = request.column_mapping

    series.updated_at = datetime.now(timezone.utc)

    for i in range(start_idx, len(rows)):
        row = rows[i]
        max_col = max(cm.timestamp_col, cm.value_col)
        if cm.note_col is not None:
            max_col = max(max_col, cm.note_col)

        if len(row) <= max_col:
            skipped += 1
            continue

        raw_ts = row[cm.timestamp_col].strip()
        raw_val = row[cm.value_col].strip()
        raw_note = row[cm.note_col].strip() if cm.note_col is not None and cm.note_col < len(row) else ""

        ts = _parse_timestamp_flexible(raw_ts)
        if ts is None:
            skipped += 1
            continue

        try:
            val = Decimal(raw_val)
        except (InvalidOperation, ValueError):
            skipped += 1
            continue

        ts_epoch = int(ts.timestamp())
        if ts_epoch in existing_ts:
            skipped += 1
            continue

        existing_ts.add(ts_epoch)

        new_reading = Reading(
            series_id=series_id,
            timestamp=ts,
            value=val,
            note=raw_note or None,
        )
        db.add(new_reading)
        imported += 1

    await db.commit()

    return CsvImportExecutionResult(
        status="success",
        message=f"Import ({request.mode}) erfolgreich: {imported} Werte hinzugefügt, {skipped} übersprungen.",
        readings_imported=imported,
        readings_skipped=skipped,
    )
