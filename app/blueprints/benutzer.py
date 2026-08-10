"""Benutzerverwaltung der Organisator-Mannschaft (nur Administrator)."""
from flask import (Blueprint, flash, redirect, render_template, request,
                   url_for)
from flask_login import current_user

from ..models import db, Benutzer, BenutzerRolle, ROLLEN
from ..auth import rolle_noetig

bp = Blueprint("benutzer", __name__, url_prefix="/benutzer")


@bp.route("/")
@rolle_noetig("administrator")
def liste():
    benutzer = Benutzer.query.order_by(Benutzer.username).all()
    return render_template("benutzer/liste.html", benutzer=benutzer,
                           ROLLEN=ROLLEN)


@bp.route("/neu", methods=["GET", "POST"])
@rolle_noetig("administrator")
def neu():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        passwort = request.form.get("passwort", "")
        if not username:
            flash("Benutzername fehlt.", "error")
        elif Benutzer.query.filter_by(username=username).first():
            flash("Benutzername ist bereits vergeben.", "error")
        elif len(passwort) < 4:
            flash("Passwort muss mindestens 4 Zeichen haben.", "error")
        else:
            b = Benutzer(username=username,
                         name=request.form.get("name", "").strip(),
                         aktiv=bool(request.form.get("aktiv")))
            b.set_password(passwort)
            _rollen_setzen(b)
            db.session.add(b)
            db.session.commit()
            flash(f"Benutzer „{username}“ angelegt.", "ok")
            return redirect(url_for("benutzer.liste"))
    return render_template("benutzer/bearbeiten.html", benutzer=None,
                           ROLLEN=ROLLEN)


@bp.route("/<int:benutzer_id>/bearbeiten", methods=["GET", "POST"])
@rolle_noetig("administrator")
def bearbeiten(benutzer_id: int):
    b = db.get_or_404(Benutzer, benutzer_id)
    if request.method == "POST":
        b.name = request.form.get("name", "").strip()
        b.aktiv = bool(request.form.get("aktiv"))
        neues_pw = request.form.get("passwort", "")
        if neues_pw:
            if len(neues_pw) < 4:
                flash("Passwort muss mindestens 4 Zeichen haben.", "error")
                return render_template("benutzer/bearbeiten.html", benutzer=b,
                                       ROLLEN=ROLLEN)
            b.set_password(neues_pw)
        _rollen_setzen(b)
        _admin_schutz_pruefen(b)
        db.session.commit()
        flash("Benutzer gespeichert.", "ok")
        return redirect(url_for("benutzer.liste"))
    return render_template("benutzer/bearbeiten.html", benutzer=b, ROLLEN=ROLLEN)


@bp.route("/<int:benutzer_id>/loeschen", methods=["POST"])
@rolle_noetig("administrator")
def loeschen(benutzer_id: int):
    b = db.get_or_404(Benutzer, benutzer_id)
    if b.id == current_user.id:
        flash("Du kannst dich nicht selbst löschen.", "error")
        return redirect(url_for("benutzer.liste"))
    if b.ist_admin() and _anzahl_aktive_admins() <= 1:
        flash("Der letzte Administrator kann nicht gelöscht werden.", "error")
        return redirect(url_for("benutzer.liste"))
    db.session.delete(b)
    db.session.commit()
    flash("Benutzer gelöscht.", "ok")
    return redirect(url_for("benutzer.liste"))


def _rollen_setzen(b: Benutzer) -> None:
    gewaehlt = request.form.getlist("rollen")
    b.rollen.clear()
    for r in gewaehlt:
        if r in ROLLEN:
            b.rollen.append(BenutzerRolle(rolle=r))


def _anzahl_aktive_admins() -> int:
    return sum(1 for b in Benutzer.query.all() if b.aktiv and b.ist_admin())


def _admin_schutz_pruefen(b: Benutzer) -> None:
    """Verhindert, dass der letzte aktive Administrator seine Rechte verliert."""
    if _anzahl_aktive_admins() == 0:
        b.aktiv = True
        if not b.ist_admin():
            b.rollen.append(BenutzerRolle(rolle="administrator"))
        flash("Hinweis: Es muss mindestens ein aktiver Administrator bleiben "
              "– Rolle/Status wurde beibehalten.", "error")
