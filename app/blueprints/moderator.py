"""Live-Dashboard für die Moderation und Pflege durch den Organisator."""
import re

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user

from ..auth import rolle_noetig
from ..models import (db, Disziplin, ModeratorStatus, Nachricht, Startplatz, Team)

bp = Blueprint("moderator", __name__, url_prefix="/moderator")


def _status() -> ModeratorStatus:
    status = db.session.get(ModeratorStatus, 1)
    if status is None:
        status = ModeratorStatus(id=1)
        db.session.add(status)
        db.session.commit()
    return status


def _lauf_optionen() -> list[dict]:
    startplaetze = (Startplatz.query.join(Disziplin)
                    .order_by(Disziplin.reihenfolge, Disziplin.name,
                              Startplatz.heat, Startplatz.startnummer).all())
    optionen = []
    gesehen = set()
    for sp in startplaetze:
        heat = (sp.heat or "").strip()
        schluessel = (sp.disziplin_id, heat)
        if schluessel in gesehen:
            continue
        gesehen.add(schluessel)
        optionen.append({
            "wert": f"{sp.disziplin_id}|{heat}",
            "text": f"{sp.disziplin.name} – {heat or 'ohne Laufbezeichnung'}",
        })
    def natuerlich(option):
        return [int(teil) if teil.isdigit() else teil.casefold()
                for teil in re.split(r"(\d+)", option["text"])]
    return sorted(optionen, key=natuerlich)


def _laufende_teams(status: ModeratorStatus) -> list[Startplatz]:
    if not status.disziplin_id:
        return []
    query = Startplatz.query.filter_by(disziplin_id=status.disziplin_id)
    if status.heat:
        query = query.filter_by(heat=status.heat)
    else:
        query = query.filter((Startplatz.heat == "") | (Startplatz.heat.is_(None)))
    return query.order_by(Startplatz.startnummer, Startplatz.id).all()


@bp.route("/")
@rolle_noetig("moderator", "organisator")
def dashboard():
    status = _status()
    nachrichten = (Nachricht.query
                   .filter((Nachricht.ziel_rolle == "moderator") |
                           (Nachricht.ziel_benutzer_id == current_user.id))
                   .order_by(Nachricht.erstellt.desc()).limit(20).all())
    alle_teams = Team.query.order_by(Team.startnummer, Team.name).all()
    return render_template(
        "moderator/dashboard.html", status=status,
        laufende_teams=_laufende_teams(status),
        lauf_optionen=_lauf_optionen(), nachrichten=nachrichten,
        alle_teams=alle_teams)


@bp.route("/status", methods=["POST"])
@rolle_noetig("organisator")
def status_speichern():
    status = _status()
    auswahl = request.form.get("lauf", "")
    if auswahl:
        try:
            disziplin_id_text, heat = auswahl.split("|", 1)
            disziplin_id = int(disziplin_id_text)
        except (ValueError, TypeError):
            flash("Ungültige Laufauswahl.", "error")
            return redirect(url_for("moderator.dashboard"))
        if not db.session.get(Disziplin, disziplin_id):
            flash("Die ausgewählte Disziplin existiert nicht.", "error")
            return redirect(url_for("moderator.dashboard"))
        status.disziplin_id = disziplin_id
        status.heat = heat
    else:
        status.disziplin_id = None
        status.heat = ""
    status.publikumsinfo = request.form.get("publikumsinfo", "").strip()
    status.sponsoren = request.form.get("sponsoren", "").strip()
    status.aktualisiert_von = current_user.username
    db.session.commit()
    flash("Moderator-Anzeige aktualisiert.", "ok")
    return redirect(url_for("moderator.dashboard"))


@bp.route("/nachricht", methods=["POST"])
@rolle_noetig("organisator")
def nachricht_senden():
    text = request.form.get("text", "").strip()
    if not text:
        flash("Bitte einen Nachrichtentext eingeben.", "error")
    else:
        db.session.add(Nachricht(text=text, absender=current_user.username,
                                 ziel_rolle="moderator"))
        db.session.commit()
        flash("Nachricht an die Moderation gesendet.", "ok")
    return redirect(url_for("moderator.dashboard"))
