#!/bin/bash
#===============================================================================
# Tracced – Interaktives Installationsskript
# Führe dieses Skript aus dem Projektordner (tracced/) aus.
#===============================================================================
set -euo pipefail

# Farben
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Tracced – Interaktive Installation   ${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

#-------------------------------------------------------------------------------
# 1. Projektordner / Installationspfad ermitteln
#-------------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

read -rp "Installationspfad [${SCRIPT_DIR}]: " INSTALL_DIR
INSTALL_DIR="${INSTALL_DIR:-${SCRIPT_DIR}}"

# Falls ein anderer Pfad angegeben wurde: Dateien dorthin kopieren
if [[ "${INSTALL_DIR}" != "${SCRIPT_DIR}" ]]; then
    echo -e "${YELLOW}Kopiere Projektdateien nach ${INSTALL_DIR} ...${NC}"
    sudo mkdir -p "${INSTALL_DIR}"
    sudo cp -a "${SCRIPT_DIR}/." "${INSTALL_DIR}/"
    sudo chown -R "$USER":"$USER" "${INSTALL_DIR}"
    cd "${INSTALL_DIR}"
else
    cd "${SCRIPT_DIR}"
fi

echo -e "${GREEN}Installationspfad: ${INSTALL_DIR}${NC}"
echo ""

#-------------------------------------------------------------------------------
# 2. Interaktive Abfragen
#-------------------------------------------------------------------------------
read -rp "Domain (z.B. tracced.deine-domain.de): " DOMAIN
read -rp "E-Mail für ersten Benutzer: " ADMIN_EMAIL
read -rsp "Passwort für ersten Benutzer: " ADMIN_PASSWORD
echo ""
read -rsp "Datenbank-Passwort für tracced_user: " DB_PASSWORD
echo ""
read -rp "Backend-Port [8000]: " BACKEND_PORT
BACKEND_PORT="${BACKEND_PORT:-8000}"
read -rp "systemd-User [$USER]: " SYSTEMD_USER
SYSTEMD_USER="${SYSTEMD_USER:-$USER}"

# SECRET_KEY automatisch erzeugen
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))" 2>/dev/null \
    || head -c 32 /dev/urandom | base64 | tr -d '\n')

echo ""
echo -e "${BLUE}Zusammenfassung:${NC}"
echo "  Installationspfad : ${INSTALL_DIR}"
echo "  Domain            : ${DOMAIN}"
echo "  E-Mail            : ${ADMIN_EMAIL}"
echo "  Backend-Port      : ${BACKEND_PORT}"
echo "  systemd-User      : ${SYSTEMD_USER}"
echo "  SECRET_KEY        : ${SECRET_KEY}"
echo ""

read -rp "Fortfahren mit der Installation? (y/N): " CONFIRM
if [[ ! "${CONFIRM}" =~ ^[Yy]$ ]]; then
    echo -e "${RED}Abbruch durch Nutzer.${NC}"
    exit 1
fi

#-------------------------------------------------------------------------------
# 3. Systempakete installieren
#-------------------------------------------------------------------------------
echo -e "${BLUE}>> Installiere Systempakete ...${NC}"
sudo apt update
sudo apt install -y python3 python3-pip postgresql postgresql-client git curl

#-------------------------------------------------------------------------------
# 4. Backend-Konfiguration (.env)
#-------------------------------------------------------------------------------
echo -e "${BLUE}>> Schreibe backend/.env ...${NC}"
cat > backend/.env <<EOF
DATABASE_URL=postgresql+asyncpg://tracced_user:${DB_PASSWORD}@127.0.0.1:5432/tracced_db
SECRET_KEY=${SECRET_KEY}
APP_ENV=production
DEBUG=false
HOST=0.0.0.0
PORT=${BACKEND_PORT}
ALLOWED_ORIGINS=https://${DOMAIN}
SECURE_COOKIES=true
EOF

chmod 600 backend/.env

