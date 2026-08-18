"""Strafenkatalog fuer die Punkterichter: vergibt Strafsekunden an Teams
nach dem festen Siloplanenrace-Strafenkatalog (models.py:STRAFKATALOG).
Der Punkterichter waehlt eine Regel, ein Team und ggf. eine Menge
(fuer variable Regeln wie Gramm-Reste) - die Strafsekunden werden sofort
gespeichert und koennen in der Auswertung beruecksichtigt werden."""
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


@bp.route("/vergeben", methods=["GET", "POST"])
@rolle_noetig("punkterichter")
def vergeben():
    if request.method == "GET":
        return redirect(url_for("strafen.dashboard"))
    team_id = request.form.get("team_id", type=int)
    regel_nr = request.form.get("regel_nr", "")
    eintrag = STRAFKATALOG_NACH_NR.get(regel_nr)

    aktuelle_team_ids = {t.id for t in _aktuelle_teams()}
    team = db.session.get(Team, team_id) if team_id else None
    if team is None:
        flash("Bitte ein Team auswaehlen.", "error")
        return redirect(url_for("strafen.dashboard"))
    if team.id not in aktuelle_team_ids:
        flash("Dieses Team ist nicht im aktuellen Lauf (Moderator-Dashboard "
              "pruefen). Strafe wurde nicht vergeben.", "error")
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
@rolle_noetig("punkterichter")
def loeschen(strafe_id):
    s = db.get_or_404(Strafe, strafe_id)
    db.session.delete(s)
    db.session.commit()
    flash("Strafe geloescht.", "ok")
    return redirect(url_for("strafen.dashboard"))
