#!/bin/bash
# Auf dem Backup-Server mit sudo ausführen, wenn der aktive ThinkPad sicher
# ausgefallen ist. Ändert ausschließlich die statische LAN-IP .35 -> .34.
set -euo pipefail

ALT_IP="192.168.1.35"
FAILOVER_IP="192.168.1.34"
NETPLAN="/etc/netplan/00-installer-config.yaml"
ECHTER_BENUTZER="${SUDO_USER:-hans}"
MARKER="/home/$ECHTER_BENUTZER/FAILOVER_ACTIVE"

if [ "${EUID:-$(id -u)}" -ne 0 ]; then
    echo "Bitte mit sudo ausführen: sudo $0" >&2
    exit 1
fi
if ping -c 2 -W 1 "$FAILOVER_IP" >/dev/null 2>&1; then
    echo "ABBRUCH: $FAILOVER_IP antwortet noch. Aktiven Server zuerst sicher abschalten." >&2
    exit 1
fi
if [ ! -f "$NETPLAN" ]; then
    echo "ABBRUCH: $NETPLAN fehlt." >&2
    exit 1
fi
if ! grep -q "$ALT_IP/24" "$NETPLAN"; then
    echo "ABBRUCH: Erwartete Backup-IP $ALT_IP/24 nicht in $NETPLAN gefunden." >&2
    exit 1
fi

touch "$MARKER"
chown "$ECHTER_BENUTZER:$ECHTER_BENUTZER" "$MARKER"
cp -a "$NETPLAN" "$NETPLAN.vor-failover-$(date +%Y%m%d_%H%M%S)"
sed -i "s/$ALT_IP\/24/$FAILOVER_IP\/24/g" "$NETPLAN"

echo "Failover wird aktiviert. Die SSH-Verbindung auf $ALT_IP bricht gleich ab."
echo "Danach über Tailscale oder $FAILOVER_IP neu verbinden."
netplan apply