#-------------------------------------------------------------------------------
# 5. Python-Abhängigkeiten installieren (ohne venv)
#-------------------------------------------------------------------------------
echo -e "${BLUE}>> Installiere Python-Abhängigkeiten ...${NC}"
cd backend
pip3 install --break-system-packages --ignore-installed -r requirements.txt
cd ..

#-------------------------------------------------------------------------------
# 6. PostgreSQL-Authentifizierung konfigurieren (pg_hba.conf)
#-------------------------------------------------------------------------------
echo -e "${BLUE}>> Konfiguriere PostgreSQL-Authentifizierung ...${NC}"

# PostgreSQL sicherstellen
sudo systemctl enable --now postgresql

# pg_hba.conf finden
PG_HBA=$(sudo find /etc/postgresql -name "pg_hba.conf" 2>/dev/null | head -1)
if [[ -z "${PG_HBA}" ]]; then
    echo -e "${RED}pg_hba.conf nicht gefunden!${NC}"
    exit 1
fi

# Backup erstellen
sudo cp "${PG_HBA}" "${PG_HBA}.bak.tracced"

# Bestehende Einträge für 127.0.0.1/32 und ::1/128 entfernen (werden von oben nach unten ausgewertet)
sudo sed -i '/127\.0\.0\.1\/32/d' "${PG_HBA}"
sudo sed -i '/::1\/128/d' "${PG_HBA}"

# Neuen Eintrag an den Anfang der Datei (nach Kommentaren/Leerzeilen) einfügen
# Damit hat er Vorrang vor allen späteren Regeln (z.B. peer)
sudo sed -i '1i host    all             all             127.0.0.1/32            scram-sha-256' "${PG_HBA}"
sudo sed -i '1i host    all             all             ::1/128                 scram-sha-256' "${PG_HBA}"

sudo systemctl reload postgresql
echo -e "${GREEN}   PostgreSQL aktiv und neu geladen.${NC}"

#-------------------------------------------------------------------------------
# 7. Bestehende Benutzer/Datenbank prüfen
#-------------------------------------------------------------------------------
echo -e "${BLUE}>> Prüfe bestehende PostgreSQL-Benutzer und Datenbank ...${NC}"

