"""Startlisten / Zeitplan je Disziplin."""
from flask import (Blueprint, flash, redirect, render_template, request,
                   url_for)

from ..models import db, Team, Disziplin, Startplatz
from ..auth import darf

bp = Blueprint("zeitplan", __name__, url_prefix="/zeitplan")


@bp.route("/")
def uebersicht():
    disziplinen = Disziplin.query.order_by(Disziplin.reihenfolge,
                                            Disziplin.name).all()
    return render_template("zeitplan/uebersicht.html", disziplinen=disziplinen)


@bp.route("/disziplin/<int:disziplin_id>", methods=["GET", "POST"])
def disziplin(disziplin_id: int):
    disziplin = db.get_or_404(Disziplin, disziplin_id)

    if request.method == "POST":
        if not darf("startrichter", "organisator"):
            flash("Zum Ändern der Startliste brauchst du die Rolle "
                  "Startrichter oder Organisator (oder Administrator).", "error")
            return redirect(url_for("auth.login",
                                    next=url_for("zeitplan.disziplin",
                                                 disziplin_id=disziplin.id)))
        aktion = request.form.get("aktion")
        if aktion == "auto":
            _startliste_automatisch(disziplin)
            flash("Startliste aus allen Mannschaften erzeugt.", "ok")
        elif aktion == "speichern":
            _startzeiten_speichern(disziplin)
            flash("Startliste gespeichert.", "ok")
        return redirect(url_for("zeitplan.disziplin", disziplin_id=disziplin.id))

    startplaetze = (Startplatz.query
                    .filter_by(disziplin_id=disziplin.id)
                    .order_by(Startplatz.startnummer).all())
    return render_template("zeitplan/disziplin.html", disziplin=disziplin,
                           startplaetze=startplaetze)


def _startliste_automatisch(disziplin: Disziplin) -> None:
    """Legt für jedes Team ohne Startplatz einen an (fortlaufende Nummer)."""
    vorhanden = {sp.team_id for sp in disziplin.startplaetze}
    naechste = (max((sp.startnummer or 0 for sp in disziplin.startplaetze),
                    default=0) + 1)
    for team in Team.query.order_by(Team.startnummer, Team.name):
        if team.id in vorhanden:
            continue
        db.session.add(Startplatz(team_id=team.id, disziplin_id=disziplin.id,
                                  startnummer=naechste))
        naechste += 1
    db.session.commit()


def _startzeiten_speichern(disziplin: Disziplin) -> None:
    for sp in disziplin.startplaetze:
        sp.startnummer = _int_or_none(request.form.get(f"nr_{sp.id}"))
        sp.startzeit = request.form.get(f"zeit_{sp.id}", "").strip()
        sp.heat = request.form.get(f"heat_{sp.id}", "").strip()
    db.session.commit()


def _int_or_none(wert):
    try:
        return int(wert)
    except (TypeError, ValueError):
        return None
