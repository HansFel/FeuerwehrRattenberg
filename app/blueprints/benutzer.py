"""Personen- und Rollenverwaltung der Organisator-Mannschaft (nur Administrator).

Muster aus MGRSoftware übernommen: Personen (Benutzer mit Login) werden als
Stammdaten angelegt; Rollen werden auf einer eigenen Seite per Dropdown
zugewiesen (Person + Rolle auswählen → „Zuweisen").
"""
from flask import (Blueprint, flash, redirect, render_template, request,
                   url_for)
from flask_login import current_user

from ..models import db, Benutzer, BenutzerRolle, ROLLEN
from ..auth import rolle_noetig

bp = Blueprint("benutzer", __name__, url_prefix="/benutzer")


# ── Personen (Benutzer mit Login) ────────────────────────────────────────────

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
            db.session.add(b)
            db.session.commit()
            flash(f"Person „{username}“ angelegt. Rollen unter „Rollen“ "
                  "zuweisen.", "ok")
            return redirect(url_for("benutzer.liste"))
    return render_template("benutzer/bearbeiten.html", benutzer=None)


@bp.route("/<int:benutzer_id>/bearbeiten", methods=["GET", "POST"])
@rolle_noetig("administrator")
def bearbeiten(benutzer_id: int):
    b = db.get_or_404(Benutzer, benutzer_id)
    if request.method == "POST":
        b.name = request.form.get("name", "").strip()
        neu_aktiv = bool(request.form.get("aktiv"))
        neues_pw = request.form.get("passwort", "")
        if neues_pw:
            if len(neues_pw) < 4:
                flash("Passwort muss mindestens 4 Zeichen haben.", "error")
                return render_template("benutzer/bearbeiten.html", benutzer=b)
            b.set_password(neues_pw)
        # Letzter aktiver Administrator darf nicht deaktiviert werden
        if not neu_aktiv and b.ist_admin() and _anzahl_aktive_admins() <= 1:
            flash("Der letzte aktive Administrator kann nicht deaktiviert "
                  "werden.", "error")
        else:
            b.aktiv = neu_aktiv
        db.session.commit()
        flash("Person gespeichert.", "ok")
        return redirect(url_for("benutzer.liste"))
    return render_template("benutzer/bearbeiten.html", benutzer=b)


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
    flash("Person gelöscht.", "ok")
    return redirect(url_for("benutzer.liste"))


# ── Rollen-Verwaltung per Dropdown (wie in MGRSoftware) ──────────────────────

@bp.route("/rollen")
@rolle_noetig("administrator")
def rollen():
    zuweisungen = (BenutzerRolle.query
                   .join(Benutzer)
                   .order_by(Benutzer.username, BenutzerRolle.rolle).all())
    personen = Benutzer.query.order_by(Benutzer.username).all()
    return render_template("benutzer/rollen.html", zuweisungen=zuweisungen,
                           personen=personen, ROLLEN=ROLLEN)


@bp.route("/rollen/neu", methods=["POST"])
@rolle_noetig("administrator")
def rolle_zuweisen():
    benutzer_id = request.form.get("benutzer_id", type=int)
    rolle = request.form.get("rolle", "")
    benutzer = db.session.get(Benutzer, benutzer_id) if benutzer_id else None

    if not benutzer or rolle not in ROLLEN:
        flash("Bitte Person und Rolle auswählen.", "error")
    elif rolle in benutzer.rollen_namen:
        flash("Diese Rolle ist der Person bereits zugewiesen.", "error")
    else:
        benutzer.rollen.append(BenutzerRolle(rolle=rolle))
        db.session.commit()
        flash(f"Rolle „{ROLLEN[rolle]}“ an {benutzer.username} zugewiesen.",
              "ok")
    return redirect(url_for("benutzer.rollen"))


@bp.route("/rollen/<int:rolle_id>/loeschen", methods=["POST"])
@rolle_noetig("administrator")
def rolle_entfernen(rolle_id: int):
    zuweisung = db.get_or_404(BenutzerRolle, rolle_id)
    # Letzte Administrator-Rolle im System schützen
    if (zuweisung.rolle == "administrator" and zuweisung.benutzer.aktiv
            and _anzahl_aktive_admins() <= 1):
        flash("Die letzte Administrator-Rolle kann nicht entfernt werden.",
              "error")
        return redirect(url_for("benutzer.rollen"))
    db.session.delete(zuweisung)
    db.session.commit()
    flash("Rolle entfernt.", "ok")
    return redirect(url_for("benutzer.rollen"))


def _anzahl_aktive_admins() -> int:
    return sum(1 for b in Benutzer.query.all() if b.aktiv and b.ist_admin())
