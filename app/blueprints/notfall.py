"""Manuelle Notfall-Zeiterfassung: falls die automatische Zuordnung der
ESP32-Zeitmessung zu einem Wettkampf-Lauf ausfällt, kann der Startrichter
hier vorab die Team-Besetzung je Bahn eintragen und die Zeiten danach von
Hand erfassen (z.B. abgelesen von der eigenständigen Weboberfläche des
ESP32, die auch bei App-Ausfall unabhängig weiterläuft)."""
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user

from ..models import db, NotfallLauf, NotfallBahn, Team
from ..auth import rolle_noetig

bp = Blueprint("notfall", __name__, url_prefix="/notfall")

ANZAHL_BAHNEN = 4


@bp.route("/")
@rolle_noetig("startrichter", "organisator")
def liste():
    laeufe = NotfallLauf.query.order_by(NotfallLauf.erstellt.desc()).all()
    return render_template("notfall/liste.html", laeufe=laeufe)


@bp.route("/neu", methods=["GET", "POST"])
@rolle_noetig("startrichter", "organisator")
def neu():
    teams = Team.query.order_by(Team.startnummer, Team.name).all()
    if request.method == "POST":
        lauf = NotfallLauf(
            bezeichnung=request.form.get("bezeichnung", "").strip(),
            erstellt_von=current_user.username,
        )
        belegt = False
        for bahn_nr in range(1, ANZAHL_BAHNEN + 1):
            team_id = _int_or_none(request.form.get(f"team_{bahn_nr}"))
            if team_id:
                belegt = True
            lauf.bahnen.append(NotfallBahn(bahn_nr=bahn_nr, team_id=team_id))
        if not belegt:
            flash("Bitte mindestens eine Bahn mit einem Team belegen.", "error")
            return render_template("notfall/neu.html", teams=teams)
        db.session.add(lauf)
        db.session.commit()
        flash("Notfall-Lauf angelegt.", "ok")
        return redirect(url_for("notfall.lauf", lauf_id=lauf.id))
    return render_template("notfall/neu.html", teams=teams)


@bp.route("/<int:lauf_id>", methods=["GET", "POST"])
@rolle_noetig("startrichter", "organisator")
def lauf(lauf_id: int):
    l = db.get_or_404(NotfallLauf, lauf_id)
    if request.method == "POST":
        for bahn in l.bahnen:
            for i in range(1, 5):
                wert = request.form.get(f"zeit_{bahn.id}_{i}", "").strip()
                setattr(bahn, f"zeit_laeufer{i}", _float_or_none(wert))
        db.session.commit()
        flash("Zeiten gespeichert.", "ok")
        return redirect(url_for("notfall.lauf", lauf_id=lauf_id))
    return render_template("notfall/lauf.html", lauf=l)


@bp.route("/<int:lauf_id>/loeschen", methods=["POST"])
@rolle_noetig("organisator")
def loeschen(lauf_id: int):
    l = db.get_or_404(NotfallLauf, lauf_id)
    db.session.delete(l)
    db.session.commit()
    flash("Notfall-Lauf gelöscht.", "ok")
    return redirect(url_for("notfall.liste"))


def _int_or_none(wert):
    try:
        return int(wert) if wert else None
    except (TypeError, ValueError):
        return None


def _float_or_none(wert: str):
    try:
        return float(wert.replace(",", ".")) if wert else None
    except (TypeError, ValueError):
        return None
