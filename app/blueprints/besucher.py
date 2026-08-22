"""Oeffentliche Besucheransicht - funktioniert ohne Anmeldung, zeigt nur
die aktuelle Gesamtwertung und den Zeitplan/die Startlisten. Reine Anzeige,
keine Aktionen/Formulare (Wertung und Zeitplan selbst sind zwar auch schon
ueber /wertung/ und /zeitplan/ ohne Login erreichbar, dort aber eingebettet
in die vollstaendige Organisator-Navigation - diese Seite ist bewusst
reduziert fuer Gaeste am Handy)."""
from flask import Blueprint, jsonify, render_template

from ..models import Team, Disziplin, Startplatz, Strafe
from ..wertung import (gesamtwertung_vollstaendig, team_challenge,
                       beste_einzelzeit)
from .zeitplan import _startplaetze_numerisch_sortieren

bp = Blueprint("besucher", __name__, url_prefix="/besucher")


def _besucher_daten() -> dict:
    """Daten fuer die live aktualisierten Bereiche der Besucheransicht
    (Gesamtwertung, Team Challenge, Zeitplan)."""
    disziplinen = Disziplin.query.order_by(Disziplin.reihenfolge,
                                            Disziplin.name).all()
    teams = Team.query.all()
    tabelle = gesamtwertung_vollstaendig(teams, disziplinen)
    challenge_tabelle = team_challenge(teams)

    # Strafsekunden je Team - auch je einzelnem Lauf (Vorrunde,
    # Platzierungslauf, Halbfinale, Finale) mit angezeigt, nicht nur in der
    # Gesamtwertung oben.
    strafsekunden: dict[int, float] = {}
    for s in Strafe.query.all():
        strafsekunden[s.team_id] = strafsekunden.get(s.team_id, 0.0) + s.sekunden

    zeitplan = []
    for d in disziplinen:
        startplaetze = (Startplatz.query.filter_by(disziplin_id=d.id)
                        .order_by(Startplatz.heat, Startplatz.startnummer).all())
        startplaetze = _startplaetze_numerisch_sortieren(startplaetze)
        if startplaetze:
            zeitplan.append({"disziplin": d, "startplaetze": startplaetze})

    return dict(tabelle=tabelle, team_challenge_tabelle=challenge_tabelle,
               beste_einzelzeit=beste_einzelzeit(),
               zeitplan=zeitplan, strafsekunden=strafsekunden)


@bp.route("/")
def index():
    return render_template("besucher/index.html", **_besucher_daten())


@bp.route("/live-fragment")
def live_fragment():
    """Liefert Gesamtwertung/Team-Challenge und Zeitplan als HTML-Fragmente
    (per JS-Polling eingebettet, kein Login noetig) - fuer Dauerbetrieb auf
    Anzeige-Screens ohne sichtbaren Seiten-Reload alle paar Sekunden."""
    daten = _besucher_daten()
    return jsonify(
        wertung_html=render_template("besucher/_wertung.html", **daten),
        zeitplan_html=render_template("besucher/_zeitplan.html", **daten),
    )
