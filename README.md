# Tracced – Einrichtung & Bedienung

Tracced ist eine selbst gehostete Webanwendung zum Erfassen, Synchronisieren, Visualisieren und Prognostizieren von Messreihen – zum Beispiel Zählerstände (Strom, Wasser, Gas, Kilometer), Verbräuche oder persönliche Messwerte wie Gewicht oder Temperatur.

Dieses Dokument führt dich durch das erste Setup auf einem Ubuntu VPS (Beispiel: Hetzner) und fasst danach die wichtigsten Konfigurations- und Betriebsinformationen zusammen.

---

## 1. Voraussetzungen

- Ubuntu-Server (z. B. Hetzner VPS)
- Nginx und Nginx Proxy Manager sind bereits installiert und erreichbar
- SSL-Zertifikate werden über den Nginx Proxy Manager verwaltet (keine Certbot-Befehle nötig)
- PostgreSQL-Datenbank ist verfügbar oder kann lokal installiert werden

> Erstelle den Projektordner am gewünschten Ort (Beispiel: `/home/tracced`) bevor du mit Schritt 2 beginnst.

---

## 2. Installation (nur Befehle)

### 2.1 Projekt klonen

```bash
git clone <DEIN_GIT_REPO> /home/tracced && cd /home/tracced
```

### 2.2 Konfiguration (.env) anpassen

Die Konfigurationsdatei liegt bereits unter `backend/.env`. Öffne sie und trage deine Werte ein:

```ini
DATABASE_URL=postgresql+asyncpg://tracced_user:<DEIN_DB_PASSWORT>@127.0.0.1:5432/tracced_db
SECRET_KEY=<DEIN_SECRETER_KEY>
APP_ENV=production
DEBUG=false
HOST=0.0.0.0
PORT=8000
ALLOWED_ORIGINS=https://<DEINE_DOMAIN.de>
SECURE_COOKIES=true
```

SECRET_KEY erzeugen:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Dann Berechtigungen setzen und Python-Pakete installieren:

```bash
cd /home/tracced/backend && chmod 600 .env && pip3 install --break-system-packages --ignore-installed -r requirements.txt
```

> Hinweis: Unter aktuellen Ubuntu/Debian-Versionen ist Python extern verwaltet (PEP 668). Deshalb werden `--break-system-packages` und `--ignore-installed` benötigt, wenn keine virtuelle Umgebung verwendet werden soll. `--ignore-installed` verhindert, dass pip versucht, von Debian vorinstallierte Pakete zu deinstallieren (diese haben keine RECORD-Datei). Ein `pip3 install --upgrade pip` wird nicht empfohlen.

### 2.3 Datenbank anlegen

```bash
sudo -u postgres psql -c "CREATE USER tracced_user WITH PASSWORD '<DEIN_DB_PASSWORT>';"
sudo -u postgres createdb -O tracced_user tracced_db
```

### 2.4 systemd-Service einrichten & starten

```bash
sudo sed -i "s|/var/www/tracced|/home/tracced|g; s|User=www-data|User=$USER|g; s|Group=www-data|Group=$USER|g; s|venv/bin/||g; s|--host 127.0.0.1|--host 0.0.0.0|g; /ProtectHome=true/d" deploy/systemd/tracced.service
sudo cp deploy/systemd/tracced.service /etc/systemd/system/tracced.service
sudo systemctl daemon-reload && sudo systemctl enable --now tracced
```

Status prüfen:

```bash
sudo systemctl status tracced --no-pager
```

### 2.5 Ersten Benutzer anlegen

```bash
cd /home/tracced/backend && python3 -m app.cli create-user --email <DEINE_EMAIL> --password "<DEIN_PASSWORT>"
```

### 2.6 Nginx Proxy Manager einrichten

In der Nginx Proxy Manager-Oberfläche einen Proxy-Host anlegen:

| Einstellung | Wert |
|-------------|------|
| Domain | `<DEINE_DOMAIN.de>` |
| Ziel | `http://<BRIDGE-IP-DES-HOSTS>:8000` |
| Scheme | `http` |
| SSL | Zertifikat über Nginx Proxy Manager ausstellen / verknüpfen |
| Websockets support | Aktivieren (empfohlen) |

> **Wichtig bei Docker:** Wenn der Nginx Proxy Manager in einem Docker-Container läuft, ist `127.0.0.1` aus Container-Sicht der Container selbst, **nicht** der VPS-Host. Trage stattdessen die Docker-Bridge-IP des VPS-Hosts ein.
>
> Bridge-IP auf dem VPS herausfinden:
> ```bash
> ip addr show | grep "inet 172"
> ```
> (z. B. `172.20.0.1`, `172.17.0.1`, `172.19.0.1` …)
>
> Beispiel für das Ziel im NPM: `http://172.20.0.1:8000`

---

## 3. Port abweichen von 8000

Ja, ein anderer Port ist möglich. Du musst den Port an **zwei Stellen** konsistent ändern, damit systemd/Uvicorn und der Nginx Proxy Manager zusammenpassen.

