"""Notfall-Zeiterfassung: der Startrichter/Organisator trägt vorab die
Team-Besetzung je Bahn ein. Wird ein Lauf zusätzlich AKTIVIERT, ordnet
app/blueprints/zeitmessung.py eingehende Kontaktereignisse (ESP32 oder
Desktop-App/Arduino-Mega) automatisch zu und füllt die Läuferzeiten selbst
aus. Ohne Aktivierung (oder falls die Automatik ausfällt) bleibt die
Handeingabe hier der Fallback."""
from datetime import datetime

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


@bp.route("/<int:lauf_id>/aktivieren", methods=["POST"])
@rolle_noetig("startrichter", "organisator")
def aktivieren(lauf_id: int):
    """Markiert diesen Lauf als aktiv für die automatische Zuordnung.

    Es kann immer nur EIN Lauf gleichzeitig aktiv sein - ein vorher aktiver
    Lauf wird automatisch deaktiviert (seine bereits zugeordneten Zeiten
    bleiben erhalten, nur neue Ereignisse werden ihm nicht mehr zugeordnet).
    """
    l = db.get_or_404(NotfallLauf, lauf_id)
    NotfallLauf.query.filter(NotfallLauf.id != lauf_id).update({"aktiv": False})
    l.aktiv = True
    l.aktiviert_um = datetime.utcnow()
    db.session.commit()
    flash(f"Lauf „{l.bezeichnung or l.id}“ ist jetzt aktiv - neue Kontaktereignisse "
          f"werden automatisch zugeordnet.", "ok")
    return redirect(url_for("notfall.lauf", lauf_id=lauf_id))


@bp.route("/<int:lauf_id>/deaktivieren", methods=["POST"])
@rolle_noetig("startrichter", "organisator")
def deaktivieren(lauf_id: int):
    l = db.get_or_404(NotfallLauf, lauf_id)
    l.aktiv = False
    db.session.commit()
    flash("Automatische Zuordnung für diesen Lauf deaktiviert.", "ok")
    return redirect(url_for("notfall.lauf", lauf_id=lauf_id))


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
