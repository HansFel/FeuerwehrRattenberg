#!/usr/bin/env bash
set -euo pipefail

EXPECTED_HOST="hans-ThinkPad-E590"
CONNECTION_UUID="30b948af-ed8b-4548-9d44-eccc62cd0add"
STATIC_ADDRESS="192.168.1.34/24"
GATEWAY="192.168.1.1"
DNS_SERVER="192.168.1.1"

if [[ "$(hostname)" != "$EXPECTED_HOST" ]]; then
  echo "Fehler: Dieses Skript darf nur auf $EXPECTED_HOST laufen." >&2
  exit 1
fi

if [[ "${EUID}" -ne 0 ]]; then
  echo "Fehler: Bitte mit sudo ausfuehren." >&2
  exit 1
fi

nmcli connection show "$CONNECTION_UUID" >/dev/null

echo "Setze die feste Adresse $STATIC_ADDRESS ..."
nmcli connection modify "$CONNECTION_UUID" \
  ipv4.method manual \
  ipv4.addresses "$STATIC_ADDRESS" \
  ipv4.gateway "$GATEWAY" \
  ipv4.dns "$DNS_SERVER" \
  ipv4.ignore-auto-dns yes

echo "Aktiviere die geaenderte WLAN-Verbindung. Die SSH-Verbindung kann kurz abbrechen."
nmcli connection up "$CONNECTION_UUID"

echo
echo "Aktive IPv4-Konfiguration:"
ip -4 address show dev wlp5s0
ip -4 route
