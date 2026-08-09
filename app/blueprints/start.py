"""Startseite / Übersicht."""
from flask import Blueprint, render_template

from ..models import Team, Disziplin, Ergebnis

bp = Blueprint("start", __name__)


@bp.route("/")
def index():
    return render_template(
        "index.html",
        anzahl_teams=Team.query.count(),
        anzahl_disziplinen=Disziplin.query.count(),
        anzahl_ergebnisse=Ergebnis.query.count(),
    )
