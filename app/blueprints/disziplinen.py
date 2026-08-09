"""Verwaltung der Disziplinen / Stationen."""
from flask import (Blueprint, flash, redirect, render_template, request,
                   url_for)

from ..models import db, Disziplin, WERTUNG_ZEIT, WERTUNG_PUNKTE
from ..auth import bearbeiter_noetig

bp = Blueprint("disziplinen", __name__, url_prefix="/disziplinen")


@bp.route("/")
def liste():
    disziplinen = Disziplin.query.order_by(Disziplin.reihenfolge,
                                           Disziplin.name).all()
    return render_template("disziplinen/liste.html", disziplinen=disziplinen)


@bp.route("/neu", methods=["GET", "POST"])
@bearbeiter_noetig
def neu():
    if request.method == "POST":
        d = _aus_formular(Disziplin())
        if not d.name:
            flash("Name der Disziplin fehlt.", "error")
        else:
            db.session.add(d)
            db.session.commit()
            flash(f"Disziplin „{d.name}“ angelegt.", "ok")
            return redirect(url_for("disziplinen.liste"))
        return render_template("disziplinen/bearbeiten.html", disziplin=d)
    return render_template("disziplinen/bearbeiten.html", disziplin=None)


@bp.route("/<int:disziplin_id>/bearbeiten", methods=["GET", "POST"])
@bearbeiter_noetig
def bearbeiten(disziplin_id: int):
    d = db.get_or_404(Disziplin, disziplin_id)
    if request.method == "POST":
        _aus_formular(d)
        db.session.commit()
        flash("Disziplin gespeichert.", "ok")
        return redirect(url_for("disziplinen.liste"))
    return render_template("disziplinen/bearbeiten.html", disziplin=d)


@bp.route("/<int:disziplin_id>/loeschen", methods=["POST"])
@bearbeiter_noetig
def loeschen(disziplin_id: int):
    d = db.get_or_404(Disziplin, disziplin_id)
    db.session.delete(d)
    db.session.commit()
    flash("Disziplin gelöscht.", "ok")
    return redirect(url_for("disziplinen.liste"))


def _aus_formular(d: Disziplin) -> Disziplin:
    d.name = request.form["name"].strip()
    d.beschreibung = request.form.get("beschreibung", "").strip()
    art = request.form.get("wertungsart", WERTUNG_ZEIT)
    d.wertungsart = art if art in (WERTUNG_ZEIT, WERTUNG_PUNKTE) else WERTUNG_ZEIT
    try:
        d.strafsekunden_pro_fehler = float(
            request.form.get("strafsekunden_pro_fehler", "0") or 0)
    except ValueError:
        d.strafsekunden_pro_fehler = 0.0
    try:
        d.reihenfolge = int(request.form.get("reihenfolge", "0") or 0)
    except ValueError:
        d.reihenfolge = 0
    return d
