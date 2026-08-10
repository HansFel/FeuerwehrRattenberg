"""Mitteilungen eines Administrators an andere Personen der
Organisator-Mannschaft ("worüber sollen sie nachdenken").

Senden ist Administratoren vorbehalten; Lesen/Als-gelesen-markieren kann
jede angemeldete Person für die an sie gerichteten Nachrichten.
"""
from flask import Blueprint, flash, redirect, request, url_for
from flask_login import current_user, login_required

from ..models import db, Benutzer, Nachricht, NachrichtGelesen, ROLLEN
from ..auth import rolle_noetig

bp = Blueprint("nachrichten", __name__, url_prefix="/nachrichten")


def fuer_benutzer(benutzer, nur_ungelesen: bool = False) -> list[Nachricht]:
    alle = Nachricht.query.order_by(Nachricht.erstellt.desc()).all()
    passende = [n for n in alle if n.richtet_sich_an(benutzer)]
    if nur_ungelesen:
        passende = [n for n in passende if not n.ist_gelesen_von(benutzer.id)]
    return passende


@bp.route("/senden", methods=["POST"])
@rolle_noetig("administrator")
def senden():
    text = request.form.get("text", "").strip()
    ziel = request.form.get("ziel", "alle")

    if not text:
        flash("Bitte einen Nachrichtentext eingeben.", "error")
        return redirect(url_for("anforderungen.index"))

    n = Nachricht(text=text, absender=current_user.username)
    if ziel.startswith("rolle:"):
        rolle = ziel.split(":", 1)[1]
        if rolle not in ROLLEN:
            flash("Unbekannte Rolle als Ziel.", "error")
            return redirect(url_for("anforderungen.index"))
        n.ziel_rolle = rolle
    elif ziel.startswith("person:"):
        benutzer_id = int(ziel.split(":", 1)[1])
        if not db.session.get(Benutzer, benutzer_id):
            flash("Unbekannte Person als Ziel.", "error")
            return redirect(url_for("anforderungen.index"))
        n.ziel_benutzer_id = benutzer_id
    # sonst: "alle" -> kein Ziel gesetzt

    db.session.add(n)
    db.session.commit()
    flash("Nachricht gesendet.", "ok")
    return redirect(url_for("anforderungen.index"))


@bp.route("/<int:nachricht_id>/loeschen", methods=["POST"])
@rolle_noetig("administrator")
def loeschen(nachricht_id: int):
    n = db.get_or_404(Nachricht, nachricht_id)
    db.session.delete(n)
    db.session.commit()
    flash("Nachricht gelöscht.", "ok")
    return redirect(url_for("anforderungen.index"))


@bp.route("/<int:nachricht_id>/gelesen", methods=["POST"])
@login_required
def gelesen(nachricht_id: int):
    n = db.get_or_404(Nachricht, nachricht_id)
    if n.richtet_sich_an(current_user) and not n.ist_gelesen_von(current_user.id):
        db.session.add(NachrichtGelesen(nachricht_id=n.id,
                                        benutzer_id=current_user.id))
        db.session.commit()
    ziel = request.form.get("next")
    if ziel and ziel.startswith("/") and not ziel.startswith("//"):
        return redirect(ziel)
    return redirect(url_for("start.index"))
