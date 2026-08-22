"""Zeiten/Punkte erfassen und Ranglisten anzeigen."""
from flask import (Blueprint, flash, redirect, render_template, request,
                   url_for)

from ..models import db, Team, Disziplin, Ergebnis, WERTUNG_ZEIT
from ..wertung import (rangliste_disziplin, gesamtwertung_vollstaendig,
                       team_challenge, beste_einzelzeit)
from ..auth import darf, rolle_noetig

bp = Blueprint("wertung", __name__, url_prefix="/wertung")


@bp.route("/", methods=["GET", "POST"])
def uebersicht():
    disziplinen = Disziplin.query.order_by(Disziplin.reihenfolge,
                                            Disziplin.name).all()
    teams = Team.query.all()
    tabelle = gesamtwertung_vollstaendig(teams, disziplinen)

    # Team Challenge: Getraenkepunkte + Fanpunkte je Team, live gereiht
    challenge_tabelle = team_challenge(teams)

    if request.method == "POST" and darf("organisator"):
        for team in teams:
            wert = request.form.get(f"fanpunkte_{team.id}", type=int)
            if wert is not None:
                team.fanpunkte = wert
        db.session.commit()
        flash("Fanpunkte aktualisiert.", "ok")
        return redirect(url_for("wertung.uebersicht"))

    return render_template("wertung/uebersicht.html",
                           disziplinen=disziplinen, tabelle=tabelle,
                           team_challenge=challenge_tabelle,
                           beste_einzelzeit=beste_einzelzeit())


@bp.route("/disziplin/<int:disziplin_id>", methods=["GET", "POST"])
def erfassen(disziplin_id: int):
    disziplin = db.get_or_404(Disziplin, disziplin_id)

    if request.method == "POST":
        if not darf("punkterichter"):
            flash("Zum Erfassen von Ergebnissen brauchst du die Rolle "
                  "Punkterichter (oder Administrator).", "error")
            return redirect(url_for("auth.login",
                                    next=url_for("wertung.erfassen",
                                                 disziplin_id=disziplin.id)))
        team_id = int(request.form["team_id"])
        erg = Ergebnis.query.filter_by(team_id=team_id,
                                       disziplin_id=disziplin.id).first()
        if erg is None:
            erg = Ergebnis(team_id=team_id, disziplin_id=disziplin.id)
            db.session.add(erg)

        erg.zeit_sekunden = _float_or_none(request.form.get("zeit_sekunden"))
        erg.punkte = _float_or_none(request.form.get("punkte"))
        erg.fehlerpunkte = _int_or_zero(request.form.get("fehlerpunkte"))
        erg.disqualifiziert = bool(request.form.get("disqualifiziert"))
        erg.notiz = request.form.get("notiz", "").strip()
        db.session.commit()
        flash("Ergebnis gespeichert.", "ok")
        return redirect(url_for("wertung.erfassen", disziplin_id=disziplin.id))

    platzierungen = rangliste_disziplin(disziplin)
    erfasste = {p.team.id: p.ergebnis for p in platzierungen}
    teams = Team.query.order_by(Team.name).all()
    return render_template("wertung/erfassen.html", disziplin=disziplin,
                           platzierungen=platzierungen, teams=teams,
                           erfasste=erfasste, ist_zeit=disziplin.wertungsart
                           == WERTUNG_ZEIT)


def _float_or_none(wert):
    if wert is None or str(wert).strip() == "":
        return None
    try:
        return float(str(wert).replace(",", "."))
    except ValueError:
        return None


def _int_or_zero(wert):
    try:
        return int(wert)
    except (TypeError, ValueError):
        return 0


