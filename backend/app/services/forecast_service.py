"""Mathematische Prognose-Engine für Tracced.

Unterstützt:
- 30, 60, 90, 365 Tage
- 6 Kalendermonate ab Basiszeitstempel (mit Ultimo-Regel bei Monatsenden & Schaltjahren)
- Fortlaufend summierende Zählerstände (Verbrauchsraten & Zählerwechsel-Erkennung)
- Diskrete Messungen (Lineare Regression / OLS mit R^2)
- Transparente Qualitätskennzeichnung und Unzureichende-Daten-Hinweise
"""
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import List, Optional, Tuple
from dateutil.relativedelta import relativedelta
from app.models import Reading, SeriesType
from app.schemas import ForecastResult, ForecastQuality, SeriesForecastReport


def calculate_target_date_and_days(base_date: datetime, horizon_key: str) -> Tuple[datetime, float, str]:
    """Berechnet das Zieldatum und die genaue Tagesdifferenz für einen Horizont."""
    if horizon_key == "30_days":
        target = base_date + timedelta(days=30)
        return target, 30.0, "30 Tage"
    elif horizon_key == "60_days":
        target = base_date + timedelta(days=60)
        return target, 60.0, "60 Tage"
    elif horizon_key == "90_days":
        target = base_date + timedelta(days=90)
        return target, 90.0, "90 Tage"
    elif horizon_key == "6_months":
        # Verbindliche 6-Kalendermonate-Regel:
        # Nutzt relativedelta, das Ultimo-Monatsenden exakt abbildet
        target = base_date + relativedelta(months=+6)
        days = (target - base_date).total_seconds() / 86400.0
        return target, days, "6 Kalendermonate (Halbes Jahr)"
    elif horizon_key == "365_days":
        target = base_date + timedelta(days=365)
        return target, 365.0, "365 Tage (1 Jahr)"
    else:
        target = base_date + timedelta(days=30)
        return target, 30.0, "30 Tage"


def linear_regression_ols(x_vals: List[float], y_vals: List[float]) -> Tuple[float, float, float]:
    """Berechnet Steigung m, Achsenabschnitt b und Bestimmtheitsmaß R^2 mittels OLS."""
    n = len(x_vals)
    if n < 2:
        return 0.0, y_vals[0] if y_vals else 0.0, 0.0
        
    mean_x = sum(x_vals) / n
    mean_y = sum(y_vals) / n
    
    ss_xy = sum((x_vals[i] - mean_x) * (y_vals[i] - mean_y) for i in range(n))
    ss_xx = sum((x_vals[i] - mean_x) ** 2 for i in range(n))
    ss_yy = sum((y_vals[i] - mean_y) ** 2 for i in range(n))
    
    if ss_xx == 0:
        return 0.0, mean_y, 0.0
        
    m = ss_xy / ss_xx
    b = mean_y - m * mean_x
    
    # R-Quadrat (Bestimmtheitsmaß)
    r_squared = (ss_xy ** 2) / (ss_xx * ss_yy) if ss_yy > 0 else 1.0
    return m, b, max(0.0, min(1.0, r_squared))


