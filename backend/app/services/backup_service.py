"""Backup- und Restore-Service für Tracced.

Eigenschaften:
- Vollständiger, stabiler JSON-Export mit UUIDs
- Vorab-Validierung vor dem Speichern
- Atomare Ausführung in einer einzigen Transaktion (Rollback bei jedem Fehler)
- Modi: Merge (Upsert / Duplikate überspringen) und Atomic Replace
- Tabellarischer CSV-Export (UTF-8 mit BOM)
"""
import csv
import io
import uuid
from datetime import datetime, timezone
from typing import Tuple, List, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload
from app.models import MeasurementSeries, Reading, SeriesType
from app.schemas import (
    BackupPayload,
    BackupSeriesItem,
    BackupReadingItem,
    ImportValidationReport,
    ImportExecutionRequest,
)


async def export_json_backup(user_id: uuid.UUID, db: AsyncSession) -> BackupPayload:
    """Erstellt ein vollständiges, stabiles JSON-Backup für den angegebenen Benutzer."""
    result = await db.execute(
        select(MeasurementSeries)
        .options(selectinload(MeasurementSeries.readings))
        .where(MeasurementSeries.user_id == user_id)
        .order_by(MeasurementSeries.name.asc())
    )
    series_list = result.scalars().all()
    
    total_readings = 0
    exported_series: List[BackupSeriesItem] = []
    
    for s in series_list:
        sorted_readings = sorted(s.readings, key=lambda r: r.timestamp)
        total_readings += len(sorted_readings)
        
        exported_series.append(BackupSeriesItem(
            id=s.id,
            name=s.name,
            unit=s.unit,
            description=s.description,
            series_type=SeriesType(s.series_type) if s.series_type in [t.value for t in SeriesType] else SeriesType.DISCRETE_METRIC,
            allow_decimals=s.allow_decimals,
            readings=[
                BackupReadingItem(
                    id=r.id,
                    timestamp=r.timestamp,
                    value=r.value,
                    note=r.note
                )
                for r in sorted_readings
            ]
        ))
        
    return BackupPayload(
        version="1.0",
        app="Tracced",
        exported_at=datetime.now(timezone.utc),
        series_count=len(exported_series),
        readings_count=total_readings,
        data=exported_series
    )


async def export_csv_backup(user_id: uuid.UUID, db: AsyncSession) -> str:
    """Erzeugt einen CSV-Export aller Messdaten (UTF-8 mit BOM für Excel)."""
    result = await db.execute(
        select(MeasurementSeries)
        .options(selectinload(MeasurementSeries.readings))
        .where(MeasurementSeries.user_id == user_id)
        .order_by(MeasurementSeries.name.asc())
    )
    series_list = result.scalars().all()
    
    output = io.StringIO()
    # UTF-8 BOM für fehlerfreies Öffnen in Excel
    output.write("\ufeff")
    
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["series_name", "unit", "series_type", "timestamp_iso", "value", "note", "series_id", "reading_id"])
    
    for s in series_list:
        sorted_readings = sorted(s.readings, key=lambda r: r.timestamp)
        for r in sorted_readings:
            writer.writerow([
                s.name,
                s.unit,
                s.series_type,
                r.timestamp.isoformat(),
                str(r.value),
                r.note or "",
                str(s.id),
                str(r.id)
            ])
            
    return output.getvalue()


def normalize_timestamp_epoch(val) -> int:
    """Normalisiert ein datetime-Objekt oder einen Datums-String robust auf Unix-Sekunden."""
    if val is None:
        return 0
    if isinstance(val, (int, float)):
        return int(val)
    if isinstance(val, str):
        # ISO-String oder SQLite-String parsen
        val = val.replace("Z", "+00:00")
        try:
            val = datetime.fromisoformat(val)
        except Exception:
            return 0
            
    if hasattr(val, "tzinfo"):
        if val.tzinfo is None:
            val = val.replace(tzinfo=timezone.utc)
        return int(val.timestamp())
    return 0


async def validate_import_payload(
    user_id: uuid.UUID,
    payload: BackupPayload,
    db: AsyncSession
) -> ImportValidationReport:
    """Validiert die Importdatei vorab gegen den aktuellen Datenbestand."""
    errors = []
    warnings = []
    
    if payload.version not in ("1.0", "1"):
        warnings.append(f"Unbekannte Backup-Version '{payload.version}', es wird versucht zu importieren.")
        
    # Bestehende Reihen laden
    res = await db.execute(
        select(MeasurementSeries)
        .options(selectinload(MeasurementSeries.readings))
        .where(MeasurementSeries.user_id == user_id)
    )
    existing_series = {s.name.lower(): s for s in res.scalars().all()}
    
    series_to_create = 0
    series_to_merge = 0
    readings_to_create = 0
    readings_duplicate_skipped = 0
    readings_conflicts = 0
    
    seen_names = set()
    for s_item in payload.data:
        norm_name = s_item.name.strip().lower()
        if not norm_name:
            errors.append("Eine Messreihe im Backup besitzt keinen gültigen Namen.")
            continue
            
        if norm_name in seen_names:
            errors.append(f"Die Messreihe '{s_item.name}' ist mehrfach im Backup-Datensatz enthalten.")
        seen_names.add(norm_name)
        
        target_series = existing_series.get(norm_name)
        if target_series:
            series_to_merge += 1
            # Bestehende Timestamps als epoch-Sekunden und IDs sammeln
            existing_ts = {normalize_timestamp_epoch(r.timestamp): r for r in target_series.readings}
            existing_ids = {str(r.id): r for r in target_series.readings}
            for r_item in s_item.readings:
                r_epoch = normalize_timestamp_epoch(r_item.timestamp)
                is_dup = False
                ex_r = None

                if r_item.id and str(r_item.id) in existing_ids:
                    is_dup = True
                    ex_r = existing_ids[str(r_item.id)]
                elif r_epoch in existing_ts:
                    is_dup = True
                    ex_r = existing_ts[r_epoch]

                if is_dup:
                    if ex_r and float(ex_r.value) == float(r_item.value):
                        readings_duplicate_skipped += 1
                    else:
                        readings_conflicts += 1
                        warnings.append(f"Reihe '{s_item.name}' am {r_item.timestamp.strftime('%d.%m.%Y %H:%M')}: Abweichender Wert ({r_item.value} vs. {ex_r.value if ex_r else '?'}).")
                else:
                    readings_to_create += 1
        else:
            series_to_create += 1
            readings_to_create += len(s_item.readings)
            
    return ImportValidationReport(
        valid=len(errors) == 0,
        series_to_create=series_to_create,
        series_to_merge=series_to_merge,
        readings_to_create=readings_to_create,
        readings_duplicate_skipped=readings_duplicate_skipped,
        readings_conflicts=readings_conflicts,
        errors=errors,
        warnings=warnings
    )


