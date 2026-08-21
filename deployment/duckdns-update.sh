#!/bin/bash
# DuckDNS-Updater fuer ffrattenberg + ffrattenbergcloud.
#
# Bewusst auf ZWEI Rechnern installiert (ThinkPad + felferlinuxlab), die
# beide im Veranstaltungs-WLAN haengen: faellt einer aus oder ist gerade
# nicht am Netz, aktualisiert der andere trotzdem weiter. Doppelte Updates
# schaden nicht - DuckDNS ist idempotent.
#
# Der Parameter ip= bleibt LEER: DuckDNS traegt dann die oeffentliche IP
# ein, von der die Anfrage kommt. Deshalb darf dieses Skript NUR auf
# Geraeten im Veranstaltungsnetz laufen - von auswaerts wuerde es die
# falsche Adresse eintragen.
#
# Installation (Cron): jede Minute + einmal beim Systemstart, siehe
# deployment/duckdns-installieren.sh
set -u

# Geheimwert niemals in diesem Skript oder in Logs speichern. Der Aufrufer
# muss DUCKDNS_TOKEN in der Prozessumgebung setzen (z.B. systemd-Credential
# oder geschützte Service-Umgebung außerhalb des Repositories).
if [ -z "${DUCKDNS_TOKEN:-}" ]; then
    printf '%s\n' "DUCKDNS_TOKEN fehlt in der Umgebung." >&2
    exit 1
fi
DOMAINS="ffrattenberg,ffrattenbergcloud"
LOG="$HOME/duckdns.log"

# verbose=true liefert "OK <ip> <status>" statt nur "OK" - damit steht die
# tatsaechlich eingetragene IP im Log und man muss sie im Fehlerfall nicht
# ueber einen externen Dienst nachschlagen.
antwort=$(curl -s --max-time 20 \
  "https://www.duckdns.org/update?domains=${DOMAINS}&token=${DUCKDNS_TOKEN}&ip=&verbose=true" \
  | tr '\n' ' ' | sed 's/  */ /g; s/ *$//')

printf '%s %s\n' "$(date '+%F %T')" "${antwort:-KEINE-ANTWORT-TIMEOUT}" >> "$LOG"

# Log nicht unbegrenzt wachsen lassen (jede Minute = ~1440 Zeilen/Tag).
if [ "$(wc -l < "$LOG" 2>/dev/null || echo 0)" -gt 3000 ]; then
    tail -n 500 "$LOG" > "${LOG}.neu" && mv "${LOG}.neu" "$LOG"
fi
