"""Konfigurationsmanagement für Tracced via Pydantic Settings."""
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Datenbank
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://tracced_user:tracced_pass@127.0.0.1:5432/tracced_db",
        description="Async PostgreSQL Verbindungs-URL"
    )

    # Sicherheit & Auth
    SECRET_KEY: str = Field(
        default="insecure-dev-secret-key-change-this-in-production-32chars!",
        description="Geheimer Schlüssel für HMAC-Token-Signierung"
    )
    SESSION_EXPIRE_DAYS: int = Field(default=30, description="Gültigkeitsdauer der Sitzung in Tagen")
    SECURE_COOKIES: bool = Field(default=False, description="Nur HTTPS für Cookies erlauben (Produktion: True)")
    COOKIE_SAMESITE: str = Field(default="lax", description="SameSite-Attribut für Session-Cookies (lax oder strict)")

    # Server
    HOST: str = Field(default="127.0.0.1")
    PORT: int = Field(default=8000)
    DEBUG: bool = Field(default=False)
    APP_ENV: str = Field(default="production")

    # CORS
    ALLOWED_ORIGINS: str = Field(
        default="http://127.0.0.1:8000,http://localhost:8000",
        description="Komma-separierte Liste erlaubter Origins"
    )

    @property
    def cors_origins(self) -> List[str]:
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]


settings = Settings()
