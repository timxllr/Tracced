# AGENTS.md

Arbeitsanleitung für KI-Agenten, die an **Tracced** Änderungen vornehmen.

## 1. Was ist Tracced?

Tracced ist eine selbst gehostete Webanwendung zum Erfassen, Synchronisieren, Visualisieren und Prognostizieren von Messreihen. Typische Anwendungsfälle sind Zählerstände (Strom, Wasser, Gas, Kilometer), Verbräuche sowie persönliche Messwerte wie Gewicht oder Temperatur.

Das Projekt ist für den produktiven, containerfreien Betrieb auf einem Linux-Server ausgelegt:

- FastAPI-Backend mit asynchronem SQLAlchemy
- PostgreSQL in Produktion, SQLite für lokale Entwicklung und Tests
- Statisches Frontend ohne Build-Schritt und ohne Node.js
- Geschlossenes Benutzersystem ohne öffentliche Registrierung
- Serverseitige Prognosen und vollständiges Backup/Restore

## 2. Wichtige Dateien

### Backend

| Datei | Zweck |
| --- | --- |
| `backend/app/main.py` | FastAPI-App, Router-Registrierung, Auslieferung des Frontends, Healthcheck, Schema-Upgrades |
| `backend/app/config.py` | Pydantic-Settings aus `.env` und Umgebungsvariablen |
| `backend/app/database.py` | Async-Engine, `AsyncSessionLocal`, `Base` und `get_db` |
| `backend/app/models.py` | SQLAlchemy-Modelle: `User`, `MeasurementSeries`, `Reading`, `SeriesType`, `GUID` |
| `backend/app/schemas.py` | Alle Pydantic-Schemata für API, Prognosen und Backup |
| `backend/app/auth.py` | Argon2id, Session-Token, CSRF-Erzeugung und -Prüfung |
| `backend/app/api/deps.py` | Auth-Dependencies und CSRF-Prüfung für schreibende Anfragen |
| `backend/app/api/auth_routes.py` | Login, Logout, Sitzungsstatus |
| `backend/app/api/series_routes.py` | CRUD für Messreihen inklusive Konflikterkennung |
| `backend/app/api/reading_routes.py` | CRUD für Messwerte inklusive Konflikterkennung |
| `backend/app/api/forecast_routes.py` | Prognose-Endpunkt pro Messreihe |
| `backend/app/api/backup_routes.py` | JSON-/CSV-Export, Import-Validierung und -Ausführung |
| `backend/app/services/forecast_service.py` | Prognose-Engine für alle Horizonte |
| `backend/app/services/backup_service.py` | Export, Validierung und atomarer Import |
| `backend/app/cli.py` | `create-user` und `init-db` |
| `backend/tests/` | Pytest-Suite mit SQLite In-Memory |

### Frontend

| Datei | Zweck |
| --- | --- |
| `frontend/index.html` | Einstiegspunkt und Grundgerüst |
| `frontend/manifest.json` | PWA-Manifest |
| `frontend/css/variables.css` | Farben, Abstände und Design-Tokens |
| `frontend/css/style.css` | Layout, Komponenten und responsive Darstellung |
| `frontend/js/app.js` | Navigation, Ansichtswechsel, Auth-Initialisierung, Logout |
| `frontend/js/api.js` | Fetch-Wrapper, CSRF-Header, Sync-Status und Fehlerbehandlung |
| `frontend/js/charts.js` | Canvas-Liniendiagramm inklusive Achsenformatierung |
| `frontend/js/views/auth_view.js` | Login-Ansicht |
| `frontend/js/views/dashboard.js` | Übersicht, Reihenkarten und Anlegen-/Bearbeiten-Dialog |
| `frontend/js/views/series_detail.js` | Detailansicht, Messwerttabelle und Messwert-Dialog |
| `frontend/js/views/forecast_view.js` | Prognosekarten und Methodikhinweise |
| `frontend/js/views/backup_view.js` | Export, Import, Validierungsbericht und Importausführung |

### Betrieb

