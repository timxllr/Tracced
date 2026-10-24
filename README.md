# Tracced

Tracced ist eine selbst gehostete Webanwendung zum Erfassen, Synchronisieren, Visualisieren und Prognostizieren von Messreihen – zum Beispiel Zählerstände, Verbräuche, Gewicht oder Temperatur.

Die Anwendung ist bewusst schlank: kein Docker, kein Frontend-Build, keine Node.js-Abhängigkeit. Das Backend läuft mit Python und PostgreSQL (für Entwicklung und Tests auch mit SQLite), das Frontend besteht aus statischem HTML, CSS und nativen JavaScript-Modulen.

## Funktionen

### Benutzer & Anmeldung
- Geschlossenes System ohne öffentliche Registrierung
- Benutzeranlage über die Server-CLI
- Login, Logout und Sitzungsstatus
- Argon2id-Passwort-Hashing
- HttpOnly-Session-Cookies mit SameSite-Schutz
- CSRF-Schutz bei allen schreibenden Anfragen
- Strikte Benutzertrennung auf Datenbankebene

### Messreihen
- Anlegen, Anzeigen, Bearbeiten und Löschen
- Zwei Typen: fortlaufender Zählerstand und diskrete Messung
- Name, Einheit, Beschreibung und Typ pro Messreihe
- Eindeutige Namen pro Benutzer
- Optionale Ganzzahl-Anzeige: Nachkommastellen lassen sich pro Reihe ein- und ausschalten
- Umschalten auch bei bereits bestehenden Messreihen möglich

### Messwerte
- Erfassen, Korrigieren und Löschen einzelner Messwerte
- Zeitstempel, Wert und optionale Notiz
- Chronologische Sortierung und Anzeige des jeweils letzten Werts
- Ganzzahl-Modus blendet Nachkommastellen in Tabelle, Dashboard, Diagramm und Prognose aus

### Visualisierung
- Dashboard mit allen Messreihen, aktuellem Wert und Anzahl der Einträge
- Detailansicht mit Messwerttabelle
- Interaktives Liniendiagramm auf Canvas-Basis, ohne externe Chart-Bibliothek
- Responsives Layout und PWA-Manifest

### Prognosen
Serverseitige Berechnung für fünf Horizonte:
- 30 Tage
- 60 Tage
- 90 Tage
- 6 Kalendermonate inklusive Monatsende- und Schaltjahr-Regel
- 365 Tage

Je nach Reihentyp:
- **Zählerstände:** tägliche Verbrauchsrate, Erkennung von Zählerwechseln und Rücksetzungen
- **Diskrete Messungen:** lineare Regression (OLS) inklusive Bestimmtheitsmaß R²

Jede Prognose enthält eine Qualitätskennzeichnung mit Hinweisen zu geringer Datenbasis, starken Schwankungen oder erkannten Zählerwechseln.

### Konsistenz & Synchronisation
- Optimistic Concurrency Control über `updated_at`
- Konflikterkennung mit HTTP 409, wenn ein Datensatz zwischenzeitlich auf einem anderen Gerät geändert wurde
- Automatischer Abgleich der aktuellen Ansicht beim Zurückkehren in den Browser-Tab
- Synchronisationsanzeige im Kopfbereich der Anwendung

### Backup & Wiederherstellung
- Vollständiger JSON-Export mit stabilen UUIDs
- CSV-Export für Tabellenkalkulationen (UTF-8 mit BOM, Semikolon-getrennt)
- Vorab-Validierung einer Importdatei mit detailliertem Prüfbericht
- Atomarer Import: entweder vollständig erfolgreich oder vollständiger Rollback
- Zwei Importmodi: Zusammenführen (Merge) oder vollständiges Ersetzen (Replace)
- Schutz vor Duplikaten und Datenverlust

### Betrieb
- Automatische Erstellung des Datenbankschemas beim Start
- Einfache, idempotente Schema-Erweiterung für neue Spalten
- Healthcheck unter `/health`
- Interaktive API-Dokumentation unter `/docs`
- Vorlagen für systemd und Nginx unter `deploy/`

## Technik

| Bereich | Verwendet |
| --- | --- |
| Backend | Python, FastAPI, SQLAlchemy (async), Pydantic |
| Datenbank | PostgreSQL (Produktion), SQLite (Entwicklung und Tests) |
| Authentifizierung | Argon2id, HMAC-signierte Session-Tokens, CSRF-Token |
| Frontend | HTML5, CSS-Variablen, native JavaScript-ES-Module, Canvas |
| Deployment | Uvicorn, systemd, Nginx bzw. Nginx Proxy Manager |

## Projektstruktur

