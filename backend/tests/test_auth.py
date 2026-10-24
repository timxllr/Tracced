"""Tests für Authentifizierung, Argon2id, Session-Handling und CSRF-Schutz."""
import pytest
from httpx import AsyncClient
from app.auth import verify_password, hash_password


@pytest.mark.asyncio
async def test_password_hashing():
    """Prüft, ob Passwörter sicher gehasht und korrekt verifiziert werden."""
    pwd = "MeinSehrSicheresPasswort2026!"
    hashed = hash_password(pwd)
    
    assert hashed != pwd
    assert hashed.startswith("$argon2id$")
    assert verify_password(pwd, hashed) is True
    assert verify_password("FalschesPasswort", hashed) is False


@pytest.mark.asyncio
async def test_login_flow(client: AsyncClient, test_user):
    """Testet erfolgreichen und fehlerhaften Login."""
    # Falsches Passwort
    res_wrong = await client.post("/api/v1/auth/login", json={
        "email": test_user.email,
        "password": "FalschesPasswort"
    })
    assert res_wrong.status_code == 401

    # Korrekter Login
    res_ok = await client.post("/api/v1/auth/login", json={
        "email": test_user.email,
        "password": "GeheimesPasswort123!"
    })
    assert res_ok.status_code == 200
    data = res_ok.json()
    assert data["authenticated"] is True
    assert data["user"]["email"] == test_user.email
    assert data["csrf_token"] is not None
    assert "tracced_session" in res_ok.cookies


@pytest.mark.asyncio
async def test_csrf_protection_on_modifications(client: AsyncClient, auth_headers):
    """Prüft, dass schreibende Anfragen ohne oder mit falschem CSRF-Token mit 403 abgewiesen werden."""
    cookies = auth_headers["cookies"]

    # Anfrage OHNE X-CSRF-Token Header
    res_no_csrf = await client.post(
        "/api/v1/series",
        json={"name": "Strom", "unit": "kWh", "series_type": "continuous_cumulative"},
        cookies=cookies
    )
    assert res_no_csrf.status_code == 403
    assert "CSRF-Token fehlt" in res_no_csrf.text

    # Anfrage mit ungültigem CSRF-Token
    res_invalid_csrf = await client.post(
        "/api/v1/series",
        json={"name": "Strom", "unit": "kWh", "series_type": "continuous_cumulative"},
        cookies=cookies,
        headers={"X-CSRF-Token": "manipuliertes_token_12345"}
    )
    assert res_invalid_csrf.status_code == 403

    # Anfrage mit gültigem CSRF-Token
    res_valid = await client.post(
        "/api/v1/series",
        json={"name": "Strom", "unit": "kWh", "series_type": "continuous_cumulative"},
        cookies=cookies,
        headers=auth_headers["headers"]
    )
    assert res_valid.status_code == 201
