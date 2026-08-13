"""Gäste-Bestellsystem: Bestellseite je Tisch (öffentlich, kein Login) sowie
Bestellungen-Übersicht/Abrechnung für Kellner."""
from datetime import datetime, timezone

from flask import (Blueprint, flash, redirect, render_template, request,
                   url_for)
from flask_login import current_user

from ..models import db, Artikel, Bestellung, BestellPosition, Team, KATEGORIEN
from ..auth import darf, rolle_noetig

bp = Blueprint("bestellung", __name__)


@bp.route("/bestellen/<int:tisch>", methods=["GET", "POST"])
def bestellen(tisch: int):
    artikel = (Artikel.query.filter_by(aktiv=True)
               .order_by(Artikel.kategorie, Artikel.reihenfolge, Artikel.name)
               .all())
    teams = Team.query.order_by(Team.name).all()

    if request.method == "POST":
        if not artikel:
            flash("Es sind noch keine Artikel in der Speisekarte hinterlegt.",
                  "error")
            return redirect(url_for("bestellung.bestellen", tisch=tisch))

        bestellung = Bestellung(tisch_nummer=tisch)
        if current_user.is_authenticated and darf("kellner"):
            bestellung.erfasst_von = current_user.username

        # Ein Team gilt für die gesamte (Sammel-)Bestellung, nicht pro Artikel.
        team_id = request.form.get("team_id") or None
        team_id = int(team_id) if team_id else None

        hinzugefuegt = False
        for a in artikel:
            menge = _int_or_null(request.form.get(f"menge_{a.id}"))
            if not menge or menge <= 0:
                continue
            bestellung.positionen.append(BestellPosition(
                artikel_id=a.id, artikel_name=a.name, einzelpreis=a.preis,
                menge=menge, team_id=team_id,
                punkte_gesamt=(a.punkte_pro_einheit or 0) * menge,
                pfand_pro_einheit=a.pfand_pro_einheit or 0.0,
            ))
            hinzugefuegt = True

        if not hinzugefuegt:
            flash("Bitte mindestens einen Artikel mit Menge auswählen.", "error")
            return redirect(url_for("bestellung.bestellen", tisch=tisch))

        db.session.add(bestellung)
        db.session.commit()
        return redirect(url_for("bestellung.bestaetigung",
                                bestellung_id=bestellung.id))

    nach_kategorie = {k: [a for a in artikel if a.kategorie == k]
                      for k in KATEGORIEN}
    return render_template("bestellen.html", tisch=tisch,
                           nach_kategorie=nach_kategorie, hat_artikel=bool(artikel),
                           KATEGORIEN=KATEGORIEN, teams=teams)


@bp.route("/bestellen/bestaetigung/<int:bestellung_id>")
def bestaetigung(bestellung_id: int):
    b = db.get_or_404(Bestellung, bestellung_id)
    return render_template("bestellen_bestaetigung.html", bestellung=b)


# ── Kellner: Bestellungen-Übersicht / Abrechnung ─────────────────────────────

@bp.route("/bestellungen/")
@rolle_noetig("kellner", "organisator", "ausschank")
def uebersicht():
    filter_status = request.args.get("status", "offen")
    query = Bestellung.query.order_by(Bestellung.erstellt.desc())
    if filter_status == "offen":
        query = query.filter_by(bezahlt=False)
    elif filter_status == "bezahlt":
        query = query.filter_by(bezahlt=True)
    bestellungen = query.all()

    alle = Bestellung.query.all()
    summe_offen = sum(b.gesamtbetrag for b in alle if not b.bezahlt)
    summe_bezahlt = sum(b.gesamtbetrag for b in alle if b.bezahlt)

    punkte_je_team: dict[int, int] = {}
    for b in alle:
        for p in b.positionen:
            if p.team_id:
                punkte_je_team[p.team_id] = (punkte_je_team.get(p.team_id, 0)
                                             + (p.punkte_gesamt or 0))
    teams_nach_id = {t.id: t for t in Team.query.filter(
        Team.id.in_(punkte_je_team.keys())).all()}
    team_punkte = sorted(
        ({"team": teams_nach_id[tid], "punkte": punkte}
         for tid, punkte in punkte_je_team.items()),
        key=lambda z: z["punkte"], reverse=True)

    return render_template("bestellungen/uebersicht.html",
                           bestellungen=bestellungen, filter_status=filter_status,
                           summe_offen=summe_offen, summe_bezahlt=summe_bezahlt,
                           summe_gesamt=summe_offen + summe_bezahlt,
                           team_punkte=team_punkte)


