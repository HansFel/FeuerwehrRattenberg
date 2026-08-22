#!/bin/bash
# Läuft auf dem Backup-Server und spiegelt die vier PostgreSQL-Datenbanken
# vom aktiven ThinkPad. Der aktive Server wird dabei nur per pg_dump gelesen.
set -euo pipefail

AKTIV_HOST="100.119.59.86"
SSH_KEY="$HOME/.ssh/id_ed25519_failover_sync"
REPO="$HOME/apps/FeuerwehrRattenberg"
BACKUP_ROOT="$HOME/backups/failover-sync"
FAILOVER_MARKER="$HOME/FAILOVER_ACTIVE"
LOCK_DATEI="$HOME/.failover-sync.lock"
INSTANZEN=(ffrattenberg ffrattenberg-test1 ffrattenberg-test2 ffrattenberg-generalprobe)

exec 9>"$LOCK_DATEI"
flock -n 9 || exit 0

if [ -e "$FAILOVER_MARKER" ]; then
    echo "$(date -Is) Failover aktiv – Synchronisierung bewusst ausgesetzt."
    exit 0
fi

mkdir -p "$BACKUP_ROOT"
zeitstempel=$(date +%Y%m%d_%H%M%S)
tmp=$(mktemp -d "$BACKUP_ROOT/.eingang-XXXXXX")
trap 'rm -rf "$tmp"' EXIT

ssh_aktiv=(ssh -o BatchMode=yes -o IdentitiesOnly=yes -o ConnectTimeout=10
           -i "$SSH_KEY" "hans@$AKTIV_HOST")

# Erst ALLE Dumps vollständig holen und prüfen. Bei einem Netz-/Dumpfehler
# bleibt der laufende Backup-Datenstand dadurch vollständig unverändert.
for instanz in "${INSTANZEN[@]}"; do
    container="db-$instanz"
    "${ssh_aktiv[@]}" "docker exec '$container' pg_dump -U silo_user -d wettbewerb" \
        | gzip -1 > "$tmp/$instanz.sql.gz"
    gzip -t "$tmp/$instanz.sql.gz"
    [ "$(stat -c %s "$tmp/$instanz.sql.gz")" -gt 1024 ]
done

apps=(app-ffrattenberg app-ffrattenberg-test1 app-ffrattenberg-test2
      app-ffrattenberg-generalprobe)
apps_gestoppt=0
apps_starten() {
    if [ "$apps_gestoppt" -eq 1 ]; then
        docker start "${apps[@]}" >/dev/null 2>&1 || true
    fi
}
trap 'apps_starten; rm -rf "$tmp"' EXIT

# Nur der Backup-Stack wird für die kurze Restore-Phase angehalten.
docker stop "${apps[@]}" >/dev/null
apps_gestoppt=1

for instanz in "${INSTANZEN[@]}"; do
    container="db-$instanz"
    docker exec "$container" psql -v ON_ERROR_STOP=1 -U silo_user -d wettbewerb \
        -c 'DROP SCHEMA public CASCADE; CREATE SCHEMA public;' >/dev/null
    gzip -dc "$tmp/$instanz.sql.gz" | \
        docker exec -i "$container" psql -v ON_ERROR_STOP=1 \
            -U silo_user -d wettbewerb >/dev/null

    ziel="$BACKUP_ROOT/$instanz"
    mkdir -p "$ziel"
    cp "$tmp/$instanz.sql.gz" "$ziel/${instanz}_sicherung_${zeitstempel}.sql.gz"
    sha256sum "$ziel/${instanz}_sicherung_${zeitstempel}.sql.gz" \
        > "$ziel/${instanz}_sicherung_${zeitstempel}.sql.gz.sha256"
    # 288 Stände = mindestens 24 Stunden bei fünfminütiger Synchronisierung.
    mapfile -t alte < <(find "$ziel" -maxdepth 1 -type f -name '*.sql.gz' \
        -printf '%T@ %p\n' | sort -rn | tail -n +289 | cut -d' ' -f2-)
    for datei in "${alte[@]}"; do
        rm -f -- "$datei" "$datei.sha256"
    done
done

docker start "${apps[@]}" >/dev/null
apps_gestoppt=0
printf '%s\n' "$zeitstempel" > "$BACKUP_ROOT/LETZTE_ERFOLGREICHE_SYNCHRONISIERUNG"
echo "$(date -Is) Datenbanken erfolgreich synchronisiert: $zeitstempel"
