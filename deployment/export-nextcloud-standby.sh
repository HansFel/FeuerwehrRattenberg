#!/usr/bin/env bash
set -euo pipefail

if [[ "$(hostname)" != "ffrattenberg" ]]; then
  echo "Fehler: Dieses Skript darf nur auf dem aktiven Server 'ffrattenberg' laufen." >&2
  exit 1
fi

TARGET_USER="${SUDO_USER:-hans}"
TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
TARGET_DIR="$TARGET_HOME/backups/nextcloud-standby"
STAMP="$(date +%Y%m%d-%H%M%S)"

echo "Nextcloud wird fuer den konsistenten Export kurz in den Wartungsmodus versetzt."
echo "Exportiere Apps, Datenbank, Konfiguration und Dateien ..."

mkdir -p "$TARGET_DIR"
nextcloud.export

EXPORT_DIR="$(find /var/snap/nextcloud/common/backups -mindepth 1 -maxdepth 1 -type d -printf '%T@ %p\n' | sort -nr | head -n1 | cut -d' ' -f2-)"
if [[ -z "$EXPORT_DIR" || ! -d "$EXPORT_DIR" ]]; then
  echo "Fehler: Der Nextcloud-Exportordner wurde nicht gefunden." >&2
  exit 1
fi

ARCHIVE="$TARGET_DIR/ffrattenberg-nextcloud-$STAMP.tar.gz"
tar czf "$ARCHIVE" -C "$(dirname "$EXPORT_DIR")" "$(basename "$EXPORT_DIR")"
chown -R "$TARGET_USER:$TARGET_USER" "$TARGET_DIR"
sha256sum "$ARCHIVE" > "$ARCHIVE.sha256"
chown "$TARGET_USER:$TARGET_USER" "$ARCHIVE.sha256"

echo
echo "Export erfolgreich:"
ls -lh "$ARCHIVE" "$ARCHIVE.sha256"
echo "Der normale Nextcloud-Betrieb wurde wieder aktiviert."