async def execute_atomic_import(
    user_id: uuid.UUID,
    request: ImportExecutionRequest,
    db: AsyncSession
) -> Dict[str, str]:
    """Führt den Import atomar in einer einzigen Transaktion aus."""
    payload = request.data
    mode = request.mode
    
    # 1. Vorab-Validierung
    report = await validate_import_payload(user_id, payload, db)
    if not report.valid:
        raise ValueError("Validierung fehlgeschlagen: " + "; ".join(report.errors))
        
    try:
        if mode == "replace":
            # Lösche alle bestehenden Reihen des Benutzers (Kaskade löscht Messwerte)
            await db.execute(delete(MeasurementSeries).where(MeasurementSeries.user_id == user_id))
            await db.flush()
            existing_series_map = {}
        else:
            # Merge-Modus: Bestehende Reihen laden
            res = await db.execute(
                select(MeasurementSeries)
                .options(selectinload(MeasurementSeries.readings))
                .where(MeasurementSeries.user_id == user_id)
            )
            existing_series_map = {s.name.lower(): s for s in res.scalars().all()}
            
        # Vorhandene Reading-IDs und Series-IDs erfassen, um Primary-Key-Kollisionen zu vermeiden
        all_readings_res = await db.execute(select(Reading.id))
        existing_reading_ids = set(all_readings_res.scalars().all())

        all_series_res = await db.execute(select(MeasurementSeries.id))
        existing_series_ids = set(all_series_res.scalars().all())

        for s_item in payload.data:
            norm_name = s_item.name.strip().lower()
            series = existing_series_map.get(norm_name)
            
            if not series:
                # Neue Reihe anlegen: Stabile ID nutzen wenn frei, sonst neue vergeben
                new_id = s_item.id if (s_item.id and s_item.id not in existing_series_ids) else uuid.uuid4()
                existing_series_ids.add(new_id)
                series = MeasurementSeries(
                    id=new_id,
                    user_id=user_id,
                    name=s_item.name.strip(),
                    unit=s_item.unit.strip(),
                    description=s_item.description,
                    series_type=s_item.series_type.value if hasattr(s_item.series_type, "value") else str(s_item.series_type),
                    allow_decimals=s_item.allow_decimals
                )
                db.add(series)
                await db.flush()
                existing_series_map[norm_name] = series
                existing_ts = set()
            # Bestehende Messwerte dieser Reihe direkt aus der Datenbank abfragen
            existing_ts = set()
            existing_ids_in_series = set()
            if series:
                r_query = await db.execute(select(Reading).where(Reading.series_id == series.id))
                for existing_r in r_query.scalars().all():
                    existing_ts.add(normalize_timestamp_epoch(existing_r.timestamp))
                    existing_ids_in_series.add(str(existing_r.id))

            for r_item in s_item.readings:
                # 1. Duplikatprüfung über ID (falls selbe UUID exportiert wurde)
                if r_item.id and str(r_item.id) in existing_ids_in_series:
                    continue

                # 2. Duplikatprüfung über normalisierten Zeitstempel (Sekundengenauigkeit)
                r_epoch = normalize_timestamp_epoch(r_item.timestamp)
                if r_epoch in existing_ts:
                    # Exakter Zeitstempel existiert bereits in dieser Reihe -> Duplikat überspringen
                    continue
                    
                # Primärschlüssel vergeben: Nur nutzen, wenn er noch nicht global vergeben ist
                reading_id = r_item.id if (r_item.id and r_item.id not in existing_reading_ids) else uuid.uuid4()
                existing_reading_ids.add(reading_id)
                existing_ids_in_series.add(str(reading_id))
                existing_ts.add(r_epoch)

                new_reading = Reading(
                    id=reading_id,
                    series_id=series.id,
                    timestamp=r_item.timestamp,
                    value=r_item.value,
                    note=r_item.note
                )
                db.add(new_reading)
                
        # Alles in einer einzigen atomaren Transaktion committen
        await db.commit()
        return {
            "status": "success",
            "message": f"Import ({mode}) erfolgreich abgeschlossen.",
            "series_processed": str(len(payload.data))
        }
    except Exception as e:
        await db.rollback()
        raise e
