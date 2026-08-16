#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
    echo "Bitte mit sudo ausführen: sudo $0" >&2
    exit 1
fi

UUID="B483-A120"
ZIEL="/mnt/usb-backups"
FSTAB_ZEILE="UUID=${UUID} ${ZIEL} vfat defaults,nofail,x-systemd.device-timeout=10,uid=1000,gid=1000,umask=0077 0 0"

mkdir -p "${ZIEL}"
if ! grep -qE "^[^#]*UUID=${UUID}[[:space:]]" /etc/fstab; then
    printf '%s\n' "${FSTAB_ZEILE}" >> /etc/fstab
fi

systemctl daemon-reload
if findmnt -rn -S "UUID=${UUID}" >/dev/null; then
    umount "$(findmnt -rn -S "UUID=${UUID}" -o TARGET | head -n 1)"
fi
mount "${ZIEL}"
chown 1000:1000 "${ZIEL}"
chmod 0700 "${ZIEL}"
findmnt "${ZIEL}"

