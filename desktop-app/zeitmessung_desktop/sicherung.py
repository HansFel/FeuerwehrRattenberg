"""Zyklische Sicherung der lokalen Zeitmessung-Datenbank.

Dateiname MUSS den Instanznamen enthalten (projektübergreifende Konvention
des Users, siehe globale CLAUDE.md: '<instanzname>_sicherung_YYYYMMDD_HHMMSS.<ext>'),
damit bei vielen Apps/Instanzen am Dateinamen allein erkennbar bleibt, wozu
eine Sicherung gehört."""
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable


def sicherung_dateiname(instance_name: str, zeitpunkt: datetime) -> str:
    return f"{instance_name}_sicherung_{zeitpunkt:%Y%m%d_%H%M%S}.sqlite"


def sicherung_durchfuehren(db_pfad: str, ziel_ordner: str, instance_name: str,
                            zeitpunkt: datetime | None = None) -> Path:
    """Erstellt eine konsistente Kopie der (ggf. gerade beschriebenen)
    SQLite-Datenbank über die sqlite3-Backup-API - sicherer als eine reine
    Dateikopie im WAL-Modus, wo eine parallele Schreiboperation sonst eine
    inkonsistente Kopie erzeugen könnte."""
    zeitpunkt = zeitpunkt or datetime.now()
    ziel = Path(ziel_ordner)
    ziel.mkdir(parents=True, exist_ok=True)
    ziel_datei = ziel / sicherung_dateiname(instance_name, zeitpunkt)

    quelle = sqlite3.connect(db_pfad)
    try:
        ziel_verbindung = sqlite3.connect(str(ziel_datei))
        try:
            quelle.backup(ziel_verbindung)
        finally:
            ziel_verbindung.close()
    finally:
        quelle.close()
    return ziel_datei


class SicherungWorker(threading.Thread):
    def __init__(self, db_pfad: str, ziel_ordner: str, instance_name: str,
                 intervall_min: int, auf_status_geaendert: Callable[[dict], None] | None = None):
        super().__init__(daemon=True)
        self._db_pfad = db_pfad
        self._ziel_ordner = ziel_ordner
        self._instance_name = instance_name
        self._intervall_s = max(1, intervall_min) * 60
        self._auf_status_geaendert = auf_status_geaendert or (lambda status: None)
        self._stop_angefordert = threading.Event()

    def stoppen(self) -> None:
        self._stop_angefordert.set()

    def run(self) -> None:
        while not self._stop_angefordert.is_set():
            try:
                ziel_datei = sicherung_durchfuehren(self._db_pfad, self._ziel_ordner,
                                                    self._instance_name)
                self._auf_status_geaendert({"erfolgreich": True, "datei": str(ziel_datei)})
            except OSError as exc:
                self._auf_status_geaendert({"erfolgreich": False, "fehler": str(exc)})
            self._stop_angefordert.wait(self._intervall_s)
