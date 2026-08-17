"""Hintergrund-Thread: liest den Arduino Mega über USB-Seriell, schreibt
jedes Kontaktereignis SOFORT in die lokale Datenbank und versucht bei
Verbindungsabbruch (USB gezogen/Neustart des Mega) automatisch erneut zu
verbinden, statt die App zum Absturz zu bringen."""
from __future__ import annotations

import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Callable

import serial

from . import datenbank
from .lokale_zuordnung import zuordnung_pruefen
from .seriell_protokoll import zeile_parsen

WIEDERVERBINDEN_PAUSE_S = 3
# Deutlich über HEARTBEAT_INTERVALL_MS (2s) der Firmware: bleibt diese Zeit
# lang komplett ohne Daten (auch kein HEARTBEAT), gilt die Verbindung als tot
# - Windows meldet ein physisch entferntes USB-Gerät nicht immer als Fehler,
# readline() liefert dann einfach dauerhaft leere Timeouts statt einer
# Exception ("Zombie-Verbindung": App zeigt weiter "verbunden", obwohl das
# Gerät längst weg ist).
VERBINDUNG_TIMEOUT_S = 8


class SeriellWorker(threading.Thread):
    def __init__(self, db_verbindung, com_port: str, baudrate: int,
                 auf_status_geaendert: Callable[[dict], None] | None = None):
        super().__init__(daemon=True)
        self._db = db_verbindung
        self._com_port = com_port
        self._baudrate = baudrate
        self._auf_status_geaendert = auf_status_geaendert or (lambda status: None)
        self._stop_angefordert = threading.Event()
        self.letzter_kontakt: float | None = None
        self.verbunden = False

    def stoppen(self) -> None:
        self._stop_angefordert.set()

    def run(self) -> None:
        while not self._stop_angefordert.is_set():
            try:
                self._verbindung_betreiben()
            except (serial.SerialException, OSError) as exc:
                self.verbunden = False
                self._auf_status_geaendert({"verbunden": False, "fehler": str(exc)})
            if self._stop_angefordert.is_set():
                break
            time.sleep(WIEDERVERBINDEN_PAUSE_S)

    def _verbindung_betreiben(self) -> None:
        with serial.Serial(self._com_port, self._baudrate, timeout=1) as port:
            self.verbunden = True
            self._auf_status_geaendert({"verbunden": True})
            letzter_datenempfang = time.monotonic()
            while not self._stop_angefordert.is_set():
                zeile_roh = port.readline()
                if not zeile_roh:
                    if time.monotonic() - letzter_datenempfang > VERBINDUNG_TIMEOUT_S:
                        self.verbunden = False
                        self._auf_status_geaendert(
                            {"verbunden": False, "fehler": "Timeout - keine Daten mehr empfangen"})
                        return   # schließt den Port (with-Block) und löst einen Reconnect aus
                    continue   # normaler Timeout, einfach weiter warten
                letzter_datenempfang = time.monotonic()
                self._zeile_verarbeiten(zeile_roh.decode("ascii", errors="ignore"))

    def _zeile_verarbeiten(self, zeile: str) -> None:
        geparst = zeile_parsen(zeile)
        if geparst is None:
            return
        self.letzter_kontakt = time.monotonic()

        if geparst["typ"] == "event":
            client_event_id = uuid.uuid4().hex
            empfangen_um = datetime.now(timezone.utc).isoformat()
            datenbank.ereignis_hinzufuegen(
                self._db, bahn=geparst["bahn"], geraet_millis=geparst["geraet_millis"],
                empfangen_um=empfangen_um, client_event_id=client_event_id,
            )
            zuordnung_pruefen(self._db, geparst["bahn"])
            self._auf_status_geaendert({"neues_ereignis": geparst})

        elif geparst["typ"] == "state":
            # Nur Live-Anzeige (Verkabeln/Testen) - bewusst NICHT in der
            # Datenbank gespeichert, EVENT bleibt die einzige Quelle für
            # echte Zeitmessung.
            self._auf_status_geaendert({"zustaende": geparst["zustaende"]})
