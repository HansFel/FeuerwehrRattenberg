#!/usr/bin/env bash
set -euo pipefail

USB_UUID="B483-A120"
AUFBEWAHREN=288
ZEITSTEMPEL="$(date +%Y%m%d_%H%M%S)"

MOUNTPOINT="$(findmnt -rn -S "UUID=${USB_UUID}" -o TARGET | head -n 1)"
if [[ -z "${MOUNTPOINT}" || ! -w "${MOUNTPOINT}" ]]; then
    echo "USB-Speicher UUID ${USB_UUID} ist nicht schreibbar eingehängt." >&2
    exit 1
fi

ZIEL="${MOUNTPOINT}/ffrattenberg-backups"
mkdir -p "${ZIEL}"

INSTANZEN=(
    "ffrattenberg:db-ffrattenberg"
    "ffrattenberg-generalprobe:db-ffrattenberg-generalprobe"
    "ffrattenberg-test1:db-ffrattenberg-test1"
    "ffrattenberg-test2:db-ffrattenberg-test2"
)

for eintrag in "${INSTANZEN[@]}"; do
    instanz="${eintrag%%:*}"
    container="${eintrag#*:}"
    datei="${ZIEL}/${instanz}_sicherung_${ZEITSTEMPEL}.sql.gz"
    temp="${datei}.part"
    statusdatei="${ZIEL}/.${instanz}_aenderungsstand"

    if [[ "$(docker inspect -f '{{.State.Running}}' "${container}" 2>/dev/null)" != "true" ]]; then
        echo "Datenbank-Container ${container} läuft nicht." >&2
        exit 1
    fi

    # PostgreSQL zählt tatsächliche Änderungen je Datenbank. Abfragen der
    # Anwendung allein lösen damit keine unnötigen Sicherungen aus.
    aenderungsstand="$(docker exec "${container}" sh -c \
        'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc \
        "SELECT tup_inserted || '"'"':'"'"' || tup_updated || '"'"':'"'"' || tup_deleted
         FROM pg_stat_database WHERE datname = current_database()"')"
    letzter_stand="$(cat "${statusdatei}" 2>/dev/null || true)"
    if [[ -n "${letzter_stand}" && "${aenderungsstand}" == "${letzter_stand}" ]]; then
        echo "Unverändert, übersprungen: ${instanz}"
        continue
    fi

    docker exec "${container}" sh -c \
        'exec pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' | gzip -9 > "${temp}"
    gzip -t "${temp}"
    mv "${temp}" "${datei}"
    sha256sum "${datei}" > "${datei}.sha256"
    printf '%s\n' "${aenderungsstand}" > "${statusdatei}"
    echo "Erstellt: ${datei}"

    mapfile -t alt < <(find "${ZIEL}" -maxdepth 1 -type f \
        -name "${instanz}_sicherung_*.sql.gz" -printf '%T@ %p\n' \
        | sort -rn | tail -n "+$((AUFBEWAHREN + 1))" | cut -d' ' -f2-)
    for alte_datei in "${alt[@]}"; do
        rm -f -- "${alte_datei}" "${alte_datei}.sha256"
    done
done
