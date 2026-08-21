#!/bin/bash
# Manueller DuckDNS-Trigger MIT Rueckmeldung im Fenster - fuer den
# Desktop-Button (siehe deployment/duckdns-jetzt.desktop).
#
# Normalfall ist der Cron-Job jede Minute (deployment/duckdns-update.sh);
# dieser Knopf ist fuer den Fall gedacht, dass es vor Ort schnell gehen
# muss und niemand 60 Sekunden warten will - etwa direkt nach einem
# Router-Neustart.
#
# Muss wie der Cron-Job auf einem Geraet IM Veranstaltungsnetz laufen:
# ip= bleibt leer, DuckDNS nimmt die oeffentliche IP der Anfrage.
set -u

if [ -z "${DUCKDNS_TOKEN:-}" ]; then
    zenity --error --width=400 --title="DuckDNS" \
        --text="DUCKDNS_TOKEN fehlt in der Prozessumgebung."
    exit 1
fi
DOMAINS="ffrattenberg,ffrattenbergcloud"
LOG="$HOME/duckdns.log"

antwort=$(curl -s --max-time 20 \
  "https://www.duckdns.org/update?domains=${DOMAINS}&token=${DUCKDNS_TOKEN}&ip=&verbose=true" \
  | tr '\n' ' ' | sed 's/  */ /g; s/ *$//')

printf '%s %s (manuell)\n' "$(date '+%F %T')" "${antwort:-KEINE-ANTWORT-TIMEOUT}" >> "$LOG"

if [ "${antwort%% *}" = "OK" ]; then
    ip=$(printf '%s' "$antwort" | awk '{print $2}')
    zenity --info --width=340 --title="DuckDNS" \
        --text="Adresse erfolgreich eingetragen.\n\nOeffentliche IP:\n<b>${ip}</b>\n\nffrattenberg.duckdns.org\nffrattenbergcloud.duckdns.org"
else
    zenity --error --width=400 --title="DuckDNS" \
        --text="Update FEHLGESCHLAGEN.\n\nAntwort von DuckDNS:\n<tt>${antwort:-keine Antwort (Zeitueberschreitung)}</tt>\n\nInternetverbindung pruefen. Der automatische Versuch laeuft jede Minute weiter."
fi