| Datei | Zweck |
| --- | --- |
| `deploy/systemd/tracced.service` | Produktionsdienst für Uvicorn |
| `deploy/nginx/tracced.conf` | HTTPS-Reverse-Proxy und statische Auslieferung |
| `.env.example` | Vorlage für lokale bzw. produktive Konfiguration |
| `.gitignore` | Ausschluss von Secrets, Datenbanken, Caches und virtuellen Umgebungen |
| `README.md` | Nutzer- und Entwicklerdokumentation |

## 3. Datenmodell und API

### Modell

- `User`: E-Mail, Argon2id-Passwort-Hash, Aktivstatus
- `MeasurementSeries`: gehört zu einem Benutzer; Name, Einheit, Beschreibung, `series_type`, `allow_decimals`
- `Reading`: gehört zu einer Messreihe; Zeitstempel, `Numeric(14,4)`-Wert, Notiz
- `SeriesType`: `continuous_cumulative` (Zählerstand) oder `discrete_metric` (diskrete Messung)
- Alle IDs sind UUIDs. `GUID` übersetzt sie für PostgreSQL und SQLite.
- Messreihennamen sind pro Benutzer case-insensitiv eindeutig.

### API

Alle Routen liegen unter `/api/v1`:

- `/auth/login`, `/auth/logout`, `/auth/status`
- `/series` und `/series/{id}`
- `/series/{id}/readings`
- `/readings/{id}`
- `/series/{id}/forecast`
- `/backup/export/json`, `/backup/export/csv`, `/backup/validate`, `/backup/execute`
- `/health` und `/docs` außerhalb des API-Prefixes

### Konsistenz

- Schreibende Anfragen benötigen bei Cookie-Auth den Header `X-CSRF-Token`.
- Änderungen an Reihen und Messwerten senden `expected_updated_at`.
- Bei Abweichung antwortet der Server mit HTTP 409.
- Jede Reihe und jeder Messwert wird zusätzlich über den Benutzer geprüft; fremde Datensätze liefern 404.

## 4. Wo ändert man was?

| Aufgabe | Relevante Dateien |
| --- | --- |
| Neues Feld an Messreihen | `models.py`, `schemas.py`, alle manuellen `SeriesSummary`-Konstruktionen in `api/series_routes.py`, Migration in `main.py`, `services/backup_service.py`, Frontend-Formulare |
| Neues Feld an Messwerten | `models.py`, `schemas.py`, `api/reading_routes.py`, `services/backup_service.py`, `series_detail.js`, `charts.js` |
| Neuer API-Endpunkt | Passende Datei unter `api/`, Router in `main.py` registrieren, Schema in `schemas.py` ergänzen |
| Neue Frontend-Ansicht | Neue Datei unter `frontend/js/views/`, Import und Route in `frontend/js/app.js`, ggf. Styles in `style.css` |
| Prognosealgorithmus | `services/forecast_service.py`; Ausgabeformat in `schemas.py`, Darstellung in `forecast_view.js` |
| Backup-Format | `schemas.py` (`BackupPayload`), `services/backup_service.py`, `backup_view.js` |
| Anmeldung oder CSRF | `auth.py`, `api/deps.py`, `api/auth_routes.py` – Sicherheitsniveau nicht abschwächen |
| Design oder Layout | `css/variables.css` für Tokens, `css/style.css` für Komponenten |
| Datenbankmigration | `_apply_schema_upgrades` in `main.py` ergänzen |
| Deployment | `deploy/systemd/tracced.service`, `deploy/nginx/tracced.conf`, `.env.example` |

### Neues Feld: Checkliste

1. Spalte in `models.py` ergänzen.
2. Feld in den passenden Pydantic-Schemata ergänzen; bei Backup-Feldern immer einen Standardwert setzen, damit alte Backups weiter funktionieren.
3. Migrationsschritt in `_apply_schema_upgrades` ergänzen. `create_all` legt nur fehlende Tabellen an, keine neuen Spalten.
4. API-Ausgaben prüfen: `SeriesSummary` wird in `series_routes.py` an mehreren Stellen manuell konstruiert.
5. Frontend-Formular, Anzeige und ggf. Chart ergänzen.
6. Tests erweitern und ausführen.

## 5. Konventionen