USER_EXISTS=$(sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='tracced_user'" 2>/dev/null || echo "")
DB_EXISTS=$(sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='tracced_db'" 2>/dev/null || echo "")

if [[ -n "${USER_EXISTS}" || -n "${DB_EXISTS}" ]]; then
    echo -e "${YELLOW}Achtung: Es existieren bereits:${NC}"
    [[ -n "${USER_EXISTS}" ]] && echo "  - Benutzer 'tracced_user'"
    [[ -n "${DB_EXISTS}" ]] && echo "  - Datenbank 'tracced_db'"
    echo ""
    read -rp "Sollen bestehende Benutzer/Datenbank entfernt und neu angelegt werden? (y/N): " RECREATE_DB
    if [[ "${RECREATE_DB}" =~ ^[Yy]$ ]]; then
        sudo -u postgres psql -c "DROP DATABASE IF EXISTS tracced_db;" 2>/dev/null || true
        sudo -u postgres psql -c "DROP ROLE IF EXISTS tracced_user;" 2>/dev/null || true
        echo -e "${GREEN}   Bestehende Objekte entfernt.${NC}"
    else
        echo -e "${YELLOW}   Bestehende Objekte werden beibehalten.${NC}"
    fi
fi

#-------------------------------------------------------------------------------
# 8. PostgreSQL-Benutzer & -Datenbank anlegen
#-------------------------------------------------------------------------------
echo -e "${BLUE}>> Lege PostgreSQL-Benutzer und Datenbank an ...${NC}"
sudo -u postgres psql -c "CREATE USER tracced_user WITH PASSWORD '${DB_PASSWORD}';" 2>/dev/null || \
    sudo -u postgres psql -c "ALTER USER tracced_user WITH PASSWORD '${DB_PASSWORD}';"
sudo -u postgres createdb -O tracced_user tracced_db 2>/dev/null || \
    sudo -u postgres psql -c "ALTER DATABASE tracced_db OWNER TO tracced_user;"
echo -e "${GREEN}   Benutzer und Datenbank bereit.${NC}"

#-------------------------------------------------------------------------------
# 9. systemd-Service einrichten
#-------------------------------------------------------------------------------
echo -e "${BLUE}>> Richte systemd-Service ein ...${NC}"

# Pfad zu uvicorn ermitteln (systemweite Installation ohne venv)
UVICORN_PATH=$(which uvicorn 2>/dev/null || echo "uvicorn")

# Service-Vorlage anpassen: Pfad, User, Group, WorkingDirectory, venv/bin/ entfernen, uvicorn-Pfad setzen, Host auf 0.0.0.0, ProtectHome entfernen
sudo sed -i \
    -e "s|/var/www/tracced|${INSTALL_DIR}|g" \
    -e "s|User=www-data|User=${SYSTEMD_USER}|g" \
    -e "s|Group=www-data|Group=${SYSTEMD_USER}|g" \
    -e "s|WorkingDirectory=.*|WorkingDirectory=${INSTALL_DIR}/backend|g" \
    -e "s|venv/bin/||g" \
    -e "s|--host 127.0.0.1|--host 0.0.0.0|g" \
    -e "s|ExecStart=.*uvicorn|ExecStart=${UVICORN_PATH} uvicorn|g" \
    -e "/ProtectHome=true/d" \
    deploy/systemd/tracced.service

sudo cp deploy/systemd/tracced.service /etc/systemd/system/tracced.service
sudo systemctl daemon-reload
sudo systemctl enable --now tracced

echo -e "${GREEN}   systemd-Service 'tracced' ist aktiv und läuft.${NC}"

#-------------------------------------------------------------------------------
# 10. Ersten Benutzer anlegen
#-------------------------------------------------------------------------------
echo -e "${BLUE}>> Lege ersten Benutzer an ...${NC}"
cd backend
python3 -m app.cli create-user --email "${ADMIN_EMAIL}" --password "${ADMIN_PASSWORD}"
cd ..

#-------------------------------------------------------------------------------
# 11. Fertig
#-------------------------------------------------------------------------------
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Installation abgeschlossen!            ${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "Backend läuft unter:  http://0.0.0.0:${BACKEND_PORT} (alle Interfaces)"
echo -e "Aufruf im Browser:    https://${DOMAIN}"
echo -e "Login-E-Mail:         ${ADMIN_EMAIL}"
echo ""
echo -e "${YELLOW}WICHTIG – Nginx Proxy Manager (NPM) in Docker:${NC}"
echo "  Da NPM in einem Docker-Container läuft, ist '127.0.0.1' aus"
echo "  Container-Sicht NICHT der VPS-Host. Trage stattdessen die"
echo "  Docker-Bridge-IP des Hosts als Ziel im NPM-Proxy-Host ein."
echo ""
echo "  1. Bridge-IP herausfinden (auf dem VPS-Host):"
echo "     ip addr show | grep 'inet 172'"
echo "     (z. B. 172.20.0.1, 172.17.0.1, 172.19.0.1 …)"
echo ""
echo "  2. Im Nginx Proxy Manager einen Proxy-Host anlegen:"
echo "     Domain     : ${DOMAIN}"
echo "     Ziel       : http://<BRIDGE-IP-DES-HOSTS>:${BACKEND_PORT}"
echo "     Scheme     : http"
echo "     SSL        : Zertifikat über Nginx Proxy Manager"
echo "     Websockets : aktivieren (empfohlen)"
echo ""
echo "  Beispiel:  http://172.20.0.1:8000"
echo ""
echo -e "${BLUE}Service-Befehle:${NC}"
echo "  sudo systemctl status tracced   # Status prüfen"
echo "  sudo systemctl restart tracced  # Neustart"
echo "  sudo journalctl -u tracced -f   # Logs verfolgen"
echo ""
