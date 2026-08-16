#!/usr/bin/env bash
# Richtet auf dem ThinkPad (aktiver Server) einen lokalen DNS-Server ein, der
# ffrattenberg.duckdns.org im Veranstaltungs-WLAN direkt auf die lokale IP
# aufloest, statt ueber die oeffentliche IP (Hairpin-NAT des Routers ist
# unzuverlaessig - siehe AGENTS.md, betrifft nachweislich auch normale
# Handy-Browser, nicht nur das ESP32). Alle anderen Domains werden normal
# an echte DNS-Server weitergereicht - kein Eingriff in sonstigen Traffic.
#
# Danach im Router-Admin-Interface den DHCP-DNS-Server fuer das WLAN auf
# 192.168.1.34 umstellen, damit ALLE Geraete im WLAN automatisch diesen
# lokalen DNS bekommen (siehe Ausgabe am Ende dieses Skripts).
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
    echo "Bitte mit sudo ausfuehren: sudo $0" >&2
    exit 1
fi

WLAN_INTERFACE="wlp5s0"
LOKALE_IP="192.168.1.34"
DOMAIN="ffrattenberg.duckdns.org"

apt-get update
apt-get install -y dnsmasq

install -d -m 0755 /etc/dnsmasq.d
install -m 0644 /dev/stdin /etc/dnsmasq.d/ffrattenberg-split-horizon.conf <<EOF
# Split-Horizon-DNS fuers Veranstaltungs-WLAN (siehe AGENTS.md).
interface=${WLAN_INTERFACE}
bind-interfaces
no-resolv
server=1.1.1.1
server=9.9.9.9
address=/${DOMAIN}/${LOKALE_IP}
EOF

systemctl enable --now dnsmasq
systemctl restart dnsmasq

echo ""
echo "=== Test ==="
getent hosts "${DOMAIN}" || true
if command -v dig >/dev/null; then
    dig @"${LOKALE_IP}" "${DOMAIN}" +short
fi

echo ""
echo "=== Naechster Schritt (im Router-Admin-Interface) ==="
echo "DHCP-DNS-Server fuer das WLAN auf ${LOKALE_IP} umstellen, damit ALLE"
echo "Geraete im Veranstaltungs-WLAN automatisch diesen lokalen DNS nutzen."
echo "Ohne diesen Schritt wirkt der lokale DNS nur fuer Geraete, die ihn"
echo "manuell in den WLAN-Einstellungen eintragen."
