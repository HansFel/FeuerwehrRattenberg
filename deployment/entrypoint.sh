#!/bin/bash
set -e

echo "=== FF Rattenberg Wettbewerb – Startup ==="
echo "Build: ${COMMIT_HASH:-unknown}"

cd /opt/wettbewerb

# Auf PostgreSQL warten (nur wenn DATABASE_URL gesetzt ist – sonst SQLite lokal)
if [ -n "${DATABASE_URL}" ]; then
    _DB_HOST=$(echo "${DATABASE_URL}" | sed -E 's|.*@([^:/]+).*|\1|')
    _DB_USER=$(echo "${DATABASE_URL}" | sed -E 's|.*://([^:]+):.*|\1|')
    echo "Warte auf Datenbank (${_DB_HOST})..."
    until pg_isready -h "${_DB_HOST}" -p 5432 -U "${_DB_USER}" -q; do
        echo "  DB noch nicht bereit, warte 2s..."
        sleep 2
    done
    echo "DB bereit."
fi

# Tabellen, additive Migration und Standard-Administrator EINMALIG anlegen,
# bevor Gunicorn mehrere Worker-Prozesse startet. Würde create_app() erst
# beim Import durch jeden Worker laufen, entsteht bei einer leeren Postgres-
# Datenbank ein Wettlauf ums CREATE TABLE (mehrere Worker gleichzeitig) und
# der Start scheitert mit "duplicate key ... pg_class_relname_nsp_index".
echo "Initialisiere Datenbank (Tabellen, Administrator)..."
python -c "from app import create_app; create_app()"
echo "Initialisierung abgeschlossen."

echo "=== Starte Gunicorn ==="
exec gunicorn -w 4 -b 0.0.0.0:8000 --timeout 300 "app:create_app()"
