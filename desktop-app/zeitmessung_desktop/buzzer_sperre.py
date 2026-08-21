"""Softwareseitige Sperrzeit für physische Buzzer-Ereignisse.

Die Firmware entprellt elektrische Flanken bereits kurz. Diese zusätzliche,
deutlich längere Sperre verhindert versehentliche Doppelauslösungen auf
derselben Bahn. Jede Bahn führt ihren eigenen Zeitstempel, sodass ein Buzzer
auf Bahn 1 niemals Bahn 2 bis 4 blockiert.
"""
from __future__ import annotations


class BuzzerSperre:
    def __init__(self, sperrzeit_s: int):
        self.sperrzeit_s = max(0, sperrzeit_s)
        self._letzte_ausloesung: dict[int, float] = {}

    def darf_ausloesen(self, bahn: int, zeitpunkt: float) -> bool:
        letzte = self._letzte_ausloesung.get(bahn)
        if letzte is not None and zeitpunkt - letzte < self.sperrzeit_s:
            return False
        self._letzte_ausloesung[bahn] = zeitpunkt
        return True
