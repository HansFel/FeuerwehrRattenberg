"""Live-Dashboard für die Moderation und Pflege durch den Organisator."""
import re

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user

from ..auth import rolle_noetig
from ..models import db, Disziplin, ModeratorStatus, Nachricht, Startplatz, Team
from ..wertung import gesamtwertung_vollstaendig, team_challenge

bp = Blueprint("moderator", __name__, url_prefix="/moderator")


def _status() -> ModeratorStatus:
    status = db.session.get(ModeratorStatus, 1)
    if status is None:
        status = ModeratorStatus(id=1)
        db.session.add(status)
        db.session.commit()
    return status


def _lauf_optionen() -> list[dict]:
    startplaetze = (Startplatz.query.join(Disziplin)
                    .order_by(Disziplin.reihenfolge, Disziplin.name,
                              Startplatz.heat, Startplatz.startnummer).all())
    optionen = []
    gesehen = set()
    for sp in startplaetze:
        heat = (sp.heat or "").strip()
        schluessel = (sp.disziplin_id, heat)
        if schluessel in gesehen:
            continue
        gesehen.add(schluessel)
        optionen.append({
            "wert": f"{sp.disziplin_id}|{heat}",
            "text": f"{sp.disziplin.name} – {heat or 'ohne Laufbezeichnung'}",
        })
    def natuerlich(option):
        return [int(teil) if teil.isdigit() else teil.casefold()
                for teil in re.split(r"(\d+)", option["text"])]
    return sorted(optionen, key=natuerlich)


def _laufende_teams(status: ModeratorStatus) -> list[Startplatz]:
    if not status.disziplin_id:
        return []
    query = Startplatz.query.filter_by(disziplin_id=status.disziplin_id)
    if status.heat:
        query = query.filter_by(heat=status.heat)
    else:
        query = query.filter((Startplatz.heat == "") | (Startplatz.heat.is_(None)))
    return query.order_by(Startplatz.startnummer, Startplatz.id).all()


def _live_daten(status: ModeratorStatus) -> dict:
    """Daten fuer die live aktualisierten Dashboard-Bereiche (aktueller Lauf,
    naechster Lauf, Siloplanen-Race- und Team-Challenge-Wertung).

    Fuer beide Wertungen wird dieselbe Berechnung wie auf der offiziellen
    Wertungsseite (/wertung/) verwendet, damit Moderator-Dashboard, Web-Ansicht
    und PDF-Export garantiert uebereinstimmen. Solange noch Teams ohne
    definitive Platzierung dabei sind, ist das die laufende Zwischenwertung;
    sobald jedes Team einen Ziellauf absolviert hat, ist es zugleich die
    (dann unveraenderliche) Gesamtwertung - keine gesonderte "Endstand"-Ansicht
    noetig.
    """
    naechster = _naechster_lauf(status)
    teams = Team.query.order_by(Team.startnummer, Team.name).all()
    disziplinen = Disziplin.query.order_by(Disziplin.reihenfolge, Disziplin.name).all()
    return dict(
        status=status,
        laufende_teams=_laufende_teams(status),
        siloplanen_tabelle=gesamtwertung_vollstaendig(teams, disziplinen),
        team_challenge_tabelle=team_challenge(teams),
        naechster=naechster,
        naechster_teams=_teams_fuer_heat(naechster) if naechster else [],
    )


@bp.route("/")
@rolle_noetig("moderator", "dj", "organisator")
def dashboard():
    status = _status()
    nachrichten = (Nachricht.query
                   .filter((Nachricht.ziel_rolle == "moderator") |
                           (Nachricht.ziel_benutzer_id == current_user.id))
                   .order_by(Nachricht.erstellt.desc()).limit(20).all())
    alle_teams = Team.query.order_by(Team.startnummer, Team.name).all()

    return render_template(
        "moderator/dashboard.html",
        lauf_optionen=_lauf_optionen(), nachrichten=nachrichten,
        alle_teams=alle_teams,
        **_live_daten(status))


