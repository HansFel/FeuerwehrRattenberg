"""Verwaltung der Mannschaften."""
from flask import (Blueprint, flash, redirect, render_template, request,
                   url_for)

from ..models import db, Team
from ..auth import bearbeiter_noetig

bp = Blueprint("teams", __name__, url_prefix="/teams")


@bp.route("/")
def liste():
    teams = Team.query.order_by(Team.startnummer.isnot(None).desc(),
                                Team.startnummer, Team.name).all()
    return render_template("teams/liste.html", teams=teams)


@bp.route("/neu", methods=["GET", "POST"])
@bearbeiter_noetig
def neu():
    if request.method == "POST":
        team = Team(
            name=request.form["name"].strip(),
            wehr=request.form.get("wehr", "").strip(),
            kontakt=request.form.get("kontakt", "").strip(),
            notiz=request.form.get("notiz", "").strip(),
            startnummer=_int_or_none(request.form.get("startnummer")),
        )
        if not team.name:
            flash("Name der Mannschaft fehlt.", "error")
        else:
            db.session.add(team)
            db.session.commit()
            flash(f"Mannschaft „{team.name}“ angelegt.", "ok")
            return redirect(url_for("teams.liste"))
    return render_template("teams/bearbeiten.html", team=None)


@bp.route("/<int:team_id>/bearbeiten", methods=["GET", "POST"])
@bearbeiter_noetig
def bearbeiten(team_id: int):
    team = db.get_or_404(Team, team_id)
    if request.method == "POST":
        team.name = request.form["name"].strip()
        team.wehr = request.form.get("wehr", "").strip()
        team.kontakt = request.form.get("kontakt", "").strip()
        team.notiz = request.form.get("notiz", "").strip()
        team.startnummer = _int_or_none(request.form.get("startnummer"))
        db.session.commit()
        flash("Mannschaft gespeichert.", "ok")
        return redirect(url_for("teams.liste"))
    return render_template("teams/bearbeiten.html", team=team)


@bp.route("/<int:team_id>/loeschen", methods=["POST"])
@bearbeiter_noetig
def loeschen(team_id: int):
    team = db.get_or_404(Team, team_id)
    db.session.delete(team)
    db.session.commit()
    flash("Mannschaft gelöscht.", "ok")
    return redirect(url_for("teams.liste"))


def _int_or_none(wert):
    try:
        return int(wert)
    except (TypeError, ValueError):
        return None
