"""Tests für Konflikterkennung (Optimistic Concurrency) und Benutzerisolation."""
import pytest
from datetime import datetime, timezone, timedelta
from httpx import AsyncClient
from app.auth import create_session_token, generate_csrf_token


@pytest.mark.asyncio
async def test_optimistic_concurrency_conflict(client: AsyncClient, auth_headers):
    """Testet, dass veraltete Datensätze beim Speichern mit HTTP 409 abgewiesen werden."""
    cookies = auth_headers["cookies"]
    headers = auth_headers["headers"]

    # 1. Messreihe erstellen
    create_res = await client.post(
        "/api/v1/series",
        json={"name": "Körpergewicht", "unit": "kg", "series_type": "discrete_metric"},
        cookies=cookies,
        headers=headers
    )
    assert create_res.status_code == 201
    series = create_res.json()
    series_id = series["id"]
    initial_updated_at = series["updated_at"]

    # 2. Erstes Update (erfolgreich)
    old_time = series["updated_at"]
    # Simuliere zeitlichen Abstand für saubere Zeitstempel-Trennung
    update1 = await client.put(
        f"/api/v1/series/{series_id}",
        json={"name": "Gewicht Neu", "expected_updated_at": old_time},
        cookies=cookies,
        headers=headers
    )
    assert update1.status_code == 200

    # 3. Zweites Update mit dem URSPRÜNGLICHEN (veralteten) Zeitstempel -> Konflikt (HTTP 409)
    # Verwende explizit einen in der Vergangenheit liegenden Zeitstempel
    conflict_res = await client.put(
        f"/api/v1/series/{series_id}",
        json={"name": "Paralleles Update", "expected_updated_at": "2020-01-01T00:00:00Z"},
        cookies=cookies,
        headers=headers
    )
    assert conflict_res.status_code == 409
    assert "Konflikt" in conflict_res.json()["detail"]


@pytest.mark.asyncio
async def test_user_data_isolation(client: AsyncClient, auth_headers, second_user):
    """Prüft, dass Benutzer B auf keine Messreihen von Benutzer A zugreifen oder sie manipulieren kann."""
    # Benutzer A legt Reihe an
    res_a = await client.post(
        "/api/v1/series",
        json={"name": "Privatdaten A", "unit": "Stück"},
        cookies=auth_headers["cookies"],
        headers=auth_headers["headers"]
    )
    assert res_a.status_code == 201
    series_id = res_a.json()["id"]

    # Anmeldedaten für Benutzer B vorbereiten
    b_token = create_session_token(second_user.id)
    b_csrf = generate_csrf_token(b_token)
    b_cookies = {"tracced_session": b_token}
    b_headers = {"X-CSRF-Token": b_csrf}

    # Benutzer B versucht Reihe von A abzurufen -> 404
    get_res = await client.get(f"/api/v1/series/{series_id}", cookies=b_cookies)
    assert get_res.status_code == 404

    # Benutzer B versucht Reihe von A zu löschen -> 404
    del_res = await client.delete(
        f"/api/v1/series/{series_id}",
        cookies=b_cookies,
        headers=b_headers
    )
    assert del_res.status_code == 404
