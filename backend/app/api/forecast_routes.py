"""API-Routen für Prognosen."""
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.database import get_db
from app.models import User, MeasurementSeries
from app.schemas import SeriesForecastReport
from app.services.forecast_service import generate_forecasts_for_series
from app.api.deps import get_current_user

router = APIRouter(prefix="/series", tags=["Prognosen"])


@router.get("/{series_id}/forecast", response_model=SeriesForecastReport)
async def get_forecast(
    series_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Liefert die serverseitig berechneten Prognosen für alle 5 Zeithorizonte."""
    result = await db.execute(
        select(MeasurementSeries)
        .options(selectinload(MeasurementSeries.readings))
        .where(
            MeasurementSeries.id == series_id,
            MeasurementSeries.user_id == current_user.id
        )
    )
    series = result.scalar_one_or_none()
    if not series:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Messreihe nicht gefunden.")
        
    report = generate_forecasts_for_series(
        series_id=series.id,
        series_name=series.name,
        series_type=series.series_type,
        unit=series.unit,
        readings=series.readings,
        allow_decimals=series.allow_decimals,
        baseline_days_limit=90
    )
    return report
