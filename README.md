# Tracced

Tracced ist eine schlank, selbst gehostete Webanwendung zum Erfassen, Synchronisieren, Visualisieren und Prognostizieren von Messreihen – zum Beispiel Zählerstände (Strom, Wasser, Gas, Kilometer), Verbräuche oder persönliche Messwerte wie Gewicht und Temperatur.

Das Projekt verzichtet bewusst auf Docker, Node.js und Build-Schritte. Das Backend läuft mit Python und PostgreSQL, das Frontend besteht aus statischem HTML, CSS und nativen JavaScript-Modulen.

---

## Hauptfunktionen

### Messreihen & Messwerte
- Anlegen, Bearbeiten und Löschen von Messreihen
- Zwei Reihentypen: fortlaufende Zählerstände und diskrete Messungen
- Ganzzahl- oder Dezimalanzeige pro Reihe einstellbar
- Chronologische Erfassung mit Zeitstempel, Wert und optionaler Notiz

### Visualisierung
- Dashboard mit allen Messreihen, aktuellem Wert und Einträge-Anzahl
- Detailansicht mit tabellarischer Wertübersicht
- Interaktives Liniendiagramm (Canvas, ohne externe Bibliotheken)
- Responsives Layout und PWA-Manifest für mobile Geräte

### Prognosen
Serverseitige Berechnung für fünf Horizonte:
- 30, 60 und 90 Tage
- 6 Kalendermonate
- 365 Tage

Je nach Reihentyp kommen unterschiedliche Verfahren zum Einsatz (Verbrauchsrate mit Zählerwechselerkennung bzw. lineare Regression mit R²).

### Import pro Messreihe
Auf jeder Detailansicht einer Messreihe können externe CSV-Daten importiert werden:

- **Datei-Upload oder Inline-Eingabe** der CSV-Daten
- **Spalten-Mapping**: Festlegung, welche Spalte Zeitstempel, Wert und optionale Notiz enthält
- **Vorschau**: Vor dem Import werden gültige und ungültige Zeilen angezeigt
- **Merge**: Neue Werte werden ergänzt, vorhandene Zeitstempel werden übersprungen
- **Replace**: Bestehende Werte der Reihe werden vor dem Import gelöscht

Unterstützte Zeitstempel-Formate umfassen unter anderem `2026-10-28 17:30:20` und `2026-10-28T17:30:20`.

### Backup & Wiederherstellung
- Vollständiger JSON-Export aller Messreihen und Messwerte
- CSV-Export für Tabellenkalkulationen
- Atomarer Import: entweder vollständig erfolgreich oder vollständiger Rollback
- Zwei Importmodi: Zusammenführen oder vollständiges Ersetzen

---

## Schnellstart (Beispiel: Ubuntu VPS)

Die Installation erfolgt auf einem Linux-Server mit PostgreSQL, systemd und einem Reverse-Proxy (z. B. Nginx Proxy Manager).

### 1. Projekt klonen
```bash
git clone <DEIN_REPOSITORY> /home/tracced
cd /home/tracced
```

### 2. Konfiguration anpassen
Die Konfigurationsdatei liegt unter `backend/.env`. Öffne sie und trage deine Werte ein:

```ini
# PostgreSQL Verbindung (Format: postgresql+asyncpg://BENUTZER:PASSWORT@HOST:PORT/DATENBANK)
DATABASE_URL=postgresql+asyncpg://tracced_user:<DEIN_DB_PASSWORT>@127.0.0.1:5432/tracced_db

# Sicherheit & Sitzungsverwaltung
# Erzeuge einen sicheren Key via: python3 -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=<DEIN_SECRETER_KEY>

# Server-Konfiguration
APP_ENV=production
DEBUG=false
HOST=0.0.0.0
PORT=8000

# CORS & Sicherheit
ALLOWED_ORIGINS=https://<DEINE_DOMAIN.de>
SECURE_COOKIES=true
```

Ersetze alle Platzhalter in Großbuchstaben (z. B. `<DEIN_DB_PASSWORT>`, `<DEINE_DOMAIN.de>`) durch deine eigenen Werte.

### 3. Abhängigkeiten installieren
```bash
cd /home/tracced/backend
chmod 600 .env
pip3 install --break-system-packages --ignore-installed -r requirements.txt
```

### 4. Datenbank anlegen
```bash
sudo -u postgres psql -c "CREATE USER tracced_user WITH PASSWORD '<DEIN_DB_PASSWORT>';"
sudo -u postgres createdb -O tracced_user tracced_db
```

### 5. Ersten Benutzer anlegen
```bash
cd /home/tracced/backend
python3 -m app.cli create-user --email <DEINE_EMAIL> --password "<DEIN_PASSWORT>"
```

### 6. Service starten
```bash
sudo systemctl enable --now tracced
sudo systemctl status tracced --no-pager
```

### 7. Reverse-Proxy einrichten
Im Nginx Proxy Manager einen Proxy-Host anlegen:

| Einstellung | Wert |
|-------------|------|
| Domain | `<DEINE_DOMAIN.de>` |
| Ziel | `http://<BRIDGE-IP-DES-HOSTS>:8000` |
| Scheme | `http` |
| SSL | Zertifikat über Nginx Proxy Manager |
| Websockets support | Aktivieren (empfohlen) |

> **Hinweis für Docker:** Wenn der Proxy-Manager in einem Container läuft, ist `127.0.0.1` aus Container-Sicht nicht der VPS-Host. Verwende stattdessen die Docker-Bridge-IP des Hosts (herauszufinden mit `ip addr show \| grep "inet 172"` auf dem VPS, z. B. `172.20.0.1`).

---

## Konfiguration

| Variable | Bedeutung | Standard |
|----------|-----------|----------|
| `DATABASE_URL` | SQLAlchemy-Verbindungs-URL | lokale PostgreSQL-Datenbank |
| `SECRET_KEY` | Schlüssel für Session-Token | zufällig generieren |
| `SESSION_EXPIRE_DAYS` | Gültigkeit der Sitzung in Tagen | `30` |
| `SECURE_COOKIES` | Cookies nur über HTTPS | `true` (Produktion) |
| `COOKIE_SAMESITE` | SameSite-Attribut (`lax` oder `strict`) | `lax` |
| `ALLOWED_ORIGINS` | Erlaubte CORS-Origins | deine Domain |
| `HOST` | Bind-Adresse | `0.0.0.0` |
| `PORT` | Port | `8000` |
| `DEBUG` | Ausführliches SQL-Logging | `false` |
| `APP_ENV` | Laufzeitumgebung | `production` |

---

## Betrieb & Wartung

```bash
sudo systemctl status tracced        # Dienststatus prüfen
sudo systemctl restart tracced       # Dienst neu starten
sudo journalctl -u tracced -f        # Live-Logs anzeigen
```

### Datenbank-Migrationen
Beim Start werden fehlende Datenbankspalten automatisch ergänzt. Bestehende Daten bleiben erhalten – manuelle Migrationen sind nicht erforderlich.

---

## API

Alle Endpunkte liegen unter `/api/v1`. Die interaktive API-Dokumentation ist unter `/docs` erreichbar (während des Betriebs).

---

## Lizenz & Mitwirkung

Tracced ist ein Open-Source-Projekt. Pull Requests und Issues sind willkommen. Weitere Details zur Lizenz und zum Beitrag finden sich im Repository.

---

Erstelle deinen ersten Zählerstand unter `https://<DEINE_DOMAIN.de>` – keine öffentliche Registrierung, Benutzer werden über die Server-CLI angelegt.
