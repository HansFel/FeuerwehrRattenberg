"""Berechnung von Ranglisten (pro Disziplin und Gesamtwertung)."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .models import (Disziplin, Ergebnis, Team, WERTUNG_ZEIT, Startplatz,
                     BestellPosition, Strafe, NotfallBahn)


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
    gewertet.sort(key=lambda e: (
        e.wert if ist_zeit else -e.wert,
        (e.team.name or "").casefold(),
        (e.team.wehr or "").casefold(),
    ))
    for i, e in enumerate(gewertet, start=1):
        e.rang = i

    ohne = sorted(
        (e for e in eintraege if e.wert is None),
        key=lambda e: ((e.team.name or "").casefold(),
                       (e.team.wehr or "").casefold()),
    )
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
    tabelle.sort(key=lambda z: (
        z["punkte"], (z["team"].name or "").casefold(),
        (z["team"].wehr or "").casefold(),
    ))
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


def beste_einzelzeit() -> list[dict]:
    """Die drei schnellsten plausiblen Teilzeiten ab 35 Sekunden.

    Angefangene oder abgebrochene Bahnen werden ignoriert. Die Auszeichnung
    ist rein informativ und beeinflusst weder Weiterkommen noch Platzierung.
    """
    kandidaten = []
    bahnen = (NotfallBahn.query
              .order_by(NotfallBahn.lauf_id, NotfallBahn.bahn_nr,
                        NotfallBahn.id).all())
    for bahn in bahnen:
        zeiten = [getattr(bahn, f"zeit_laeufer{i}") for i in range(1, 5)]
        if any(zeit is None or zeit <= 0 for zeit in zeiten):
            continue
        mitglieder = {m.position: m for m in (bahn.team.mitglieder
                                               if bahn.team else [])}
        for laeufer_nr, zeit in enumerate(zeiten, start=1):
            if zeit < 35:
                continue
            if (bahn.einzelzeit_ausschluss_mask or 0) & (1 << (laeufer_nr - 1)):
                continue
            mitglied = mitglieder.get(laeufer_nr)
            kandidat = {
                "zeit": float(zeit),
                "team": bahn.team,
                "mitglied": mitglied,
                "laeufer_name": (mitglied.anzeige() if mitglied
                                  else f"Läufer {laeufer_nr}"),
                "laeufer_nr": laeufer_nr,
                "lauf": bahn.lauf,
                "bahn_nr": bahn.bahn_nr,
                "runde": _rundenname(bahn.lauf.bezeichnung),
                "rundenherkunft": _rundenherkunft(bahn.lauf.bezeichnung),
            }
            kandidaten.append(kandidat)
    kandidaten.sort(key=lambda k: (
        k["zeit"], k["laeufer_name"].casefold(),
        (k["team"].name or "").casefold()))
    return kandidaten[:3]


def _rundenname(bezeichnung: str | None) -> str:
    """Kurzer, besucherfreundlicher Name der Runde einer Einzelzeit."""
    text = bezeichnung or ""
    for name in ("Großes Finale", "Kleines Finale", "Halbfinale",
                 "Platzierungslauf", "Vorrunde"):
        if name in text:
            return name
    return text or "unbekanntem Lauf"


def _rundenherkunft(bezeichnung: str | None) -> str:
    """Rundenname mit passendem Artikel im Dativ für 'Bestzeit aus ...'."""
    name = _rundenname(bezeichnung)
    return {
        "Großes Finale": "dem Großen Finale",
        "Kleines Finale": "dem Kleinen Finale",
        "Halbfinale": "dem Halbfinale",
        "Platzierungslauf": "dem Platzierungslauf",
        "Vorrunde": "der Vorrunde",
    }.get(name, name)


_ZIEL_PLATZ_MUSTER = re.compile(r"Platz (\d+)-(\d+)")


def _lauf_nummer(heat: str | None) -> int:
    zahlen = re.findall(r"\d+", heat or "")
    return int(zahlen[0]) if zahlen else 0


def finale_platzierung(team: Team,
                       strafsekunden: dict[int, float] | None = None) -> int | None:
    """Definitive Platzierung eines Teams (siehe app/blueprints/zeitplan.py:
    _naechste_runde_erzeugen/_finale_erzeugen fuer das Heat-Namensschema).

    Sobald ein Team einen Ziellauf (Platzierungslauf oder Finale, erkennbar
    am "Platz <von>-<bis>" im Heat-Namen) mit erfasstem Ergebnis absolviert
    hat, ist DAS die endgueltige Platzierung - unabhaengig vom weiteren
    Turnierverlauf. Gibt None zurueck, wenn das Team noch in keinem Ziellauf
    war (Platzierung noch nicht definitiv, siehe stattdessen die
    vorlaeufige Summenzeit aus der Vorrunde).
    """
    strafsekunden = strafsekunden or {}
    eintraege = [sp for sp in Startplatz.query.filter_by(team_id=team.id).all()
                if sp.ergebnis_sekunden is not None]
    ziel_eintraege = [sp for sp in eintraege if _ZIEL_PLATZ_MUSTER.search(sp.heat or "")]
    if not ziel_eintraege:
        return None

    letzter = max(ziel_eintraege, key=lambda sp: _lauf_nummer(sp.heat))
    von = int(_ZIEL_PLATZ_MUSTER.search(letzter.heat).group(1))

    teilnehmer = (Startplatz.query.filter_by(heat=letzter.heat)
                 .filter(Startplatz.ergebnis_sekunden.isnot(None)).all())
    teilnehmer.sort(key=lambda sp: sp.ergebnis_sekunden
                    + strafsekunden.get(sp.team_id, 0.0))
    for rang, sp in enumerate(teilnehmer, start=1):
        if sp.team_id == team.id:
            return von + (rang - 1)
    return None


def team_challenge(teams: list[Team]) -> list[dict]:
    """Team Challenge: Getraenkepunkte (aus dem Ausschank) + Fanpunkte (vom
    Organisator) = Gesamt. Live gereiht, hoechste Punktzahl = bester. Von der
    Siloplanen-Race-Gesamtwertung unabhaengige, eigene Wertung."""
    gp: dict[int, int] = {}
    for pos in BestellPosition.query.all():
        if pos.team_id and pos.punkte_gesamt:
            gp[pos.team_id] = gp.get(pos.team_id, 0) + pos.punkte_gesamt

    eintraege = []
    for t in teams:
        getraenke = gp.get(t.id, 0)
        fan = t.fanpunkte or 0
        eintraege.append({
            "team": t, "getraenkepunkte": getraenke,
            "fanpunkte": fan, "gesamt": getraenke + fan,
        })
    eintraege.sort(key=lambda e: (
        -e["gesamt"], (e["team"].name or "").casefold(),
        (e["team"].wehr or "").casefold(),
    ))
    for i, e in enumerate(eintraege, start=1):
        e["rang"] = i
    return eintraege


def gesamtwertung_vollstaendig(teams: list[Team],
                               disziplinen: list[Disziplin]) -> list[dict]:
    """Vollstaendige Gesamtwertungs-Tabelle inkl. Getraenkepunkte,
    Strafsekunden, gemessener Zeit und definitiver/vorlaeufiger Platzierung -
    einzige Quelle fuer diese Berechnung, damit Web-Ansicht (wertung/
    uebersicht.html) und PDF-Export (pdf.gesamt) garantiert uebereinstimmen.
    Jede Zeile: team, punkte (Rangpunkte), getraenkepunkte, strafsekunden,
    gemessene_zeit, gesamtzeit, finaler_platz, rang.
    """
    tabelle = gesamtwertung(teams, disziplinen)

    getraenkepunkte: dict[int, int] = {}
    for pos in BestellPosition.query.all():
        if pos.team_id and pos.punkte_gesamt:
            getraenkepunkte[pos.team_id] = (
                getraenkepunkte.get(pos.team_id, 0) + pos.punkte_gesamt)

    strafsekunden: dict[int, float] = {}
    for s in Strafe.query.all():
        strafsekunden[s.team_id] = (
            strafsekunden.get(s.team_id, 0.0) + s.sekunden)

    gemessene_zeit: dict[int, float] = {}
    for sp in Startplatz.query.filter(Startplatz.ergebnis_sekunden.isnot(None)).all():
        gemessene_zeit[sp.team_id] = (
            gemessene_zeit.get(sp.team_id, 0.0) + sp.ergebnis_sekunden)

    for zeile in tabelle:
        tid = zeile["team"].id
        zeile["getraenkepunkte"] = getraenkepunkte.get(tid, 0)
        zeile["strafsekunden"] = strafsekunden.get(tid, 0.0)
        zeile["gemessene_zeit"] = gemessene_zeit.get(tid)
        if zeile["gemessene_zeit"] is None:
            zeile["gesamtzeit"] = None
        else:
            zeile["gesamtzeit"] = zeile["gemessene_zeit"] + zeile["strafsekunden"]
        zeile["finaler_platz"] = finale_platzierung(zeile["team"], strafsekunden)

    def _sortier_schluessel(z):
        alphabetisch = ((z["team"].name or "").casefold(),
                        (z["team"].wehr or "").casefold())
        if z["finaler_platz"] is not None:
            return (0, z["finaler_platz"], *alphabetisch)
        if z["gesamtzeit"] is not None:
            return (1, z["gesamtzeit"], *alphabetisch)
        return (2, 0, *alphabetisch)
    tabelle.sort(key=_sortier_schluessel)
    for i, zeile in enumerate(tabelle, start=1):
        zeile["rang"] = zeile["finaler_platz"] if zeile["finaler_platz"] is not None else i

    return tabelle
