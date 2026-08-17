"""Parser für das serielle Zeilenprotokoll des Arduino Mega (siehe
firmware/zeitmessung-mega/README.md). Reine Funktion ohne I/O, damit sie
ohne echte Hardware testbar ist."""
from __future__ import annotations


def zeile_parsen(zeile: str) -> dict | None:
    """Zerlegt eine einzelne empfangene Serial-Zeile.

    Rückgabe z.B. {"typ": "event", "bahn": 2, "geraet_millis": 12345},
    {"typ": "heartbeat", "geraet_millis": 12345},
    {"typ": "ready", "geraet_id": "mega2560-zeitmessung-1"},
    {"typ": "state", "geraet_millis": 12345, "zustaende": [0, 1, 0, 0]}
    (Index 0 = Bahn 1, Wert 1 = Kontakt gerade ausgelöst/HIGH - nur für die
    Live-Anzeige beim Verkabeln/Testen, siehe firmware-README),
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

    if teile[0] == "STATE" and len(teile) >= 6:
        millis = _int_oder_none(teile[1])
        zustaende = [_int_oder_none(w) for w in teile[2:6]]
        if millis is None or any(z is None or z not in (0, 1) for z in zustaende):
            return None
        return {"typ": "state", "geraet_millis": millis, "zustaende": zustaende}

    return None


def _int_oder_none(wert: str) -> int | None:
    try:
        return int(wert)
    except ValueError:
        return None
