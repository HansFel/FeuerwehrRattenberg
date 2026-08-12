"""Speisekarte (Essen & Getränke) und Tisch-QR-Code-Aufkleber – Organisator."""
import io

import qrcode
from flask import (Blueprint, Response, flash, redirect, render_template,
                   request, url_for)
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

from ..models import db, Artikel, KATEGORIEN, KATEGORIE_GETRAENK
from ..auth import rolle_noetig

bp = Blueprint("speisekarte", __name__, url_prefix="/speisekarte")


@bp.route("/")
@rolle_noetig("organisator")
def liste():
    artikel = Artikel.query.order_by(Artikel.kategorie, Artikel.reihenfolge,
                                     Artikel.name).all()
    return render_template("speisekarte/liste.html", artikel=artikel,
                           KATEGORIEN=KATEGORIEN)


@bp.route("/neu", methods=["GET", "POST"])
@rolle_noetig("organisator")
def neu():
    if request.method == "POST":
        a = _aus_formular(Artikel())
        if not a.name:
            flash("Name des Artikels fehlt.", "error")
        else:
            db.session.add(a)
            db.session.commit()
            flash(f"Artikel „{a.name}“ angelegt.", "ok")
            return redirect(url_for("speisekarte.liste"))
        return render_template("speisekarte/bearbeiten.html", artikel=a,
                               KATEGORIEN=KATEGORIEN)
    return render_template("speisekarte/bearbeiten.html", artikel=None,
                           KATEGORIEN=KATEGORIEN)


@bp.route("/<int:artikel_id>/bearbeiten", methods=["GET", "POST"])
@rolle_noetig("organisator")
def bearbeiten(artikel_id: int):
    a = db.get_or_404(Artikel, artikel_id)
    if request.method == "POST":
        _aus_formular(a)
        db.session.commit()
        flash("Artikel gespeichert.", "ok")
        return redirect(url_for("speisekarte.liste"))
    return render_template("speisekarte/bearbeiten.html", artikel=a,
                           KATEGORIEN=KATEGORIEN)


@bp.route("/<int:artikel_id>/loeschen", methods=["POST"])
@rolle_noetig("organisator")
def loeschen(artikel_id: int):
    a = db.get_or_404(Artikel, artikel_id)
    db.session.delete(a)
    db.session.commit()
    flash("Artikel gelöscht.", "ok")
    return redirect(url_for("speisekarte.liste"))


def _aus_formular(a: Artikel) -> Artikel:
    a.name = request.form["name"].strip()
    kategorie = request.form.get("kategorie", KATEGORIE_GETRAENK)
    a.kategorie = kategorie if kategorie in KATEGORIEN else KATEGORIE_GETRAENK
    try:
        a.preis = float(request.form.get("preis", "0").replace(",", "."))
    except ValueError:
        a.preis = 0.0
    try:
        a.punkte_pro_einheit = int(request.form.get("punkte_pro_einheit", "0") or 0)
    except ValueError:
        a.punkte_pro_einheit = 0
    try:
        a.reihenfolge = int(request.form.get("reihenfolge", "0") or 0)
    except ValueError:
        a.reihenfolge = 0
    a.aktiv = bool(request.form.get("aktiv"))
    return a


# ── Tisch-QR-Code-Aufkleber ───────────────────────────────────────────────────

AUFKLEBER_BREITE = 70 * mm
AUFKLEBER_HOEHE = 70 * mm
SPALTEN = 2
ZEILEN = 3


@bp.route("/tische")
@rolle_noetig("organisator")
def tische():
    return render_template("speisekarte/tische.html")


@bp.route("/tische/qrcodes.pdf")
@rolle_noetig("organisator")
def qrcodes_pdf():
    von = request.args.get("von", type=int)
    bis = request.args.get("bis", type=int)
    if not von:
        flash("Bitte mindestens eine Tischnummer angeben.", "error")
        return redirect(url_for("speisekarte.tische"))
    bis = bis or von
    if bis < von:
        von, bis = bis, von
    nummern = list(range(von, bis + 1))

    puffer = io.BytesIO()
    seite = canvas.Canvas(puffer, pagesize=A4)
    breite, hoehe = A4
    rand = 10 * mm

    x0, y0 = rand, hoehe - rand - AUFKLEBER_HOEHE
    spalte = zeile = 0

    for nummer in nummern:
        x = x0 + spalte * AUFKLEBER_BREITE
        y = y0 - zeile * AUFKLEBER_HOEHE

        seite.rect(x, y, AUFKLEBER_BREITE, AUFKLEBER_HOEHE)
        seite.setFont("Helvetica-Bold", 20)
        seite.drawCentredString(x + AUFKLEBER_BREITE / 2, y + AUFKLEBER_HOEHE - 14 * mm,
                                f"Tisch {nummer}")

        ziel_url = url_for("bestellung.bestellen", tisch=nummer, _external=True)
        qr_bild = qrcode.make(ziel_url)
        qr_puffer = io.BytesIO()
        qr_bild.save(qr_puffer, format="PNG")
        qr_puffer.seek(0)
        qr_groesse = 45 * mm
        seite.drawImage(ImageReader(qr_puffer),
                        x + (AUFKLEBER_BREITE - qr_groesse) / 2, y + 6 * mm,
                        width=qr_groesse, height=qr_groesse)

        seite.setFont("Helvetica", 7)
        seite.drawCentredString(x + AUFKLEBER_BREITE / 2, y + 2 * mm,
                                "Essen & Getränke bestellen")

        spalte += 1
        if spalte >= SPALTEN:
            spalte = 0
            zeile += 1
            if zeile >= ZEILEN:
                zeile = 0
                seite.showPage()

    seite.save()
    puffer.seek(0)
    return Response(
        puffer.getvalue(), mimetype="application/pdf",
        headers={"Content-Disposition":
                 f'attachment; filename="tisch_qrcodes_{von}-{bis}.pdf"'},
    )
