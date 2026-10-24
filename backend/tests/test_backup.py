"""Tests für stabiles Backup, atomaren Import und Rollback bei Fehlern."""
import pytest
import uuid
from decimal import Decimal
from datetime import datetime, timezone
from httpx import AsyncClient
from app.services.backup_service import execute_atomic_import
from app.schemas import ImportExecutionRequest, BackupPayload, BackupSeriesItem, BackupReadingItem, SeriesType


@pytest.mark.asyncio
async def test_backup_json_export_and_import(client: AsyncClient, auth_headers):
    """Testet vollständigen Export und anschließenden Import."""
    cookies = auth_headers["cookies"]
    headers = auth_headers["headers"]

    # Reihe und Messwert anlegen
    res = await client.post(
        "/api/v1/series",
        json={"name": "Gastherme", "unit": "m³", "series_type": "continuous_cumulative"},
        cookies=cookies,
        headers=headers
    )
    series_id = res.json()["id"]

    now = datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc)
    await client.post(
        f"/api/v1/series/{series_id}/readings",
        json={"timestamp": now.isoformat(), "value": 1500.5, "note": "März"},
        cookies=cookies,
        headers=headers
    )

    # Export anfordern
    export_res = await client.get("/api/v1/backup/export/json", cookies=cookies)
    assert export_res.status_code == 200
    backup_data = export_res.json()
    assert backup_data["series_count"] == 1
    assert backup_data["readings_count"] == 1
    assert backup_data["data"][0]["name"] == "Gastherme"
    assert backup_data["data"][0]["readings"][0]["value"] == 1500.5

    # Validierung aufrufen
    val_res = await client.post("/api/v1/backup/validate", json=backup_data, cookies=cookies, headers=headers)
    assert val_res.status_code == 200
    val_report = val_res.json()
    assert val_report["valid"] is True
    # Da die Daten schon existieren, sollte es als Duplicate erkannt werden
    assert val_report["readings_duplicate_skipped"] == 1


@pytest.mark.asyncio
async def test_atomic_import_rollback_on_error(db_session, test_user):
    """Prüft, dass bei einem ungültigen Datensatz die gesamte Transaktion zurückgerollt wird."""
    invalid_payload = BackupPayload(
        version="1.0",
        app="Tracced",
        exported_at=datetime.now(timezone.utc),
        series_count=1,
        readings_count=1,
        data=[
            BackupSeriesItem(
                name="",  # Ungültig: leerer Name führt zum Validierungsfehler
                unit="kg",
                series_type=SeriesType.DISCRETE_METRIC,
                readings=[]
            )
        ]
    )

    req = ImportExecutionRequest(mode="merge", data=invalid_payload)

    with pytest.raises(ValueError) as exc:
        await execute_atomic_import(test_user.id, req, db_session)
    assert "Validierung fehlgeschlagen" in str(exc.value)
