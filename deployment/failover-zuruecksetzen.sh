#!/bin/bash
# Setzt den Backup-Server nach beendetem Failover wieder auf .35 zurück.
set -euo pipefail

FAILOVER_IP="192.168.1.34"
BACKUP_IP="192.168.1.35"
NETPLAN="/etc/netplan/00-installer-config.yaml"
ECHTER_BENUTZER="${SUDO_USER:-hans}"
MARKER="/home/$ECHTER_BENUTZER/FAILOVER_ACTIVE"

if [ "${EUID:-$(id -u)}" -ne 0 ]; then
    echo "Bitte mit sudo ausführen: sudo $0" >&2
    exit 1
fi
if ! grep -q "$FAILOVER_IP/24" "$NETPLAN"; then
    echo "ABBRUCH: Erwartete Failover-IP $FAILOVER_IP/24 nicht gefunden." >&2
    exit 1
fi

cp -a "$NETPLAN" "$NETPLAN.vor-ruecksetzen-$(date +%Y%m%d_%H%M%S)"
sed -i "s/$FAILOVER_IP\/24/$BACKUP_IP\/24/g" "$NETPLAN"
rm -f "$MARKER"
echo "Backup-IP wird auf $BACKUP_IP zurückgesetzt."
netplan apply
