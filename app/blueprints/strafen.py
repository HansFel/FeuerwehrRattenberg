"""Strafenkatalog fuer die Startrichter: vergibt Strafsekunden an Teams
nach dem festen Siloplanenrace-Strafenkatalog (models.py:STRAFKATALOG).
Der Startrichter waehlt eine Regel, ein Team und ggf. eine Menge
(fuer variable Regeln wie Gramm-Reste) - die Strafsekunden werden sofort
gespeichert und koennen in der Auswertung beruecksichtigt werden."""
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user

from ..models import db, Team, Strafe, STRAFKATALOG, STRAFKATALOG_NACH_NR
from ..auth import rolle_noetig

bp = Blueprint("strafen", __name__, url_prefix="/strafen")


@bp.route("/")
@rolle_noetig("startrichter", "organisator")
def dashboard():
    teams = Team.query.order_by(Team.startnummer, Team.name).all()
    strafen = Strafe.query.order_by(Strafe.erstellt.desc()).all()
    summen = {}
    for s in strafen:
        summen[s.team_id] = summen.get(s.team_id, 0.0) + s.sekunden
    teams_nach_id = {t.id: t for t in teams}
    return render_template("strafen_dashboard.html", katalog=STRAFKATALOG,
                           teams=teams, strafen=strafen, summen=summen,
                           teams_nach_id=teams_nach_id)


@bp.route("/vergeben", methods=["GET", "POST"])
@rolle_noetig("startrichter", "organisator")
def vergeben():
    if request.method == "GET":
        return redirect(url_for("strafen.dashboard"))
    team_id = request.form.get("team_id", type=int)
    regel_nr = request.form.get("regel_nr", "")
    eintrag = STRAFKATALOG_NACH_NR.get(regel_nr)

    team = db.session.get(Team, team_id) if team_id else None
    if team is None:
        flash("Bitte ein Team auswaehlen.", "error")
        return redirect(url_for("strafen.dashboard"))
    if eintrag is None:
        flash("Bitte eine Regel aus dem Strafenkatalog auswaehlen.", "error")
        return redirect(url_for("strafen.dashboard"))

    if "sekunden_pro_einheit" in eintrag:
        menge = request.form.get("menge", type=float)
        if not menge or menge <= 0:
            flash('Bitte eine Menge eingeben (in ' + eintrag['einheit'] + ').', 'error')
            return redirect(url_for("strafen.dashboard"))
        sekunden = menge * eintrag['sekunden_pro_einheit']
    else:
        sekunden = float(eintrag.get('sekunden', 0))

    notiz = request.form.get('notiz', '').strip()
    strafe = Strafe(
        team_id=team.id,
        regel_nr=regel_nr,
        regel_text=eintrag['regel'],
        sekunden=sekunden,
        notiz=notiz,
        erfasst_von=current_user.username,
    )
    db.session.add(strafe)
    db.session.commit()
    flash('Strafe vergeben: ' + team.name + ' +' + str(int(sekunden)) + ' s (Regel ' + regel_nr + ').', 'ok')
    return redirect(url_for("strafen.dashboard"))


@bp.route("/<int:strafe_id>/loeschen", methods=["POST"])
@rolle_noetig("startrichter", "organisator")
def loeschen(strafe_id):
    s = db.get_or_404(Strafe, strafe_id)
    db.session.delete(s)
    db.session.commit()
    flash("Strafe geloescht.", "ok")
    return redirect(url_for("strafen.dashboard"))
