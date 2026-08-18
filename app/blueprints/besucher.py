"""Oeffentliche Besucheransicht - funktioniert ohne Anmeldung, zeigt nur
die aktuelle Gesamtwertung und den Zeitplan/die Startlisten. Reine Anzeige,
keine Aktionen/Formulare (Wertung und Zeitplan selbst sind zwar auch schon
ueber /wertung/ und /zeitplan/ ohne Login erreichbar, dort aber eingebettet
in die vollstaendige Organisator-Navigation - diese Seite ist bewusst
reduziert fuer Gaeste am Handy)."""
from flask import Blueprint, render_template

from ..models import Team, Disziplin, Startplatz
from ..wertung import gesamtwertung_vollstaendig
from .zeitplan import _startplaetze_numerisch_sortieren

bp = Blueprint("besucher", __name__, url_prefix="/besucher")


@bp.route("/")
def index():
    disziplinen = Disziplin.query.order_by(Disziplin.reihenfolge,
                                            Disziplin.name).all()
    teams = Team.query.all()
    tabelle = gesamtwertung_vollstaendig(teams, disziplinen)

    zeitplan = []
    for d in disziplinen:
        startplaetze = (Startplatz.query.filter_by(disziplin_id=d.id)
                        .order_by(Startplatz.heat, Startplatz.startnummer).all())
        startplaetze = _startplaetze_numerisch_sortieren(startplaetze)
        if startplaetze:
            zeitplan.append({"disziplin": d, "startplaetze": startplaetze})

    return render_template("besucher/index.html", tabelle=tabelle,
                           zeitplan=zeitplan)
