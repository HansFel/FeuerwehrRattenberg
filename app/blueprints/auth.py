"""Anmeldung / Abmeldung für die Organisator-Mannschaft."""
from flask import (Blueprint, flash, redirect, render_template, request,
                   session, url_for)
from flask_login import login_user, logout_user, login_required, current_user

from ..models import db, ROLLEN, _jetzt
from ..auth import authentifiziere, setze_aktive_rolle, SESSION_ROLLE

bp = Blueprint("auth", __name__)


def _sicheres_ziel(ziel: str | None) -> str:
    """Nur lokale Pfade zulassen (kein Open-Redirect)."""
    if ziel and ziel.startswith("/") and not ziel.startswith("//"):
        return ziel
    return url_for("start.index")


@bp.route("/anmelden", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("start.index"))

    ziel = request.values.get("next")
    if request.method == "POST":
        benutzer = authentifiziere(request.form.get("username", "").strip(),
                                   request.form.get("passwort", ""))
        if benutzer:
            login_user(benutzer)
            benutzer.letzter_login = _jetzt()
            db.session.commit()
            session.pop(SESSION_ROLLE, None)
            flash(f"Angemeldet als {benutzer.name or benutzer.username}.", "ok")
            rollen = benutzer.rollen_namen
            if len(rollen) == 1:
                session[SESSION_ROLLE] = rollen[0]
                return redirect(_sicheres_ziel(ziel))
            if len(rollen) > 1:
                # Mehrere Rollen: Mitarbeiter wählt seine aktive Rolle
                return redirect(url_for("auth.rolle_waehlen", next=ziel))
            return redirect(_sicheres_ziel(ziel))
        flash("Benutzername oder Passwort falsch.", "error")
    return render_template("anmelden.html", ziel=ziel)


@bp.route("/rolle-waehlen")
@login_required
def rolle_waehlen():
    """Auswahl der aktiven Rolle, wenn der Mitarbeiter mehrere Rollen hat."""
    rollen = current_user.rollen_namen
    if len(rollen) <= 1:
        if rollen:
            setze_aktive_rolle(rollen[0])
        return redirect(url_for("start.index"))
    return render_template("rolle_waehlen.html", rollen=rollen, ROLLEN=ROLLEN,
                           ziel=request.values.get("next"))


@bp.route("/rolle-setzen", methods=["POST"])
@login_required
def rolle_setzen():
    """Speichert die gewählte aktive Rolle in der Session."""
    rolle = request.form.get("rolle", "")
    if setze_aktive_rolle(rolle):
        flash(f"Aktive Rolle: {ROLLEN.get(rolle, rolle)}.", "ok")
    else:
        flash("Diese Rolle ist dir nicht zugewiesen.", "error")
    ziel = request.form.get("next")
    if ziel and ziel.startswith("/") and not ziel.startswith("//"):
        return redirect(ziel)
    return redirect(url_for("start.index"))


@bp.route("/abmelden", methods=["POST"])
@login_required
def logout():
    session.pop(SESSION_ROLLE, None)
    logout_user()
    flash("Abgemeldet.", "ok")
    return redirect(url_for("start.index"))
