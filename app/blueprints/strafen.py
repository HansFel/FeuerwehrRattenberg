"""Strafenkatalog fuer die Punkterichter: vergibt Strafsekunden an Teams
nach dem festen Siloplanenrace-Strafenkatalog (models.py:STRAFKATALOG).
Der Punkterichter waehlt ein Team und EINE ODER MEHRERE Regeln (fuer
variable Regeln wie Gramm-Reste je eine Menge) - pro ausgewaehlter Regel
wird eine eigene Strafe gespeichert, damit die Auswertung/Loeschung je
Regel granular bleibt."""
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user

from ..models import db, Team, Strafe, ModeratorStatus, Startplatz, STRAFKATALOG, STRAFKATALOG_NACH_NR
from ..auth import rolle_noetig

bp = Blueprint("strafen", __name__, url_prefix="/strafen")


def _aktuelle_teams() -> list[Team]:
    """Teams des aktuell im Moderator-Dashboard eingestellten Laufs
    (Disziplin + Heat) - nur diese duerfen eine Strafe bekommen, damit
    der Punkterichter nicht versehentlich ein Team eines anderen Laufs
    trifft."""
    status = db.session.get(ModeratorStatus, 1)
    if status is None or not status.disziplin_id:
        return []
    query = Startplatz.query.filter_by(disziplin_id=status.disziplin_id)
    if status.heat:
        query = query.filter_by(heat=status.heat)
    else:
        query = query.filter((Startplatz.heat == "") | (Startplatz.heat.is_(None)))
    startplaetze = query.order_by(Startplatz.startnummer, Startplatz.id).all()
    return [sp.team for sp in startplaetze if sp.team is not None]


@bp.route("/")
@rolle_noetig("punkterichter")
def dashboard():
    teams = _aktuelle_teams()
    strafen = Strafe.query.order_by(Strafe.erstellt.desc()).all()
    summen = {}
    for s in strafen:
        summen[s.team_id] = summen.get(s.team_id, 0.0) + s.sekunden
    teams_nach_id = {t.id: t for t in Team.query.all()}
    return render_template("strafen_dashboard.html", katalog=STRAFKATALOG,
                           teams=teams, strafen=strafen, summen=summen,
                           teams_nach_id=teams_nach_id)


def _menge_or_none(wert):
    if wert is None or str(wert).strip() == "":
        return None
    try:
        menge = float(str(wert).replace(",", "."))
    except ValueError:
        return None
    return menge if menge > 0 else None


@bp.route("/vergeben", methods=["GET", "POST"])
@rolle_noetig("punkterichter")
def vergeben():
    if request.method == "GET":
        return redirect(url_for("strafen.dashboard"))
    team_id = request.form.get("team_id", type=int)
    regel_nrn = request.form.getlist("regel_nr")

    aktuelle_team_ids = {t.id for t in _aktuelle_teams()}
    team = db.session.get(Team, team_id) if team_id else None
    if team is None:
        flash("Bitte ein Team auswaehlen.", "error")
        return redirect(url_for("strafen.dashboard"))
    if team.id not in aktuelle_team_ids:
        flash("Dieses Team ist nicht im aktuellen Lauf (Moderator-Dashboard "
              "pruefen). Strafe wurde nicht vergeben.", "error")
        return redirect(url_for("strafen.dashboard"))
    if not regel_nrn:
        flash("Bitte mindestens eine Regel aus dem Strafenkatalog auswaehlen.",
              "error")
        return redirect(url_for("strafen.dashboard"))

    notiz = request.form.get('notiz', '').strip()
    neue_strafen = []
    for regel_nr in regel_nrn:
        eintrag = STRAFKATALOG_NACH_NR.get(regel_nr)
        if eintrag is None:
            continue
        if "sekunden_pro_einheit" in eintrag:
            menge = _menge_or_none(request.form.get(f"menge_{regel_nr}"))
            if menge is None:
                flash('Bitte eine Menge fuer Regel ' + regel_nr + ' eingeben (in '
                      + eintrag['einheit'] + ').', 'error')
                return redirect(url_for("strafen.dashboard"))
            sekunden = menge * eintrag['sekunden_pro_einheit']
        else:
            sekunden = float(eintrag.get('sekunden', 0))
        neue_strafen.append(Strafe(
            team_id=team.id,
            regel_nr=regel_nr,
            regel_text=eintrag['regel'],
            sekunden=sekunden,
            notiz=notiz,
            erfasst_von=current_user.username,
        ))

    if not neue_strafen:
        flash("Bitte mindestens eine gueltige Regel aus dem Strafenkatalog "
              "auswaehlen.", "error")
        return redirect(url_for("strafen.dashboard"))

    db.session.add_all(neue_strafen)
    db.session.commit()
    gesamt_sekunden = sum(s.sekunden for s in neue_strafen)
    regeln_text = ", ".join(s.regel_nr for s in neue_strafen)
    flash(f"{len(neue_strafen)} Strafe(n) vergeben: {team.name} "
          f"+{int(gesamt_sekunden)} s gesamt (Regel {regeln_text}).", "ok")
    return redirect(url_for("strafen.dashboard"))


@bp.route("/<int:strafe_id>/loeschen", methods=["POST"])
@rolle_noetig("punkterichter")
def loeschen(strafe_id):
    s = db.get_or_404(Strafe, strafe_id)
    db.session.delete(s)
    db.session.commit()
    flash("Strafe geloescht.", "ok")
    return redirect(url_for("strafen.dashboard"))
