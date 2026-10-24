"""Tests für Prognosehorizonte, 6-Monate-Regel, OLS-Regression und Zählerwechsel."""
import pytest
import uuid
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from app.models import Reading, SeriesType
from app.services.forecast_service import (
    calculate_target_date_and_days,
    linear_regression_ols,
    generate_forecasts_for_series,
)
from app.schemas import ForecastQuality


def test_six_months_ultimo_rule():
    """Testet die exakte 6-Kalendermonate-Regel und die Ultimo-Behandlung."""
    # Fall 1: 31. August -> 6 Monate später = 28. Februar (Normaljahr) bzw. 29. Feb (Schaltjahr)
    base_aug31 = datetime(2025, 8, 31, 12, 0, tzinfo=timezone.utc)
    target, days, label = calculate_target_date_and_days(base_aug31, "6_months")
    
    assert target.month == 2
    assert target.day == 28  # 2026 ist kein Schaltjahr
    assert target.year == 2026
    assert 180 <= days <= 184

    # Fall 2: Schaltjahr-Prüfung: 31. August 2023 -> 29. Februar 2024
    base_schalt = datetime(2023, 8, 31, 10, 0, tzinfo=timezone.utc)
    target_schalt, days_schalt, _ = calculate_target_date_and_days(base_schalt, "6_months")
    assert target_schalt.month == 2
    assert target_schalt.day == 29
    assert target_schalt.year == 2024

    # Fall 3: Regulärer Monat (z.B. 15. Januar -> 15. Juli)
    base_jan15 = datetime(2026, 1, 15, 8, 0, tzinfo=timezone.utc)
    target_jul15, days_jul, _ = calculate_target_date_and_days(base_jan15, "6_months")
    assert target_jul15.month == 7
    assert target_jul15.day == 15
    assert target_jul15.year == 2026


def test_ols_linear_regression():
    """Testet die OLS-Formeln für Steigung, Achsenabschnitt und R^2."""
    # Perfekte Gerade: y = 2x + 10
    x = [0.0, 1.0, 2.0, 3.0, 4.0]
    y = [10.0, 12.0, 14.0, 16.0, 18.0]
    
    m, b, r2 = linear_regression_ols(x, y)
    assert round(m, 4) == 2.0
    assert round(b, 4) == 10.0
    assert round(r2, 4) == 1.0


def test_counter_forecast_with_meter_reset():
    """Testet Zählerstandsprognosen und die Erkennung von Zählerwechseln/Rücksetzungen."""
    now = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    
    # Historie mit Zählerwechsel am Tag 10
    # Tag 0: 9500 kWh
    # Tag 5: 9600 kWh (Verbrauch: 20 kWh/Tag)
    # Tag 10: 100 kWh (Neuer Zähler!)
    # Tag 20: 300 kWh (Verbrauch am neuen Zähler: 20 kWh/Tag)
    readings = [
        Reading(id=uuid.uuid4(), timestamp=now, value=Decimal("9500.0")),
        Reading(id=uuid.uuid4(), timestamp=now + timedelta(days=5), value=Decimal("9600.0")),
        Reading(id=uuid.uuid4(), timestamp=now + timedelta(days=10), value=Decimal("100.0")),
        Reading(id=uuid.uuid4(), timestamp=now + timedelta(days=20), value=Decimal("300.0")),
    ]
    
    report = generate_forecasts_for_series(
        series_id=uuid.uuid4(),
        series_name="Stromzähler",
        series_type=SeriesType.CONTINUOUS_CUMULATIVE.value,
        unit="kWh",
        readings=readings,
        baseline_days_limit=90
    )
    
    # 30-Tage Prognose prüfen
    f30 = next(f for f in report.forecasts if f.horizon_key == "30_days")
    assert f30.quality == ForecastQuality.RESET_DETECTED
    assert "Zählerwechsel/Rücksetzung erkannt" in f30.quality_message
    
    # Täglicher Verbrauch am neuen Zähler: (300 - 100) / 10 Tage = 20 kWh/Tag
    assert f30.daily_rate == 20.0
    # 30 Tage * 20 kWh/Tag = 600 kWh Zuwachs -> 300 + 600 = 900 kWh
    assert f30.expected_change == Decimal("600.0000")
    assert f30.forecasted_value == Decimal("900.0000")


def test_insufficient_data_status():
    """Prüft, dass bei nur 1 Messwert INSUFFICIENT_DATA gemeldet wird."""
    now = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    readings = [Reading(id=uuid.uuid4(), timestamp=now, value=Decimal("75.5"))]
    
    report = generate_forecasts_for_series(
        series_id=uuid.uuid4(),
        series_name="Gewicht",
        series_type=SeriesType.DISCRETE_METRIC.value,
        unit="kg",
        readings=readings
    )
    
    for f in report.forecasts:
        assert f.quality == ForecastQuality.INSUFFICIENT_DATA
        assert f.forecasted_value is None
