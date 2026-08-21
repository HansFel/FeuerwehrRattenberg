#!/bin/bash
# Installiert die Zeitmessungs-App als systemd-Benutzerdienst auf dem
# Zeitnehmungs-PC. Das Skript darf aus einem beliebigen Verzeichnis gestartet
# werden; Repository und virtuelle Umgebung werden daraus automatisch erkannt.
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PYTHON="$SCRIPT_DIR/.venv/bin/python"
SERVICE_DIR="$HOME/.config/systemd/user"
SERVICE_FILE="$SERVICE_DIR/zeitmessung-desktop.service"

if [ ! -x "$PYTHON" ]; then
    printf '%s\n' "Fehler: $PYTHON fehlt." >&2
    printf '%s\n' "Zuerst im Ordner desktop-app ausführen:" >&2
    printf '%s\n' "  python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'" >&2
    exit 1
fi

mkdir -p "$SERVICE_DIR"
cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Feuerwehr Rattenberg Zeitmessung
After=graphical-session.target network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$SCRIPT_DIR
ExecStart=$PYTHON -m zeitmessung_desktop
Restart=on-failure
RestartSec=3
Environment=DISPLAY=:0

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now zeitmessung-desktop.service

printf '%s\n' "Zeitmessung-Autostart ist eingerichtet."
printf '%s\n' "Status: systemctl --user status zeitmessung-desktop.service"
printf '%s\n' "Log:    journalctl --user -u zeitmessung-desktop.service -f"
