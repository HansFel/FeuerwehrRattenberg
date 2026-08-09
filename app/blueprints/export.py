"""CSV-Export von Mannschaften, Ergebnissen und Gesamtwertung.

Format: UTF-8 mit BOM und Semikolon-Trennung – so öffnet deutsches Excel die
Datei direkt korrekt (Umlaute + Spalten).
"""
import csv
import io

from flask import Blueprint, Response

from ..models import Team, Disziplin, WERTUNG_ZEIT
from ..wertung import rangliste_disziplin, gesamtwertung, format_zeit

bp = Blueprint("export", __name__, url_prefix="/export")


def _csv_antwort(zeilen: list[list], dateiname: str) -> Response:
    puffer = io.StringIO()
    schreiber = csv.writer(puffer, delimiter=";")
    schreiber.writerows(zeilen)
    daten = "﻿" + puffer.getvalue()          # BOM voranstellen
    return Response(
        daten,
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{dateiname}"'},
    )


@bp.route("/mannschaften.csv")
def mannschaften():
    zeilen = [["Startnummer", "Name", "Wehr/Ort", "Kontakt", "Notiz"]]
    for t in Team.query.order_by(Team.startnummer, Team.name):
        zeilen.append([t.startnummer, t.name, t.wehr, t.kontakt, t.notiz])
    return _csv_antwort(zeilen, "mannschaften.csv")


@bp.route("/ergebnisse.csv")
def ergebnisse():
    zeilen = [["Disziplin", "Rang", "Mannschaft", "Wehr", "Wert",
               "Fehlerpunkte", "DSQ", "Notiz"]]
    for d in Disziplin.query.order_by(Disziplin.reihenfolge, Disziplin.name):
        ist_zeit = d.wertungsart == WERTUNG_ZEIT
        for p in rangliste_disziplin(d):
            erg = p.ergebnis
            if erg is None:
                continue
            wert = format_zeit(p.wert) if ist_zeit else (
                "" if p.wert is None else p.wert)
            zeilen.append([d.name, p.rang or "", p.team.name, p.team.wehr,
                           wert, erg.fehlerpunkte or 0,
                           "ja" if erg.disqualifiziert else "", erg.notiz])
    return _csv_antwort(zeilen, "ergebnisse.csv")


@bp.route("/gesamtwertung.csv")
def gesamt():
    teams = Team.query.all()
    disziplinen = Disziplin.query.order_by(Disziplin.reihenfolge).all()
    zeilen = [["Rang", "Mannschaft", "Wehr", "Rangpunkte"]]
    for z in gesamtwertung(teams, disziplinen):
        zeilen.append([z["rang"], z["team"].name, z["team"].wehr, z["punkte"]])
    return _csv_antwort(zeilen, "gesamtwertung.csv")
