"""Steuerung der 4 Bahn-Scheinwerfer (DMX über Arduino Uno + MAX485) über
eine zweite, vom Zeitmessung-Mega unabhängige serielle Schnittstelle - siehe
../DMX_Zeitmessung/README.md für Hardware/Protokoll-Details. Portiert aus
DMX_Zeitmessung/lane_lights.py, an Namens-/Codestil dieses Pakets angepasst.

Bewusst rein additiv/optional: fehlt der Port oder bricht die Verbindung ab,
läuft die eigentliche Zeitmessung unbeeinflusst weiter - jeder Fehler wird
nur geloggt, nie weitergereicht (siehe _schreiben())."""
from __future__ import annotations

import logging
import threading
import time

import serial

_log = logging.getLogger(__name__)

ZUSTANDSFARBEN = {
    "aus":          (0, 0, 0),
    "vorbereitung": (255, 80, 0),   # Amber
    "bereit":       (0, 0, 255),    # Blau
    "start":        (0, 255, 0),    # Grün
}
BLITZFARBE = (255, 255, 255)         # Kontaktauslösung je Bahn = weißer Blitz
BLITZ_MS = 350
ANZAHL_BAHNEN = 4


class Bahnbeleuchtung:
    def __init__(self, port: str, baudrate: int = 9600):
        self._ser: serial.Serial | None = None
        self._verbunden = False
        try:
            self._ser = serial.Serial(port, baudrate, timeout=1)
            time.sleep(2)   # Arduino bootet nach dem Öffnen automatisch neu
            self._verbunden = True
        except (serial.SerialException, OSError) as exc:
            _log.warning("Bahnbeleuchtung: Port %s nicht erreichbar: %s", port, exc)
        self._lock = threading.Lock()
        self._blitz_timer: dict[int, threading.Timer] = {}
        self.zustand = "aus"

    @property
    def verbunden(self) -> bool:
        return self._verbunden

    def _schreiben(self, bahn: int, rgb: tuple[int, int, int]) -> None:
        if not self._verbunden or self._ser is None:
            return
        r, g, b = rgb
        befehl = f"{bahn} {r} {g} {b}\n".encode()
        try:
            with self._lock:
                self._ser.write(befehl)
        except (serial.SerialException, OSError) as exc:
            _log.warning("Bahnbeleuchtung: Schreiben fehlgeschlagen, "
                        "gelte ab jetzt als getrennt: %s", exc)
            self._verbunden = False

    def zustand_setzen(self, zustand: str) -> None:
        """Setzt ALLE 4 Bahnen auf die Zustandsfarbe (siehe licht_zustand.py
        für die Ableitung des Zustands aus dem Lauf-Status)."""
        if zustand not in ZUSTANDSFARBEN:
            raise ValueError(f"Unbekannter Zustand: {zustand!r}")
        self.zustand = zustand
        rgb = ZUSTANDSFARBEN[zustand]
        for bahn in range(1, ANZAHL_BAHNEN + 1):
            self._blitz_abbrechen(bahn)
            self._schreiben(bahn, rgb)

    def blitzen(self, bahn: int) -> None:
        """Bahn `bahn` kurz weiß aufblitzen lassen (Kontaktauslösung/
        Bahnwechsel), danach automatisch zurück zur aktuellen
        Zustandsfarbe. Nicht blockierend."""
        if not 1 <= bahn <= ANZAHL_BAHNEN:
            return
        self._blitz_abbrechen(bahn)
        self._schreiben(bahn, BLITZFARBE)
        timer = threading.Timer(BLITZ_MS / 1000.0, self._wiederherstellen, args=(bahn,))
        timer.daemon = True
        self._blitz_timer[bahn] = timer
        timer.start()

    def _wiederherstellen(self, bahn: int) -> None:
        self._blitz_timer.pop(bahn, None)
        self._schreiben(bahn, ZUSTANDSFARBEN[self.zustand])

    def _blitz_abbrechen(self, bahn: int) -> None:
        timer = self._blitz_timer.pop(bahn, None)
        if timer is not None:
            timer.cancel()

    def schliessen(self) -> None:
        for bahn in list(self._blitz_timer):
            self._blitz_abbrechen(bahn)
        if self._verbunden:
            self.zustand_setzen("aus")
        if self._ser is not None:
            self._ser.close()
