"""Anmeldung / Abmeldung für die Organisator-Mannschaft."""
from flask import (Blueprint, flash, redirect, render_template, request,
                   url_for)
from flask_login import login_user, logout_user, login_required, current_user

from ..models import db, _jetzt
from ..auth import authentifiziere

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
            flash(f"Angemeldet als {benutzer.name or benutzer.username}.", "ok")
            return redirect(_sicheres_ziel(ziel))
        flash("Benutzername oder Passwort falsch.", "error")
    return render_template("anmelden.html", ziel=ziel)


@bp.route("/abmelden", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("Abgemeldet.", "ok")
    return redirect(url_for("start.index"))
