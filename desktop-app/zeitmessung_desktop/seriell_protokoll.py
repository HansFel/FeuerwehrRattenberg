"""Parser für das serielle Zeilenprotokoll des Arduino Mega (siehe
firmware/zeitmessung-mega/README.md). Reine Funktion ohne I/O, damit sie
ohne echte Hardware testbar ist."""
from __future__ import annotations


def zeile_parsen(zeile: str) -> dict | None:
    """Zerlegt eine einzelne empfangene Serial-Zeile.

    Rückgabe z.B. {"typ": "event", "bahn": 2, "geraet_millis": 12345},
    {"typ": "heartbeat", "geraet_millis": 12345},
    {"typ": "ready", "geraet_id": "mega2560-zeitmessung-1"},
    oder None bei einer unbekannten/fehlerhaften Zeile (wird ignoriert,
    kein Absturz bei seriellem Rauschen/Teilzeilen)."""
    zeile = zeile.strip()
    if not zeile:
        return None
    teile = zeile.split(";")

    if teile[0] == "READY" and len(teile) >= 2:
        return {"typ": "ready", "geraet_id": teile[1]}

    if teile[0] == "HEARTBEAT" and len(teile) >= 2:
        millis = _int_oder_none(teile[1])
        if millis is None:
            return None
        return {"typ": "heartbeat", "geraet_millis": millis}

    if teile[0] == "EVENT" and len(teile) >= 3:
        bahn = _int_oder_none(teile[1])
        millis = _int_oder_none(teile[2])
        if bahn is None or millis is None or not (1 <= bahn <= 4):
            return None
        return {"typ": "event", "bahn": bahn, "geraet_millis": millis}

    return None


def _int_oder_none(wert: str) -> int | None:
    try:
        return int(wert)
    except ValueError:
        return None
