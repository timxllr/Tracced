"""SQLAlchemy-Datenmodelle für Benutzer, Messreihen und Messwerte."""
import uuid
from datetime import datetime, timezone
from enum import Enum
from sqlalchemy import (
    Column,
    String,
    Text,
    Boolean,
    DateTime,
    Numeric,
    ForeignKey,
    Index,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.types import TypeDecorator, CHAR
from sqlalchemy.orm import relationship
from app.database import Base


# Universeller UUID-Typ für PostgreSQL und SQLite (Tests)
class GUID(TypeDecorator):
    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID())
        else:
            return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        elif dialect.name == "postgresql":
            return str(value)
        else:
            if not isinstance(value, uuid.UUID):
                return str(uuid.UUID(str(value)))
            return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        else:
            if not isinstance(value, uuid.UUID):
                return uuid.UUID(str(value))
            return value


class SeriesType(str, Enum):
    """Typ der Messreihe."""
    CONTINUOUS_CUMULATIVE = "continuous_cumulative"  # Fortlaufend summierend (z.B. Zählerstand)
    DISCRETE_METRIC = "discrete_metric"              # Diskrete Messung (z.B. Gewicht, Temperatur)


def now_utc():
    return datetime.now(timezone.utc)


class User(Base):
    """Benutzer-Entität (Geschlossenes System)."""
    __tablename__ = "users"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)

    # Beziehungen
    series = relationship("MeasurementSeries", back_populates="user", cascade="all, delete-orphan")


class MeasurementSeries(Base):
    """Messreihen-Definition."""
    __tablename__ = "measurement_series"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(150), nullable=False)
    unit = Column(String(50), nullable=False)
    description = Column(Text, nullable=True)
    series_type = Column(String(30), default=SeriesType.DISCRETE_METRIC.value, nullable=False)
    allow_decimals = Column(Boolean, default=True, nullable=False)
    
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)

    # Beziehungen
    user = relationship("User", back_populates="series")
    readings = relationship("Reading", back_populates="series", cascade="all, delete-orphan", order_by="Reading.timestamp.asc()")

    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_user_series_name"),
    )


class Reading(Base):
    """Ein einzelner datierter Messwert."""
    __tablename__ = "readings"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    series_id = Column(GUID(), ForeignKey("measurement_series.id", ondelete="CASCADE"), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    value = Column(Numeric(14, 4), nullable=False)
    note = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)

    # Beziehungen
    series = relationship("MeasurementSeries", back_populates="readings")

    __table_args__ = (
        Index("idx_readings_series_timestamp", "series_id", "timestamp"),
    )
