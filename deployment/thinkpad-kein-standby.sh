#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
    echo "Bitte mit sudo ausfuehren: sudo $0" >&2
    exit 1
fi

install -d -m 0755 /etc/systemd/logind.conf.d
install -m 0644 /dev/stdin /etc/systemd/logind.conf.d/99-server-kein-standby.conf <<'EOF'
[Login]
HandleLidSwitch=ignore
HandleLidSwitchExternalPower=ignore
HandleLidSwitchDocked=ignore
IdleAction=ignore
EOF

systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
systemctl restart systemd-logind

echo "Suspend, Hibernate, Hybrid-Sleep und Deckelaktion sind systemweit deaktiviert."
systemctl is-enabled sleep.target suspend.target hibernate.target hybrid-sleep.target