@bp.route("/bestellungen/<int:bestellung_id>/bezahlt", methods=["POST"])
@rolle_noetig("kellner", "organisator", "ausschank")
def bezahlt_umschalten(bestellung_id: int):
    b = db.get_or_404(Bestellung, bestellung_id)
    b.bezahlt = not b.bezahlt
    b.bezahlt_am = datetime.now(timezone.utc) if b.bezahlt else None
    db.session.commit()
    return redirect(url_for("bestellung.uebersicht",
                            status=request.args.get("status", "offen")))


@bp.route("/bestellungen/tisch-suche", methods=["POST"])
@rolle_noetig("kellner", "organisator", "ausschank")
def tisch_suche():
    """Schneller Sprung zur Bestellseite eines Tisches (z.B. nach QR-Scan
    oder manueller Eingabe der Tischnummer)."""
    tisch = request.form.get("tisch", type=int)
    if not tisch:
        flash("Bitte eine Tischnummer eingeben.", "error")
        return redirect(url_for("start.index"))
    return redirect(url_for("bestellung.bestellen", tisch=tisch))


def _int_or_null(wert):
    try:
        return int(wert)
    except (TypeError, ValueError):
        return None


# ── Pfand-Rückgabe (Kellner, Organisator, Ausschank) ─────────────────────────
# Bewusst schnell/einfach gehalten: eine Ansicht pro Tisch, große Buttons,
# Teilrückgaben möglich (nicht immer kommt alles zurück).

@bp.route("/pfand/tisch-suche", methods=["POST"])
@rolle_noetig("kellner", "organisator", "ausschank")
def pfand_suche():
    """Schneller Sprung zur Pfand-Rückgabe eines Tisches."""
    tisch = request.form.get("tisch", type=int)
    if not tisch:
        flash("Bitte eine Tischnummer eingeben.", "error")
        return redirect(url_for("bestellung.uebersicht"))
    return redirect(url_for("bestellung.pfand_tisch", tisch=tisch))


@bp.route("/pfand/<int:tisch>")
@rolle_noetig("kellner", "organisator", "ausschank")
def pfand_tisch(tisch: int):
    positionen = (BestellPosition.query
                  .join(Bestellung)
                  .filter(Bestellung.tisch_nummer == tisch,
                         BestellPosition.pfand_pro_einheit > 0)
                  .order_by(Bestellung.erstellt).all())
    offene = [p for p in positionen if p.pfand_offen_anzahl > 0]
    offener_betrag = sum(p.pfand_offen_betrag for p in offene)
    return render_template("pfand_tisch.html", tisch=tisch, offene=offene,
                           offener_betrag=offener_betrag)


@bp.route("/pfand/position/<int:position_id>/rueckgabe", methods=["POST"])
@rolle_noetig("kellner", "organisator", "ausschank")
def pfand_rueckgabe(position_id: int):
    p = db.get_or_404(BestellPosition, position_id)
    if request.form.get("alle"):
        anzahl = p.pfand_offen_anzahl
    else:
        anzahl = 1
    p.pfand_zurueckgegeben = min(p.menge, (p.pfand_zurueckgegeben or 0) + anzahl)
    db.session.commit()
    return redirect(url_for("bestellung.pfand_tisch",
                            tisch=p.bestellung.tisch_nummer))