```text
Tracced/
├── backend/
│   ├── app/
│   │   ├── api/            # Auth-, Reihen-, Messwert-, Prognose- und Backup-Routen
│   │   ├── services/       # Prognose- und Backup-Logik
│   │   ├── auth.py         # Passwort-Hashing, Sessions und CSRF
│   │   ├── config.py       # Konfiguration über Umgebungsvariablen
│   │   ├── database.py     # Async-Engine und Datenbanksitzungen
│   │   ├── models.py       # SQLAlchemy-Modelle
│   │   ├── schemas.py      # Pydantic-Ein- und Ausgabeschemata
│   │   ├── cli.py          # Benutzerverwaltung und Datenbank-Initialisierung
│   │   └── main.py         # FastAPI-App, statisches Frontend, Schema-Upgrades
│   ├── tests/              # Pytest-Suite mit SQLite In-Memory
│   ├── requirements.txt
│   └── pytest.ini
├── frontend/
│   ├── css/                # Design-Tokens und Layout
│   ├── js/                 # API-Client, Routing, Diagramme und Ansichten
│   ├── index.html
│   └── manifest.json
├── deploy/
│   ├── nginx/              # Nginx-VirtualHost
│   └── systemd/            # systemd-Service
├── .env.example
└── AGENTS.md               # Hinweise für KI-Agenten
```

## Lokaler Start

### 1. Backend vorbereiten

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Konfiguration anlegen

```bash
cp ../.env.example .env
```

Für einen schnellen lokalen Test ohne PostgreSQL genügt in `backend/.env`:

```ini
DATABASE_URL=sqlite+aiosqlite:///./tracced.db
```

Für PostgreSQL die Verbindung entsprechend anpassen:

```ini
DATABASE_URL=postgresql+asyncpg://tracced_user:passwort@127.0.0.1:5432/tracced_db
```

### 3. Benutzer anlegen

```bash
python -m app.cli create-user --email benutzer@example.com --password "DeinSicheresPasswort"
```

### 4. Server starten

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Danach sind erreichbar:

- Anwendung: `http://127.0.0.1:8000`
- API-Dokumentation: `http://127.0.0.1:8000/docs`
- Healthcheck: `http://127.0.0.1:8000/health`

Wichtig: Befehle immer aus dem Verzeichnis `backend/` ausführen, da `.env` und die relative SQLite-Datei vom Arbeitsverzeichnis abhängen.

## Konfiguration

Die Konfiguration erfolgt über `backend/.env` oder Umgebungsvariablen:

| Variable | Bedeutung | Standard |
| --- | --- | --- |
| `DATABASE_URL` | SQLAlchemy-Verbindungs-URL | lokale PostgreSQL-Datenbank |
| `SECRET_KEY` | Schlüssel für Session-Tokens | unsicherer Entwicklungswert |
| `SESSION_EXPIRE_DAYS` | Gültigkeit der Sitzung in Tagen | `30` |
| `SECURE_COOKIES` | Cookies nur über HTTPS | `false` |
| `COOKIE_SAMESITE` | SameSite-Attribut (`lax` oder `strict`) | `lax` |
| `ALLOWED_ORIGINS` | Komma-separierte CORS-Origins | lokale Adressen |
| `HOST` | Bind-Adresse | `127.0.0.1` |
| `PORT` | Port | `8000` |
| `DEBUG` | SQL-Logging aktivieren | `false` |
| `APP_ENV` | Laufzeitumgebung | `production` |

Für den Produktivbetrieb unbedingt einen zufälligen `SECRET_KEY` erzeugen und `SECURE_COOKIES=true` setzen:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

## Tests

```bash
cd backend
venv/bin/pytest -v
```

Die Tests verwenden eine SQLite-In-Memory-Datenbank und benötigen kein PostgreSQL.

## Deployment

Unter `deploy/` liegen Vorlagen für:

- `deploy/systemd/tracced.service` – Uvicorn-Dienst mit Härtung
- `deploy/nginx/tracced.conf` – HTTPS-Reverse-Proxy und Auslieferung des Frontends

Ablauf in Kurzform:

1. Projekt auf den Server übertragen (ohne `venv`, `.env` und lokale Datenbank).
2. PostgreSQL-Datenbank und Benutzer anlegen.
3. Virtuelle Umgebung erstellen und Abhängigkeiten installieren.
4. `backend/.env` mit produktiven Werten anlegen.
5. Benutzer per CLI erstellen.
6. systemd-Service aktivieren.
7. Nginx bzw. Nginx Proxy Manager auf `127.0.0.1:8000` zeigen lassen.

## Hinweise

- Es gibt keine offene Registrierung. Neue Konten werden ausschließlich über die CLI angelegt.
- Neue Datenbankspalten werden beim Start automatisch ergänzt; bestehende Daten bleiben erhalten.
- Das Frontend wird ohne Build-Schritt direkt vom Backend bzw. von Nginx ausgeliefert.
- Die Anwendung ist für den Betrieb hinter HTTPS und einen Reverse-Proxy ausgelegt.