**Beispiel: Port 8080**

### 3.1 `backend/.env` anpassen

```ini
PORT=8080
```

### 3.2 systemd-Service anpassen

In `deploy/systemd/tracced.service` den Port im `ExecStart` ändern:

```ini
ExecStart=uvicorn app.main:app --host 0.0.0.0 --port 8080 --workers 2
```

*(Pfad entsprechend deiner Installation anpassen.)*

### 3.3 systemd neu laden & neu starten

```bash
sudo systemctl daemon-reload && sudo systemctl restart tracced
```

### 3.4 Nginx Proxy Manager anpassen

Im Nginx Proxy Manager das Ziel des Proxy-Hosts auf `<BRIDGE-IP-DES-HOSTS>:8080` ändern (statt `127.0.0.1:8000`). Siehe Hinweis in Schritt 2.6 zu Docker und Bridge-IP.

> Wichtig: Die `PORT`-Variable in der `.env` und der `--port`-Wert im systemd-Service sollten übereinstimmen.

---

## 4. Fertig – Aufruf & Login

Aufruf: `https://<DEINE_DOMAIN.de>`  
Login mit dem Benutzer aus Schritt 2.5.

Es gibt **keine öffentliche Registrierung**. Weitere Benutzer werden nur über die CLI angelegt:

```bash
cd /home/tracced/backend && python3 -m app.cli create-user --email <NEUE_EMAIL> --password "<NEUES_PASSWORT>"
```

---

## 5. Konfiguration

Die Konfiguration erfolgt über `backend/.env` oder Umgebungsvariablen:

| Variable | Bedeutung | Standard |
|----------|-----------|----------|
| `DATABASE_URL` | SQLAlchemy-Verbindungs-URL | lokale PostgreSQL-Datenbank |
| `SECRET_KEY` | Schlüssel für Session-Tokens | unsicherer Entwicklungswert |
| `SESSION_EXPIRE_DAYS` | Gültigkeit der Sitzung in Tagen | `30` |
| `SECURE_COOKIES` | Cookies nur über HTTPS | `false` (Produktion: `true`) |
| `COOKIE_SAMESITE` | SameSite-Attribut (`lax` oder `strict`) | `lax` |
| `ALLOWED_ORIGINS` | Komma-separierte CORS-Origins | lokale Adressen |
| `HOST` | Bind-Adresse | `127.0.0.1` |
| `PORT` | Port | `8000` |
| `DEBUG` | SQL-Logging aktivieren | `false` |
| `APP_ENV` | Laufzeitumgebung | `production` |

Für den Produktivbetrieb unbedingt einen zufälligen `SECRET_KEY` erzeugen und `SECURE_COOKIES=true` setzen.

---

## 6. Funktionen (Überblick)

- **Benutzer & Anmeldung:** Geschlossenes System ohne öffentliche Registrierung, Argon2id-Passwort-Hashing, HttpOnly-Session-Cookies, CSRF-Schutz
- **Messreihen:** Anlegen, Bearbeiten, Löschen; Zählerstände oder diskrete Messungen; Ganzzahl- oder Dezimalmodus
- **Messwerte:** Zeitstempel, Wert, Notiz; chronologische Sortierung
- **Visualisierung:** Dashboard, Detailansicht, interaktives Liniendiagramm (Canvas, ohne externe Bibliothek), PWA
- **Prognosen:** Serverseitig für 30, 60, 90 Tage, 6 Monate und 365 Tage
- **Backup & Wiederherstellung:** JSON-/CSV-Export, Import-Validierung, atomarer Import (Merge oder Replace)
- **Betrieb:** Healthcheck unter `/health`, API-Dokumentation unter `/docs`, automatische Schema-Upgrades beim Start

---

## 7. Betrieb & Wartung

### systemd-Service

```bash
sudo systemctl status tracced        # Status prüfen
sudo systemctl restart tracced       # Neustart nach Änderungen
sudo systemctl disable --now tracced # Dienst stoppen & deaktivieren
```

### Tests

```bash
cd /home/tracced/backend
pip3 install pytest pytest-asyncio httpx  # falls noch nicht installiert
python3 -m pytest -v
```

Die Tests verwenden eine SQLite-In-Memory-Datenbank und benötigen kein PostgreSQL.

### Datenbank-Migrationen

Neue Spalten werden beim Start automatisch über idempotente Schema-Upgrades ergänzt. Bestehende Daten bleiben erhalten. Es ist nicht nötig, Tabellen manuell zu migrieren.

### Logs

```bash
sudo journalctl -u tracced -f
```

---

## 8. Hinweise & Sicherheit

- Geheimnisse (`.env`, Datenbank-Passwörter) niemals ins Repository committen.
- Die Anwendung ist für den Betrieb hinter HTTPS und einem Reverse-Proxy ausgelegt.
- CSRF- und Eigentümerprüfungen sind auf allen schreibenden API-Endpunkten aktiv.
- Lokale SQLite-Dateien, virtuelle Umgebungen und `.env` werden über `.gitignore` ausgeschlossen.