def generate_forecasts_for_series(
    series_id,
    series_name: str,
    series_type: str,
    unit: str,
    readings: List[Reading],
    allow_decimals: bool = True,
    baseline_days_limit: int = 90
) -> SeriesForecastReport:
    """Erstellt den vollständigen Prognosebericht für alle 5 Zeithorizonte."""
    horizons = ["30_days", "60_days", "90_days", "6_months", "365_days"]
    
    # Chronologisch sortieren
    sorted_readings = sorted(readings, key=lambda r: r.timestamp)
    
    # Prüfung auf Mindestdaten
    if len(sorted_readings) < 2:
        empty_results = []
        base_time = sorted_readings[-1].timestamp if sorted_readings else datetime.now(timezone.utc)
        curr_val = sorted_readings[-1].value if sorted_readings else None
        
        for h in horizons:
            t_date, days, label = calculate_target_date_and_days(base_time, h)
            empty_results.append(ForecastResult(
                horizon_key=h,
                horizon_label=label,
                target_date=t_date,
                duration_days=days,
                current_value=curr_val,
                forecasted_value=None,
                expected_change=None,
                daily_rate=None,
                quality=ForecastQuality.INSUFFICIENT_DATA,
                quality_message="Mindestens 2 Messwerte an unterschiedlichen Zeitpunkten erforderlich.",
                r_squared=None,
                rule_note=None
            ))
            
        return SeriesForecastReport(
            series_id=series_id,
            series_name=series_name,
            series_type=series_type,
            unit=unit,
            allow_decimals=allow_decimals,
            baseline_days_used=0,
            readings_considered=len(sorted_readings),
            forecasts=empty_results
        )
        
    latest_reading = sorted_readings[-1]
    base_time = latest_reading.timestamp
    curr_val = latest_reading.value
    
    # Standard-Bezugszeitraum: Letzte 90 Tage vor dem letzten Messwert
    cutoff_time = base_time - timedelta(days=baseline_days_limit)
    window_readings = [r for r in sorted_readings if r.timestamp >= cutoff_time]
    
    # Falls im 90-Tage-Fenster weniger als 2 Werte liegen, den gesamten Datensatz nutzen
    if len(window_readings) < 2:
        window_readings = sorted_readings
        
    span_seconds = (window_readings[-1].timestamp - window_readings[0].timestamp).total_seconds()
    span_days = max(span_seconds / 86400.0, 0.0001)
    
    forecasts = []
    
    # --- FALL A: Fortlaufend summierend (Zählerstände) ---
    if series_type == SeriesType.CONTINUOUS_CUMULATIVE.value or series_type == "continuous_cumulative":
        # Prüfung auf Zählerstandsrücksetzung (Meter Reset / Zählertausch)
        reset_detected = False
        reset_time = None
        for i in range(len(window_readings) - 1):
            if window_readings[i+1].value < window_readings[i].value:
                reset_detected = True
                reset_time = window_readings[i+1].timestamp
                break
                
        # Falls Reset erkannt: nur die Daten ab dem Reset verwenden
        if reset_detected and reset_time:
            active_readings = [r for r in window_readings if r.timestamp >= reset_time]
            if len(active_readings) < 2:
                active_readings = window_readings[-2:]
        else:
            active_readings = window_readings
            
        active_span_days = max((active_readings[-1].timestamp - active_readings[0].timestamp).total_seconds() / 86400.0, 0.0001)
        val_delta = float(active_readings[-1].value - active_readings[0].value)
        daily_rate = val_delta / active_span_days
        
        # Plausibilität: Zählerstände dürfen nicht sinken
        if daily_rate < 0:
            daily_rate = 0.0
            
        for h in horizons:
            t_date, days, label = calculate_target_date_and_days(base_time, h)
            extrapolated_delta = daily_rate * days
            forecasted_val = curr_val + Decimal(str(round(extrapolated_delta, 4)))
            
            # Qualitätsbewertung
            quality = ForecastQuality.GOOD
            msg = f"Zuverlässige Extrapolation basierend auf einer täglichen Verbrauchsrate von {round(daily_rate, 3)} {unit}/Tag."
            
            if reset_detected:
                quality = ForecastQuality.RESET_DETECTED
                msg = f"Hinweis: Zählerwechsel/Rücksetzung erkannt. Berechnung nutzt nur Daten seit dem {reset_time.strftime('%d.%m.%Y')}."
            elif span_days < (days * 0.15):
                quality = ForecastQuality.LIMITED
                msg = f"Eingeschränkte Genauigkeit: Beobachtungszeitraum ({round(span_days, 1)} Tage) deckt weniger als 15% des Horizonts ab."
                
            rule_note = None
            if h == "6_months":
                rule_note = f"Stichtag exakt 6 Kalendermonate ab {base_time.strftime('%d.%m.%Y')} ({round(days, 1)} Tage, Ultimo-geregelt)."
                
            forecasts.append(ForecastResult(
                horizon_key=h,
                horizon_label=label,
                target_date=t_date,
                duration_days=days,
                current_value=curr_val,
                forecasted_value=forecasted_val,
                expected_change=Decimal(str(round(extrapolated_delta, 4))),
                daily_rate=round(daily_rate, 4),
                quality=quality,
                quality_message=msg,
                r_squared=None,
                rule_note=rule_note
            ))

    # --- FALL B: Diskrete Messungen (Lineare Regression) ---
    else:
        # x-Werte in Tagen relativ zum ersten Messwert im Fenster
        t0 = window_readings[0].timestamp
        x_vals = [(r.timestamp - t0).total_seconds() / 86400.0 for r in window_readings]
        y_vals = [float(r.value) for r in window_readings]
        
        m, b, r2 = linear_regression_ols(x_vals, y_vals)
        
        for h in horizons:
            t_date, days, label = calculate_target_date_and_days(base_time, h)
            target_x = (t_date - t0).total_seconds() / 86400.0
            pred_y = m * target_x + b
            delta = pred_y - float(curr_val)
            
            # Qualität & Warnungen
            quality = ForecastQuality.GOOD
            msg = f"Lineare Regression (R² = {round(r2, 2)})."
            
            if len(window_readings) < 3:
                quality = ForecastQuality.LIMITED
                msg = "Geringe Datenbasis (nur 2 Messpunkte). Keine Regressionsgüte bestimmbar."
            elif r2 < 0.3:
                quality = ForecastQuality.LIMITED
                msg = f"Starke Schwankungen / geringer linearer Trend (R² = {round(r2, 2)})."
            elif span_days < (days * 0.1):
                quality = ForecastQuality.LIMITED
                msg = f"Extrapolationswarnung: Datenzeitraum ({round(span_days, 1)} Tage) deckt unter 10% des Horizonts ab."
                
            rule_note = None
            if h == "6_months":
                rule_note = f"Stichtag exakt 6 Kalendermonate ab {base_time.strftime('%d.%m.%Y')} ({round(days, 1)} Tage, Ultimo-geregelt)."
                
            forecasts.append(ForecastResult(
                horizon_key=h,
                horizon_label=label,
                target_date=t_date,
                duration_days=days,
                current_value=curr_val,
                forecasted_value=Decimal(str(round(pred_y, 4))),
                expected_change=Decimal(str(round(delta, 4))),
                daily_rate=round(m, 4),
                quality=quality,
                quality_message=msg,
                r_squared=round(r2, 3),
                rule_note=rule_note
            ))
            
    return SeriesForecastReport(
        series_id=series_id,
        series_name=series_name,
        series_type=series_type,
        unit=unit,
        allow_decimals=allow_decimals,
        baseline_days_used=int(span_days),
        readings_considered=len(window_readings),
        forecasts=forecasts
    )
