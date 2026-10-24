"""Pydantic-Schemas für Validierung, Serialisierung und API-Ein-/Ausgabe."""
import uuid
from decimal import Decimal
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_serializer
from app.models import SeriesType


# --- Benutzer ---
class UserBase(BaseModel):
    email: EmailStr


class UserCreate(UserBase):
    password: str = Field(min_length=8, description="Passwort (mind. 8 Zeichen)")


class UserRead(UserBase):
    id: uuid.UUID
    is_active: bool
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthStatus(BaseModel):
    authenticated: bool
    user: Optional[UserRead] = None
    csrf_token: Optional[str] = None


# --- Messwerte (Readings) ---
class ReadingBase(BaseModel):
    timestamp: datetime
    value: Decimal = Field(description="Exakter Messwert (bis zu 4 Nachkommastellen)")
    note: Optional[str] = Field(default=None, max_length=1000)

    @field_serializer('value')
    def serialize_value(self, val: Decimal, _info):
        return float(val)


class ReadingCreate(ReadingBase):
    pass


class ReadingUpdate(BaseModel):
    timestamp: Optional[datetime] = None
    value: Optional[Decimal] = None
    note: Optional[str] = None
    expected_updated_at: datetime = Field(
        description="Zeitstempel von updated_at zur Prüfung auf Optimistic Concurrency"
    )


class ReadingRead(ReadingBase):
    id: uuid.UUID
    series_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


# --- Messreihen (Series) ---
class SeriesBase(BaseModel):
    name: str = Field(min_length=1, max_length=150, description="Name der Messreihe")
    unit: str = Field(min_length=1, max_length=50, description="Physikalische Einheit")
    description: Optional[str] = Field(default=None, max_length=2000)
    series_type: SeriesType = Field(default=SeriesType.DISCRETE_METRIC)
    allow_decimals: bool = Field(default=True, description="Nachkommastellen erlauben (False = nur Ganzzahlen anzeigen)")


class SeriesCreate(SeriesBase):
    pass


class SeriesUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=150)
    unit: Optional[str] = Field(default=None, min_length=1, max_length=50)
    description: Optional[str] = None
    series_type: Optional[SeriesType] = None
    allow_decimals: Optional[bool] = None
    expected_updated_at: datetime = Field(
        description="Zeitstempel von updated_at zur Prüfung auf Optimistic Concurrency"
    )


class SeriesSummary(SeriesBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    readings_count: int = 0
    latest_reading: Optional[ReadingRead] = None
    model_config = ConfigDict(from_attributes=True)


class SeriesDetail(SeriesSummary):
    readings: List[ReadingRead] = []


# --- Prognosen ---
class ForecastHorizon(str):
    DAYS_30 = "30_days"
    DAYS_60 = "60_days"
    DAYS_90 = "90_days"
    MONTHS_6 = "6_months"
    DAYS_365 = "365_days"


class ForecastQuality(str):
    GOOD = "good"
    LIMITED = "limited"
    INSUFFICIENT_DATA = "insufficient_data"
    RESET_DETECTED = "reset_detected"


class ForecastResult(BaseModel):
    horizon_key: str
    horizon_label: str
    target_date: datetime
    duration_days: float
    current_value: Optional[Decimal] = None
    forecasted_value: Optional[Decimal] = None
    expected_change: Optional[Decimal] = None
    daily_rate: Optional[float] = None
    quality: str
    quality_message: str
    r_squared: Optional[float] = None
    rule_note: Optional[str] = None


class SeriesForecastReport(BaseModel):
    series_id: uuid.UUID
    series_name: str
    series_type: str
    unit: str
    allow_decimals: bool = True
    baseline_days_used: int
    readings_considered: int
    forecasts: List[ForecastResult]


# --- Backup & Import ---
class BackupReadingItem(BaseModel):
    id: Optional[uuid.UUID] = None
    timestamp: datetime
    value: Decimal
    note: Optional[str] = None

    @field_serializer('value')
    def serialize_value(self, val: Decimal, _info):
        return float(val)


class BackupSeriesItem(BaseModel):
    id: Optional[uuid.UUID] = None
    name: str
    unit: str
    description: Optional[str] = None
    series_type: SeriesType
    allow_decimals: bool = True
    readings: List[BackupReadingItem] = []


class BackupPayload(BaseModel):
    version: str = "1.0"
    app: str = "Tracced"
    exported_at: datetime
    series_count: int
    readings_count: int
    data: List[BackupSeriesItem]


class ImportValidationReport(BaseModel):
    valid: bool
    series_to_create: int
    series_to_merge: int
    readings_to_create: int
    readings_duplicate_skipped: int
    readings_conflicts: int
    errors: List[str] = []
    warnings: List[str] = []


class ImportExecutionRequest(BaseModel):
    mode: str = Field(default="merge", pattern="^(merge|replace)$")
    data: BackupPayload