@bp.route("/live-fragment")
@rolle_noetig("moderator", "dj", "organisator")
def live_fragment():
    """Liefert die live aktualisierten Dashboard-Bereiche als HTML-Fragmente
    (per JS-Polling eingebettet), damit neue Zeiten sofort erscheinen, ohne
    die Seite neu zu laden und ohne laufende Formulareingaben zu stoeren."""
    daten = _live_daten(_status())
    return jsonify(
        live_html=render_template("moderator/_live.html", **daten),
        rangliste_html=render_template("moderator/_rangliste.html", **daten),
    )


@bp.route("/status", methods=["POST"])
@rolle_noetig("organisator")
def status_speichern():
    status = _status()
    auswahl = request.form.get("lauf", "")
    if auswahl:
        try:
            disziplin_id_text, heat = auswahl.split("|", 1)
            disziplin_id = int(disziplin_id_text)
        except (ValueError, TypeError):
            flash("Ungültige Laufauswahl.", "error")
            return redirect(url_for("moderator.dashboard"))
        if not db.session.get(Disziplin, disziplin_id):
            flash("Die ausgewählte Disziplin existiert nicht.", "error")
            return redirect(url_for("moderator.dashboard"))
        status.disziplin_id = disziplin_id
        status.heat = heat
    else:
        status.disziplin_id = None
        status.heat = ""
    status.publikumsinfo = request.form.get("publikumsinfo", "").strip()
    status.sponsoren = request.form.get("sponsoren", "").strip()
    status.aktualisiert_von = current_user.username
    db.session.commit()
    flash("Moderator-Anzeige aktualisiert.", "ok")
    return redirect(url_for("moderator.dashboard"))


@bp.route("/nachricht", methods=["POST"])
@rolle_noetig("organisator")
def nachricht_senden():
    text = request.form.get("text", "").strip()
    if not text:
        flash("Bitte einen Nachrichtentext eingeben.", "error")
    else:
        db.session.add(Nachricht(text=text, absender=current_user.username,
                                 ziel_rolle="moderator"))
        db.session.commit()
        flash("Nachricht an die Moderation gesendet.", "ok")
    return redirect(url_for("moderator.dashboard"))


def _heats_numerisch(disziplin_id):
    """Heat-Namen numerisch sortiert fuer eine Disziplin."""
    import re
    seen = {}
    for sp in Startplatz.query.filter_by(disziplin_id=disziplin_id).all():
        key = sp.heat or ""
        if key not in seen:
            seen[key] = None
    heats = list(seen.keys())
    def sort_key(name):
        zahlen = re.findall(r"\d+", name)
        return tuple(int(z) for z in zahlen) if zahlen else (0,)
    heats.sort(key=sort_key)
    return heats


def _naechster_lauf(status):
    """Naechster geplanter Heat nach dem aktuellen (numerisch sortiert).
    Liefert (heat_name, startplaetze) oder None."""
    if not status.disziplin_id:
        return None
    heats = _heats_numerisch(status.disziplin_id)
    if not heats:
        return None
    if not status.heat or status.heat not in heats:
        heat = heats[0]
    else:
        idx = heats.index(status.heat)
        if idx + 1 >= len(heats):
            return None
        heat = heats[idx + 1]
    sps = Startplatz.query.filter_by(
        disziplin_id=status.disziplin_id, heat=heat
    ).order_by(Startplatz.startnummer).all()
    if not sps:
        return None
    return (heat, sps)


def _teams_fuer_heat(lauf_tupel):
    """Hilfsfunktion: gibt Startplaetze aus dem (heat, sps)-Tupel zurueck."""
    if lauf_tupel is None:
        return []
    return lauf_tupel[1]


@bp.route("/naechster-lauf", methods=["POST"])
@rolle_noetig("organisator")
def naechster_lauf_starten():
    """Setzt den naechsten geplanten Lauf als aktuellen und gibt ihn frei."""
    status = _status()
    naechster = _naechster_lauf(status)
    if naechster is None:
        flash("Kein naechster Lauf verfuegbar.", "error")
        return redirect(url_for("moderator.dashboard"))
    heat, _sps = naechster
    status.heat = heat
    status.aktualisiert_von = current_user.username
    db.session.commit()
    flash(f"Lauf „{heat}“ als aktuell gesetzt. "
          f"Jetzt „Zeitmessung freigeben“ klicken zum Starten.", "ok")
    return redirect(url_for("moderator.dashboard"))

