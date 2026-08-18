"""Datensicherung – Übersicht, Erstellen, Herunterladen, Hochladen,
Wiederherstellen, Löschen (nur Administrator)."""
import os

from flask import (Blueprint, flash, redirect, render_template, request,
                   send_file, url_for)
from flask_login import current_user

from .. import sicherung as dienst
from ..auth import rolle_noetig

bp = Blueprint("sicherung", __name__, url_prefix="/sicherung")


@bp.route("/")
@rolle_noetig("administrator")
def index():
    return render_template("sicherung/index.html", sicherungen=dienst.liste())


@bp.route("/erstellen", methods=["POST"])
@rolle_noetig("administrator")
def erstellen():
    try:
        s = dienst.erstellen(typ="manuell", von=current_user.username)
        flash(f"Sicherung erstellt: {s.dateiname} ({s.groesse_formatiert}).",
              "ok")
    except Exception as e:  # noqa: BLE001 – Fehler dem Admin zeigen
        flash(f"Sicherung fehlgeschlagen: {e}", "error")
    return redirect(url_for("sicherung.index"))


@bp.route("/<int:sicherung_id>/download")
@rolle_noetig("administrator")
def download(sicherung_id: int):
    s, pfad = dienst.pfad_fuer(sicherung_id)
    if not os.path.exists(pfad):
        flash(f"Datei „{s.dateiname}“ fehlt auf dem Server (z.B. nach einem "
              "Container-Neustart ohne dauerhaften Speicher). Der Eintrag "
              "kann über „Löschen“ entfernt werden.", "error")
        return redirect(url_for("sicherung.index"))
    return send_file(pfad, as_attachment=True, download_name=s.dateiname)


@bp.route("/hochladen", methods=["POST"])
@rolle_noetig("administrator")
def hochladen():
    try:
        dienst.hochladen(request.files.get("datei"), von=current_user.username)
        flash("Sicherung hochgeladen.", "ok")
    except Exception as e:  # noqa: BLE001
        flash(f"Hochladen fehlgeschlagen: {e}", "error")
    return redirect(url_for("sicherung.index"))


@bp.route("/<int:sicherung_id>/wiederherstellen", methods=["POST"])
@rolle_noetig("administrator")
def wiederherstellen(sicherung_id: int):
    try:
        dienst.wiederherstellen(sicherung_id)
        flash("Datenbank wiederhergestellt. Der aktuelle Stand wurde vorher "
              "automatisch gesichert.", "ok")
    except Exception as e:  # noqa: BLE001
        flash(f"Wiederherstellung fehlgeschlagen: {e}", "error")
    return redirect(url_for("sicherung.index"))


@bp.route("/<int:sicherung_id>/loeschen", methods=["POST"])
@rolle_noetig("administrator")
def loeschen(sicherung_id: int):
    dienst.loeschen(sicherung_id)
    flash("Sicherung gelöscht.", "ok")
    return redirect(url_for("sicherung.index"))


@bp.route("/testdaten-loeschen", methods=["POST"])
@rolle_noetig("administrator")
def testdaten_loeschen():
    try:
        dienst.erstellen(typ="vor-testdaten-loeschen", von=current_user.username)
        anzahl = dienst.testdaten_loeschen()
        flash(
            f"Testdaten gelöscht: {anzahl['zeitereignisse']} Zeitereignisse, "
            f"{anzahl['notfalllaeufe']} Läufe, {anzahl['bestellungen']} "
            f"Bestellungen, {anzahl['strafen']} Strafen, "
            f"{anzahl['ergebnisse']} Ergebnisse. Teams, Mitglieder und "
            "Speisekarte sind unverändert. Der vorherige Stand wurde "
            "automatisch gesichert.", "ok")
    except Exception as e:  # noqa: BLE001
        flash(f"Löschen der Testdaten fehlgeschlagen: {e}", "error")
    return redirect(url_for("sicherung.index"))
