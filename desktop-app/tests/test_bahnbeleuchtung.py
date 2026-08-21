"""Tests für die Bahnbeleuchtung (DMX-Ansteuerung) mit einem gefälschten
seriellen Port - kein Arduino nötig. Prüft vor allem, dass ein fehlender/
gestörter Port NIE eine Exception nach außen wirft (siehe
bahnbeleuchtung.py Docstring: die Zeitmessung darf davon nie betroffen sein)."""
from __future__ import annotations

import pytest
import serial

from zeitmessung_desktop import bahnbeleuchtung as modul
from zeitmessung_desktop.bahnbeleuchtung import Bahnbeleuchtung


class GefaelschterPort:
    def __init__(self, port, baudrate, timeout=None):
        self.geschrieben: list[bytes] = []
        self.geschlossen = False

    def write(self, daten: bytes) -> None:
        self.geschrieben.append(daten)

    def close(self) -> None:
        self.geschlossen = True


class FehlerhafterPort:
    def __init__(self, port, baudrate, timeout=None):
        raise serial.SerialException("kein Gerät an diesem Port")


@pytest.fixture(autouse=True)
def _kein_echtes_warten(monkeypatch):
    """time.sleep(2) beim Verbindungsaufbau (Arduino-Reset abwarten) in
    Tests überspringen."""
    monkeypatch.setattr(modul.time, "sleep", lambda s: None)


def test_verbindungsfehler_wirft_keine_exception(monkeypatch):
    monkeypatch.setattr(modul.serial, "Serial", FehlerhafterPort)
    b = Bahnbeleuchtung("/dev/ttyUSB99")   # darf nicht werfen
    assert b.verbunden is False


def test_aufrufe_ohne_verbindung_sind_folgenlos(monkeypatch):
    monkeypatch.setattr(modul.serial, "Serial", FehlerhafterPort)
    b = Bahnbeleuchtung("/dev/ttyUSB99")
    b.zustand_setzen("start")   # darf nicht werfen
    b.blitzen(1)                # darf nicht werfen
    b.schliessen()              # darf nicht werfen


def test_zustand_setzen_schreibt_alle_4_bahnen(monkeypatch):
    monkeypatch.setattr(modul.serial, "Serial", GefaelschterPort)
    b = Bahnbeleuchtung("/dev/ttyUSB0")
    b.zustand_setzen("start")
    assert b._ser.geschrieben == [
        b"1 0 255 0\n", b"2 0 255 0\n", b"3 0 255 0\n", b"4 0 255 0\n",
    ]
    assert b.zustand == "start"


def test_unbekannter_zustand_wirft_wertfehler(monkeypatch):
    monkeypatch.setattr(modul.serial, "Serial", GefaelschterPort)
    b = Bahnbeleuchtung("/dev/ttyUSB0")
    with pytest.raises(ValueError):
        b.zustand_setzen("unsinn")


def test_blitzen_ausserhalb_1_bis_4_wird_ignoriert(monkeypatch):
    monkeypatch.setattr(modul.serial, "Serial", GefaelschterPort)
    b = Bahnbeleuchtung("/dev/ttyUSB0")
    b.blitzen(0)
    b.blitzen(5)
    assert b._ser.geschrieben == []


def test_blitzen_schreibt_weiss_und_stellt_danach_zustand_wieder_her(monkeypatch):
    """Ruft _wiederherstellen() direkt auf statt auf den echten Timer zu
    warten - deterministisch, unabhängig von Wall-Clock-Timing (der
    autouse-Fixture oben patcht ohnehin time.sleep global, ein echtes Warten
    hier wäre also gar nicht messbar)."""
    monkeypatch.setattr(modul.serial, "Serial", GefaelschterPort)
    b = Bahnbeleuchtung("/dev/ttyUSB0")
    b.zustand_setzen("start")
    b._ser.geschrieben.clear()

    b.blitzen(2)
    assert b._ser.geschrieben == [b"2 255 255 255\n"]

    b._wiederherstellen(2)
    assert b._ser.geschrieben[-1] == f"2 {' '.join(map(str, modul.ZUSTANDSFARBEN['start']))}\n".encode()


def test_schreibfehler_markiert_als_getrennt(monkeypatch):
    monkeypatch.setattr(modul.serial, "Serial", GefaelschterPort)
    b = Bahnbeleuchtung("/dev/ttyUSB0")

    def kaputtes_write(daten):
        raise serial.SerialException("Kabel gezogen")

    b._ser.write = kaputtes_write
    b.zustand_setzen("start")   # darf nicht werfen
    assert b.verbunden is False


def test_schliessen_schaltet_aus_und_schliesst_port(monkeypatch):
    monkeypatch.setattr(modul.serial, "Serial", GefaelschterPort)
    b = Bahnbeleuchtung("/dev/ttyUSB0")
    b.zustand_setzen("start")
    b._ser.geschrieben.clear()

    b.schliessen()
    assert b._ser.geschrieben == [b"1 0 0 0\n", b"2 0 0 0\n", b"3 0 0 0\n", b"4 0 0 0\n"]
    assert b._ser.geschlossen is True