- **Sprache:** UI-Texte, Fehlermeldungen, Docstrings und Kommentare auf Deutsch. Code-Bezeichner (Variablen, Funktionen, Felder) auf Englisch.
- **Datumsangaben:** intern UTC, Anzeige in `de-DE`.
- **Werte:** Messwerte als `Decimal` mit maximal vier Nachkommastellen speichern; die API serialisiert sie als Zahl.
- **Frontend:** reines HTML/CSS/JavaScript mit ES-Modulen. Kein Build-Schritt, kein Framework und keine neuen Abhängigkeiten ohne zwingenden Grund.
- **API:** neue Endpunkte unter dem bestehenden Präfix `/api/v1`; Antworten über Pydantic-Schemata.
- **Sicherheit:** keine offene Registrierung, keine Secrets im Repository, CSRF- und Eigentümerprüfungen beibehalten.
- **Kompatibilität:** Änderungen am Backup-Format müssen abwärtskompatibel sein (Standardwerte für neue Felder).
- **Ganzzahl-Modus:** `allow_decimals=false` beeinflusst nur Anzeige und Eingabeschritt im Frontend. Werte werden weiterhin als Dezimalzahl gespeichert.

## 6. Lokale Entwicklung

```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Wichtig:

- Immer aus `backend/` starten. `.env` und die relative SQLite-Datei hängen vom Arbeitsverzeichnis ab.
- Für einen schnellen Start ohne PostgreSQL in `backend/.env` setzen:
  `DATABASE_URL=sqlite+aiosqlite:///./tracced.db`
- Benutzer anlegen:
  `python -m app.cli create-user --email test@example.com --password "TestPasswort123!"`
- Frontend-Änderungen benötigen keinen Neustart, aber einen Browser-Reload (ggf. hart mit `Strg+Shift+R`).

## 7. Tests und Verifikation

```bash
cd backend
venv/bin/pytest -v
```

- Die Tests laufen mit einer frischen SQLite-In-Memory-Datenbank und benötigen kein PostgreSQL.
- Bei Änderungen an Modellen oder Migrationen zusätzlich die Migration gegen eine Kopie einer bestehenden SQLite-Datenbank prüfen.
- Bei API-Änderungen die betroffenen Endpunkte mit einem gültigen Session-Cookie und CSRF-Header testen.
- Bei Frontend-Änderungen die betroffenen Ansichten im Browser prüfen: Dashboard, Detailansicht, Prognose und Backup.

## 8. Fallstricke

- **Schema-Updates:** `Base.metadata.create_all` ändert bestehende Tabellen nicht. Neue Spalten immer über `_apply_schema_upgrades` ergänzen.
- **SQLite vs. PostgreSQL:** Beim `ALTER TABLE` den passenden Default verwenden (`TRUE` für PostgreSQL, `1` für SQLite).
- **Manuelle API-Ausgaben:** `SeriesSummary` wird in `series_routes.py` an drei Stellen explizit aufgebaut. Neue Pflichtfelder sonst vergessen.
- **Relative Pfade:** Server und CLI aus `backend/` starten, sonst wird eine neue, leere Datenbank angelegt.
- **CSRF:** Schreibende Requests aus dem Frontend laufen über `apiRequest`, das den Token automatisch setzt. Bei neuen Direktaufrufen daran denken.
- **Chart:** `charts.js` erhält Optionen wie `{ decimals: false }`. Bei neuen Darstellungsoptionen die Achsenbeschriftung nicht abschneiden.
- **Backups:** Neue Felder in `BackupSeriesItem` oder `BackupReadingItem` immer mit Standardwert versehen.
- **Datenbank nicht committen:** `*.db`, `.env` und `venv/` sind absichtlich ignoriert.
- **Keine Daten löschen:** Lokale SQLite-Dateien können echte Testdaten enthalten. Vor Migrationstests eine Kopie verwenden.

## 9. Definition of Done

Eine Änderung ist fertig, wenn:

1. die Backend-Tests erfolgreich laufen,
2. bestehende Datenbanken durch eine idempotente Migration weiter funktionieren,
3. die betroffenen Ansichten im Browser geprüft wurden,
4. Sicherheits- und Eigentümerprüfungen unverändert greifen,
5. keine Secrets, Datenbanken oder virtuellen Umgebungen im Repository landen,
6. bei sichtbaren Änderungen README oder diese Datei aktualisiert wurden.
