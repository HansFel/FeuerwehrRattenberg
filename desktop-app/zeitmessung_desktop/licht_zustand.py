"""Reine Logik: leitet aus dem Lauf-Zustand (Server- oder lokal-gesteuert)
den anzuzeigenden Bahnbeleuchtung-Zustand ab (siehe DMX_Zeitmessung/README.md
für die Hardware-Seite). Bewusst getrennt von bahnbeleuchtung.py
(Hardware-I/O), damit ohne Arduino testbar - selbes Muster wie
lokale_zuordnung.py für die Zeitmessung selbst."""
from __future__ import annotations

ZUSTAENDE = ("aus", "vorbereitung", "bereit", "start")


def zustand_bestimmen(lauf_aktiv: bool, aktiviert: bool, hat_kontakt: bool) -> str:
    """
    lauf_aktiv:  existiert gerade ein (Server- oder lokaler) Lauf?
    aktiviert:   wurde er freigegeben (aktiviert_um gesetzt)?
    hat_kontakt: ist seit der Freigabe schon mindestens 1 Kontaktereignis
                 für diesen Lauf eingetroffen?

    Reihenfolge der Prüfungen ist bewusst so gewählt, dass ein
    inkonsistenter Aufruf (z.B. hat_kontakt=True bei aktiviert=False) nie zu
    "start" ohne "aktiviert" führen kann - die Zustände sind eine feste
    Kette aus/vorbereitung/bereit/start.
    """
    if not lauf_aktiv:
        return "aus"
    if not aktiviert:
        return "vorbereitung"
    if not hat_kontakt:
        return "bereit"
    return "start"
