"""Reine Logik: leitet aus dem Lauf-Zustand (Server- oder lokal-gesteuert)
den anzuzeigenden Bahnbeleuchtung-Zustand ab (siehe DMX_Zeitmessung/README.md
für die Hardware-Seite). Bewusst getrennt von bahnbeleuchtung.py
(Hardware-I/O), damit ohne Arduino testbar - selbes Muster wie
lokale_zuordnung.py für die Zeitmessung selbst."""
from __future__ import annotations

ZUSTAENDE = ("aus", "vorbereitung", "start", "fertig")


def zustand_bestimmen(lauf_aktiv: bool, aktiviert: bool, hat_kontakt: bool,
                      vollstaendig: bool = False) -> str:
    """
    lauf_aktiv:   existiert gerade ein (Server- oder lokaler) Lauf?
    aktiviert:    wurde er freigegeben (aktiviert_um gesetzt)?
    hat_kontakt:  ist seit der Freigabe schon mindestens 1 Kontaktereignis
                  für diesen Lauf eingetroffen? (wird fuer die Zustands-
                  ableitung nicht mehr herangezogen - siehe Hinweis unten -
                  aber fuer das white-blitzen je Bahn in bahnbeleuchtung.py
                  weiterhin ausgewertet; der Parameter bleibt aus Kompat-
                 ibilitaet erhalten.)
    vollstaendig: sind alle Team-Bahnen dieses Laufs zu Ende gemessen
                  (alle 4 Läuferzeiten gesetzt)? Dann -> "fertig" (ROT).

    Gewollte Farb-Automatik (auf Wunsch des Users, Build 80):
      kein Lauf                    -> aus          (Licht aus)
      Lauf vorhanden, NICHT freig. -> vorbereitung (Amber)
      freigegeben, NICHT fertig    -> start        (GRUEN)  <- sobald der
                                                            Lauf beginnt
      fertig (alle Zeiten da)      -> fertig       (ROT)    <- bis der
                                                            naechste Lauf
                                                            freigegeben wird

    "bereit" (Blau) wird vorerst bewusst NICHT verwendet (auf Wunsch des
    Users "die Farbe Blau koennen wir uns zurzeit sparen", Build 80): schon
    ab Freigabe GRUEN, nicht erst beim 1. Kontakt. Der Zustand ist aus
    ZUSTAENDE/ZUSTANDSFARBEN entfernt; das DmxSimple-Protokoll/README kennt
    ihn weiterhin, falls er spaeter wieder gebraucht wird.
    """
    if not lauf_aktiv:
        return "aus"
    if not aktiviert:
        return "vorbereitung"
    if vollstaendig:
        return "fertig"
    return "start"
