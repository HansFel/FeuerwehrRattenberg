"""Startseite / rollenabhängiges Dashboard sowie rechtliche Pflichtseiten."""
from flask import Blueprint, render_template

from ..models import Team, Disziplin, Ergebnis

bp = Blueprint("start", __name__)


@bp.route("/")
def index():
    disziplinen = Disziplin.query.order_by(Disziplin.reihenfolge,
                                           Disziplin.name).all()
    return render_template(
        "index.html",
        anzahl_teams=Team.query.count(),
        anzahl_disziplinen=len(disziplinen),
        anzahl_ergebnisse=Ergebnis.query.count(),
        disziplinen=disziplinen,
    )


@bp.route("/impressum")
def impressum():
    return render_template("impressum.html")


@bp.route("/datenschutz")
def datenschutz():
    return render_template("datenschutz.html")
