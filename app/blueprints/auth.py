"""Anmeldung / Abmeldung für Bearbeiter."""
from flask import (Blueprint, flash, redirect, render_template, request,
                   session, url_for)

from ..auth import passwort_korrekt

bp = Blueprint("auth", __name__)


def _sicheres_ziel(ziel: str | None) -> str:
    """Nur lokale Pfade als Weiterleitungsziel zulassen (kein Open-Redirect)."""
    if ziel and ziel.startswith("/") and not ziel.startswith("//"):
        return ziel
    return url_for("start.index")


@bp.route("/anmelden", methods=["GET", "POST"])
def login():
    ziel = request.values.get("next")
    if request.method == "POST":
        if passwort_korrekt(request.form.get("passwort", "")):
            session["bearbeiter"] = True
            flash("Angemeldet – Bearbeitung freigeschaltet.", "ok")
            return redirect(_sicheres_ziel(ziel))
        flash("Falsches Passwort.", "error")
    return render_template("anmelden.html", ziel=ziel)


@bp.route("/abmelden", methods=["POST"])
def logout():
    session.pop("bearbeiter", None)
    flash("Abgemeldet.", "ok")
    return redirect(url_for("start.index"))
