"""Haupteinstiegspunkt der FastAPI-Anwendung."""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text
from app.config import settings
from app.database import engine, Base
from app.api.auth_routes import router as auth_router
from app.api.series_routes import router as series_router
from app.api.reading_routes import router as reading_router
from app.api.forecast_routes import router as forecast_router
from app.api.backup_routes import router as backup_router


def _apply_schema_upgrades(connection):
    """Ergänzt neue Spalten in bestehenden Datenbanken (einfache, idempotente Migration)."""
    inspector = inspect(connection)
    columns = {col["name"] for col in inspector.get_columns("measurement_series")}
    if "allow_decimals" not in columns:
        default = "TRUE" if connection.dialect.name == "postgresql" else "1"
        connection.execute(text(
            f"ALTER TABLE measurement_series ADD COLUMN allow_decimals BOOLEAN NOT NULL DEFAULT {default}"
        ))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Tabellen initialisieren falls nicht vorhanden
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_apply_schema_upgrades)
    yield
    await engine.dispose()


app = FastAPI(
    title="Tracced API",
    version="1.0.0",
    description="Produktionsorientierter Messwert-Tracker mit Synchronisation, Backup und Prognose",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS Middleware konfigurieren
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API-Router einbinden
api_prefix = "/api/v1"
app.include_router(auth_router, prefix=api_prefix)
app.include_router(series_router, prefix=api_prefix)
app.include_router(reading_router, prefix=api_prefix)
app.include_router(forecast_router, prefix=api_prefix)
app.include_router(backup_router, prefix=api_prefix)


@app.get("/health", tags=["System"])
async def health_check():
    """System-Healthcheck."""
    return {"status": "ok", "app": "Tracced", "version": "1.0.0"}


# Statische Frontend-Auslieferung für lokale Entwicklung und Single Page App
# Sucht nach frontend/ relativ zum Projekt-Root oder Backend-Verzeichnis
frontend_candidates = [
    os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../frontend")),
    os.path.abspath(os.path.join(os.path.dirname(__file__), "../../frontend")),
    os.path.abspath(os.path.join(os.getcwd(), "frontend")),
    os.path.abspath(os.path.join(os.getcwd(), "../frontend")),
]

frontend_dir = None
for candidate in frontend_candidates:
    if os.path.isdir(candidate) and os.path.exists(os.path.join(candidate, "index.html")):
        frontend_dir = candidate
        break

if frontend_dir:
    # Mount für CSS & JS Unterverzeichnisse
    app.mount("/css", StaticFiles(directory=os.path.join(frontend_dir, "css")), name="css")
    app.mount("/js", StaticFiles(directory=os.path.join(frontend_dir, "js")), name="js")

    @app.get("/", include_in_schema=False)
    async def serve_index():
        return FileResponse(os.path.join(frontend_dir, "index.html"))

    @app.get("/manifest.json", include_in_schema=False)
    async def serve_manifest():
        manifest_path = os.path.join(frontend_dir, "manifest.json")
        if os.path.exists(manifest_path):
            return FileResponse(manifest_path, media_type="application/manifest+json")
        return JSONResponse(status_code=404, content={"detail": "Not found"})
