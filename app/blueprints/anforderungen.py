"""Anforderungen an die App – Wünsche/Regeln der Administratoren.

Administratoren tragen hier Wünsche, Regeln und Ideen für die
Weiterentwicklung ein. Die Einträge werden in der Datenbank gespeichert und
zusätzlich bei jeder Änderung nach ``ANFORDERUNGEN.md`` im Projektstamm
exportiert, damit sie automatisch (auch von der Entwicklung) gelesen werden
können.
"""
import os

from flask import (Blueprint, current_app, flash, redirect, render_template,
                   request, url_for)
from flask_login import current_user

from ..models import db, Anforderung, Benutzer, Nachricht, ROLLEN
from ..auth import rolle_noetig

bp = Blueprint("anforderungen", __name__, url_prefix="/anforderungen")


def _eintraege():
    return (Anforderung.query
            .order_by(Anforderung.erledigt, Anforderung.erstellt.desc()).all())


@bp.route("/")
@rolle_noetig("administrator")
def index():
    personen = Benutzer.query.order_by(Benutzer.username).all()
    nachrichten = Nachricht.query.order_by(Nachricht.erstellt.desc()).all()
    return render_template("anforderungen/index.html", eintraege=_eintraege(),
                           personen=personen, nachrichten=nachrichten,
                           ROLLEN=ROLLEN)


@bp.route("/neu", methods=["POST"])
@rolle_noetig("administrator")
def neu():
    text = request.form.get("text", "").strip()
    if not text:
        flash("Bitte einen Text eingeben.", "error")
    else:
        db.session.add(Anforderung(text=text, autor=current_user.username))
        db.session.commit()
        _exportieren()
        flash("Anforderung gespeichert.", "ok")
    return redirect(url_for("anforderungen.index"))


@bp.route("/<int:anforderung_id>/erledigt", methods=["POST"])
@rolle_noetig("administrator")
def erledigt(anforderung_id: int):
    a = db.get_or_404(Anforderung, anforderung_id)
    a.erledigt = not a.erledigt
    db.session.commit()
    _exportieren()
    return redirect(url_for("anforderungen.index"))


@bp.route("/<int:anforderung_id>/loeschen", methods=["POST"])
@rolle_noetig("administrator")
def loeschen(anforderung_id: int):
    a = db.get_or_404(Anforderung, anforderung_id)
    db.session.delete(a)
    db.session.commit()
    _exportieren()
    flash("Anforderung gelöscht.", "ok")
    return redirect(url_for("anforderungen.index"))


def _exportieren() -> None:
    """Schreibt alle Anforderungen als Markdown in den Projektstamm.

    Läuft best-effort: schlägt das Schreiben fehl (z.B. schreibgeschützter
    Container), bleibt der DB-Eintrag trotzdem erhalten.
    """
    offen = [e for e in _eintraege() if not e.erledigt]
    erledigt = [e for e in _eintraege() if e.erledigt]

    zeilen = [
        "# Anforderungen an die App",
        "",
        "<!-- Automatisch aus der App exportiert (Bereich Anforderungen).",
        "     Von Administratoren gepflegt; hier NICHT von Hand editieren. -->",
        "",
        f"## Offen ({len(offen)})",
        "",
    ]
    zeilen += [_als_markdown(e) for e in offen] or ["_(keine offenen Einträge)_"]
    zeilen += ["", f"## Erledigt ({len(erledigt)})", ""]
    zeilen += [_als_markdown(e) for e in erledigt] or ["_(keine)_"]
    inhalt = "\n".join(zeilen) + "\n"

    pfad = current_app.config.get("ANFORDERUNGEN_PFAD") or os.path.join(
        os.path.dirname(current_app.root_path), "ANFORDERUNGEN.md")
    try:
        with open(pfad, "w", encoding="utf-8") as f:
            f.write(inhalt)
    except OSError as e:
        current_app.logger.warning("Export ANFORDERUNGEN.md fehlgeschlagen: %s", e)


def _als_markdown(e: Anforderung) -> str:
    kasten = "x" if e.erledigt else " "
    datum = e.erstellt.strftime("%d.%m.%Y") if e.erstellt else ""
    kopf = f"- [{kasten}] **{e.autor or '?'}** · {datum}"
    # mehrzeiligen Text eingerückt anhängen
    text = e.text.strip().replace("\r\n", "\n")
    eingerueckt = "\n".join("  " + z for z in text.split("\n"))
    return f"{kopf}\n{eingerueckt}"
