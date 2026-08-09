"""Berechnung von Ranglisten (pro Disziplin und Gesamtwertung)."""
from __future__ import annotations

from dataclasses import dataclass

from .models import Disziplin, Ergebnis, Team, WERTUNG_ZEIT


@dataclass
class Platzierung:
    team: Team
    ergebnis: Ergebnis | None
    wert: float | None      # Nettozeit (klein=gut) oder Punkte (groß=gut)
    rang: int | None        # None bei DSQ / ohne Ergebnis


def rangliste_disziplin(disziplin: Disziplin) -> list[Platzierung]:
    """Sortierte Platzierungen einer einzelnen Disziplin."""
    ist_zeit = disziplin.wertungsart == WERTUNG_ZEIT
    eintraege: list[Platzierung] = []

    for erg in disziplin.ergebnisse:
        if erg.disqualifiziert:
            wert = None
        elif ist_zeit:
            wert = erg.nettozeit
        else:
            wert = erg.punkte
        eintraege.append(Platzierung(team=erg.team, ergebnis=erg,
                                     wert=wert, rang=None))

    gewertet = [e for e in eintraege if e.wert is not None]
    gewertet.sort(key=lambda e: e.wert, reverse=not ist_zeit)
    for i, e in enumerate(gewertet, start=1):
        e.rang = i

    ohne = [e for e in eintraege if e.wert is None]
    return gewertet + ohne


def gesamtwertung(teams: list[Team],
                  disziplinen: list[Disziplin]) -> list[dict]:
    """Gesamtwertung über alle Disziplinen nach Rangpunkten.

    Pro Disziplin gibt es Rangpunkte = Platzierung (1 = bester). Wer nicht
    gewertet ist, bekommt (Teilnehmerzahl + 1) Punkte. Wenig Punkte = besser.
    """
    rangpunkte: dict[int, int] = {t.id: 0 for t in teams}
    for d in disziplinen:
        platzierungen = rangliste_disziplin(d)
        strafe = len(teams) + 1
        for p in platzierungen:
            rangpunkte[p.team.id] += p.rang if p.rang is not None else strafe

    tabelle = [{"team": t, "punkte": rangpunkte[t.id]} for t in teams]
    tabelle.sort(key=lambda z: z["punkte"])
    for i, z in enumerate(tabelle, start=1):
        z["rang"] = i
    return tabelle


def format_zeit(sekunden: float | None) -> str:
    """Sekunden als m:ss,hh darstellen."""
    if sekunden is None:
        return "–"
    minuten = int(sekunden // 60)
    rest = sekunden - minuten * 60
    if minuten:
        return f"{minuten}:{rest:05.2f}".replace(".", ",")
    return f"{rest:.2f}".replace(".", ",") + " s"
