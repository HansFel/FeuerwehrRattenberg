"""Zeiten/Punkte erfassen und Ranglisten anzeigen."""
from flask import (Blueprint, flash, redirect, render_template, request,
                   url_for)

from ..models import (db, Team, Disziplin, Ergebnis, WERTUNG_ZEIT,
                      BestellPosition, Strafe, Startplatz)
from ..wertung import rangliste_disziplin, gesamtwertung
from ..auth import darf

bp = Blueprint("wertung", __name__, url_prefix="/wertung")


@bp.route("/")
def uebersicht():
    disziplinen = Disziplin.query.order_by(Disziplin.reihenfolge,
                                            Disziplin.name).all()
    teams = Team.query.all()
    tabelle = gesamtwertung(teams, disziplinen)

    # Getraenkepunkte je Team (aus dem Bestellsystem/Ausschank)
    getraenkepunkte: dict[int, int] = {}
    for pos in BestellPosition.query.all():
        if pos.team_id and pos.punkte_gesamt:
            getraenkepunkte[pos.team_id] = (
                getraenkepunkte.get(pos.team_id, 0) + pos.punkte_gesamt)

    # Strafsekunden je Team (aus dem Strafenkatalog der Punkterichter)
    strafsekunden: dict[int, float] = {}
    for s in Strafe.query.all():
        strafsekunden[s.team_id] = (
            strafsekunden.get(s.team_id, 0.0) + s.sekunden)

    # Summe der gemessenen Zeiten je Team (aus der Zeitmessung, ueber
    # Startplatz.ergebnis_sekunden - z.B. beide Vorrunden-Laeufe addiert).
    # None nur, wenn noch KEINE gemessene Zeit vorliegt (nicht 0).
    gemessene_zeit: dict[int, float] = {}
    for sp in Startplatz.query.filter(Startplatz.ergebnis_sekunden.isnot(None)).all():
        gemessene_zeit[sp.team_id] = (
            gemessene_zeit.get(sp.team_id, 0.0) + sp.ergebnis_sekunden)

    for zeile in tabelle:
        tid = zeile["team"].id
        zeile["getraenkepunkte"] = getraenkepunkte.get(tid, 0)
        zeile["strafsekunden"] = strafsekunden.get(tid, 0.0)
        zeile["gemessene_zeit"] = gemessene_zeit.get(tid)
        if zeile["gemessene_zeit"] is None:
            zeile["gesamtzeit"] = None
        else:
            zeile["gesamtzeit"] = zeile["gemessene_zeit"] + zeile["strafsekunden"]

    return render_template("wertung/uebersicht.html",
                           disziplinen=disziplinen, tabelle=tabelle)


@bp.route("/disziplin/<int:disziplin_id>", methods=["GET", "POST"])
def erfassen(disziplin_id: int):
    disziplin = db.get_or_404(Disziplin, disziplin_id)

    if request.method == "POST":
        if not darf("punkterichter"):
            flash("Zum Erfassen von Ergebnissen brauchst du die Rolle "
                  "Punkterichter (oder Administrator).", "error")
            return redirect(url_for("auth.login",
                                    next=url_for("wertung.erfassen",
                                                 disziplin_id=disziplin.id)))
        team_id = int(request.form["team_id"])
        erg = Ergebnis.query.filter_by(team_id=team_id,
                                       disziplin_id=disziplin.id).first()
        if erg is None:
            erg = Ergebnis(team_id=team_id, disziplin_id=disziplin.id)
            db.session.add(erg)

        erg.zeit_sekunden = _float_or_none(request.form.get("zeit_sekunden"))
        erg.punkte = _float_or_none(request.form.get("punkte"))
        erg.fehlerpunkte = _int_or_zero(request.form.get("fehlerpunkte"))
        erg.disqualifiziert = bool(request.form.get("disqualifiziert"))
        erg.notiz = request.form.get("notiz", "").strip()
        db.session.commit()
        flash("Ergebnis gespeichert.", "ok")
        return redirect(url_for("wertung.erfassen", disziplin_id=disziplin.id))

    platzierungen = rangliste_disziplin(disziplin)
    erfasste = {p.team.id: p.ergebnis for p in platzierungen}
    teams = Team.query.order_by(Team.name).all()
    return render_template("wertung/erfassen.html", disziplin=disziplin,
                           platzierungen=platzierungen, teams=teams,
                           erfasste=erfasste, ist_zeit=disziplin.wertungsart
                           == WERTUNG_ZEIT)


def _float_or_none(wert):
    if wert is None or str(wert).strip() == "":
        return None
    try:
        return float(str(wert).replace(",", "."))
    except ValueError:
        return None


def _int_or_zero(wert):
    try:
        return int(wert)
    except (TypeError, ValueError):
        return 0
