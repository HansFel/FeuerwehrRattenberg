"""Verwaltung der Mannschaften."""
from flask import (Blueprint, flash, redirect, render_template, request,
                   url_for)

from ..models import db, Team, Mitglied
from ..auth import rolle_noetig

bp = Blueprint("teams", __name__, url_prefix="/teams")

MAX_PERSONEN = 4


@bp.route("/")
def liste():
    teams = Team.query.order_by(Team.startnummer.isnot(None).desc(),
                                Team.startnummer, Team.name).all()
    return render_template("teams/liste.html", teams=teams)


@bp.route("/neu", methods=["GET", "POST"])
@rolle_noetig("organisator")
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
            return render_template("teams/bearbeiten.html", team=None,
                                   personen=_personen_aus_formular())
        _mitglieder_uebernehmen(team)
        db.session.add(team)
        db.session.commit()
        flash(f"Mannschaft „{team.name}“ angelegt.", "ok")
        return redirect(url_for("teams.liste"))
    return render_template("teams/bearbeiten.html", team=None,
                           personen=[""] * MAX_PERSONEN)


@bp.route("/<int:team_id>/bearbeiten", methods=["GET", "POST"])
@rolle_noetig("organisator")
def bearbeiten(team_id: int):
    team = db.get_or_404(Team, team_id)
    if request.method == "POST":
        team.name = request.form["name"].strip()
        team.wehr = request.form.get("wehr", "").strip()
        team.kontakt = request.form.get("kontakt", "").strip()
        team.notiz = request.form.get("notiz", "").strip()
        team.startnummer = _int_or_none(request.form.get("startnummer"))
        _mitglieder_uebernehmen(team)
        db.session.commit()
        flash("Mannschaft gespeichert.", "ok")
        return redirect(url_for("teams.liste"))
    personen = [m.name for m in team.mitglieder]
    personen += [""] * (MAX_PERSONEN - len(personen))
    return render_template("teams/bearbeiten.html", team=team,
                           personen=personen[:MAX_PERSONEN])


@bp.route("/<int:team_id>/loeschen", methods=["POST"])
@rolle_noetig("organisator")
def loeschen(team_id: int):
    team = db.get_or_404(Team, team_id)
    db.session.delete(team)
    db.session.commit()
    flash("Mannschaft gelöscht.", "ok")
    return redirect(url_for("teams.liste"))


def _personen_aus_formular() -> list[str]:
    return [request.form.get(f"person_{i}", "").strip()
            for i in range(1, MAX_PERSONEN + 1)]


def _mitglieder_uebernehmen(team: Team) -> None:
    """Setzt die (bis zu 4) Team-Mitglieder aus dem Formular neu."""
    team.mitglieder.clear()   # cascade delete-orphan entfernt alte Einträge
    for pos, name in enumerate(_personen_aus_formular(), start=1):
        if name:
            team.mitglieder.append(Mitglied(name=name, position=pos))


def _int_or_none(wert):
    try:
        return int(wert)
    except (TypeError, ValueError):
        return None
