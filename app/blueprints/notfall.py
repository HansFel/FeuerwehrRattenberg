"""Notfall-Zeiterfassung: der Startrichter/Organisator trägt vorab die
Team-Besetzung je Bahn ein. Wird ein Lauf zusätzlich AKTIVIERT, ordnet
app/blueprints/zeitmessung.py eingehende Kontaktereignisse (ESP32 oder
Desktop-App/Arduino-Mega) automatisch zu und füllt die Läuferzeiten selbst
aus. Ohne Aktivierung (oder falls die Automatik ausfällt) bleibt die
Handeingabe hier der Fallback."""
from datetime import datetime

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user

from ..models import db, NotfallLauf, NotfallBahn, Team
from ..auth import rolle_noetig
from .moderator import _status as _moderator_status, _laufende_teams

bp = Blueprint("notfall", __name__, url_prefix="/notfall")

ANZAHL_BAHNEN = 4


@bp.route("/")
@rolle_noetig("startrichter", "organisator")
def liste():
    laeufe = NotfallLauf.query.order_by(NotfallLauf.erstellt.desc()).all()
    return render_template("notfall/liste.html", laeufe=laeufe)


@bp.route("/neu", methods=["GET", "POST"])
@rolle_noetig("startrichter", "organisator")
def neu():
    teams = Team.query.order_by(Team.startnummer, Team.name).all()
    if request.method == "POST":
        lauf = NotfallLauf(
            bezeichnung=request.form.get("bezeichnung", "").strip(),
            erstellt_von=current_user.username,
        )
        belegt = False
        for bahn_nr in range(1, ANZAHL_BAHNEN + 1):
            team_id = _int_or_none(request.form.get(f"team_{bahn_nr}"))
            if team_id:
                belegt = True
            lauf.bahnen.append(NotfallBahn(bahn_nr=bahn_nr, team_id=team_id))
        if not belegt:
            flash("Bitte mindestens eine Bahn mit einem Team belegen.", "error")
            return render_template("notfall/neu.html", teams=teams)
        db.session.add(lauf)
        db.session.commit()
        flash("Notfall-Lauf angelegt.", "ok")
        return redirect(url_for("notfall.lauf", lauf_id=lauf.id))
    return render_template("notfall/neu.html", teams=teams)


@bp.route("/<int:lauf_id>", methods=["GET", "POST"])
@rolle_noetig("startrichter", "organisator")
def lauf(lauf_id: int):
    l = db.get_or_404(NotfallLauf, lauf_id)
    if request.method == "POST":
        for bahn in l.bahnen:
            for i in range(1, 5):
                wert = request.form.get(f"zeit_{bahn.id}_{i}", "").strip()
                setattr(bahn, f"zeit_laeufer{i}", _float_or_none(wert))
        db.session.commit()
        flash("Zeiten gespeichert.", "ok")
        return redirect(url_for("notfall.lauf", lauf_id=lauf_id))
    return render_template("notfall/lauf.html", lauf=l)


@bp.route("/<int:lauf_id>/aktivieren", methods=["POST"])
@rolle_noetig("startrichter", "organisator")
def aktivieren(lauf_id: int):
    """Markiert diesen Lauf als aktiv für die automatische Zuordnung.

    Es kann immer nur EIN Lauf gleichzeitig aktiv sein - ein vorher aktiver
    Lauf wird automatisch deaktiviert (seine bereits zugeordneten Zeiten
    bleiben erhalten, nur neue Ereignisse werden ihm nicht mehr zugeordnet).
    """
    l = db.get_or_404(NotfallLauf, lauf_id)
    NotfallLauf.query.filter(NotfallLauf.id != lauf_id).update({"aktiv": False})
    l.aktiv = True
    l.aktiviert_um = datetime.utcnow()
    db.session.commit()
    flash(f"Lauf „{l.bezeichnung or l.id}“ ist jetzt aktiv - neue Kontaktereignisse "
          f"werden automatisch zugeordnet.", "ok")
    return redirect(url_for("notfall.lauf", lauf_id=lauf_id))


@bp.route("/<int:lauf_id>/deaktivieren", methods=["POST"])
@rolle_noetig("startrichter", "organisator")
def deaktivieren(lauf_id: int):
    l = db.get_or_404(NotfallLauf, lauf_id)
    l.aktiv = False
    db.session.commit()
    flash("Automatische Zuordnung für diesen Lauf deaktiviert.", "ok")
    return redirect(url_for("notfall.lauf", lauf_id=lauf_id))


@bp.route("/<int:lauf_id>/loeschen", methods=["POST"])
@rolle_noetig("organisator")
def loeschen(lauf_id: int):
    l = db.get_or_404(NotfallLauf, lauf_id)
    db.session.delete(l)
    db.session.commit()
    flash("Notfall-Lauf gelöscht.", "ok")
    return redirect(url_for("notfall.liste"))


@bp.route("/aus-startliste-freigeben", methods=["POST"])
@rolle_noetig("startrichter", "organisator")
def aus_startliste_freigeben():
    """Erzeugt und aktiviert einen NotfallLauf aus dem aktuell im
    Moderator-Dashboard eingestellten Heat (siehe moderator.py) - vermeidet
    die doppelte Eingabe der Team-Besetzung, die dort schon aus der
    Startliste (Startplatz) bekannt ist. Jede erzeugte NotfallBahn wird per
    startplatz_id mit dem Ursprungs-Startplatz verknüpft, damit das Ergebnis
    nach Abschluss automatisch dorthin zurückgeschrieben wird (siehe
    app/blueprints/zeitmessung.py:_automatische_zuordnung_pruefen)."""
    status = _moderator_status()
    startplaetze = _laufende_teams(status)
    if not startplaetze:
        flash("Kein aktueller Lauf im Moderator-Dashboard eingestellt - dort "
              "zuerst Disziplin/Heat auswählen.", "error")
        return redirect(url_for("moderator.dashboard"))

    bezeichnung = f"{status.disziplin.name} – {status.heat or 'ohne Laufbezeichnung'}"
    lauf = NotfallLauf(bezeichnung=bezeichnung, erstellt_von=current_user.username)
    for sp in startplaetze:
        if sp.startnummer is None or not (1 <= sp.startnummer <= ANZAHL_BAHNEN):
            continue
        lauf.bahnen.append(NotfallBahn(bahn_nr=sp.startnummer, team_id=sp.team_id,
                                       startplatz_id=sp.id))
    if not lauf.bahnen:
        flash("Keine gültigen Bahn-Nummern (1-4) in der Startliste für diesen "
              "Lauf gefunden.", "error")
        return redirect(url_for("moderator.dashboard"))

    NotfallLauf.query.filter(NotfallLauf.aktiv.is_(True)).update({"aktiv": False})
    lauf.aktiv = True
    lauf.aktiviert_um = datetime.utcnow()
    db.session.add(lauf)
    db.session.commit()
    flash(f"Zeitmessung für „{bezeichnung}“ freigegeben.", "ok")
    return redirect(url_for("notfall.lauf", lauf_id=lauf.id))


@bp.route("/api/aktiv")
def api_aktiver_lauf():
    """Liefert den aktuell aktiven Lauf (Bahn/Team/Läuferzeiten) als JSON -
    für die Desktop-App (Live-Anzeige), kein Benutzer-Login vorhanden, daher
    Authentifizierung über denselben API-Key wie die Zeitmessung-Ereignisse
    ('X-API-Key'-Header, siehe app/blueprints/zeitmessung.py)."""
    erwarteter_key = current_app.config["ZEITMESSUNG_API_KEY"]
    if request.headers.get("X-API-Key") != erwarteter_key:
        return jsonify(fehler="Ungültiger oder fehlender API-Key."), 401

    lauf = NotfallLauf.query.filter_by(aktiv=True).first()
    if not lauf:
        return jsonify(aktiv=False)

    bahnen = []
    for bahn in lauf.bahnen:
        laeufer = []
        if bahn.team:
            for i, zeit in enumerate(bahn.zeiten, start=1):
                mitglied = (bahn.team.mitglieder[i - 1]
                           if len(bahn.team.mitglieder) >= i else None)
                laeufer.append({
                    "nummer": i,
                    "name": mitglied.anzeige() if mitglied else None,
                    "zeit": zeit,
                })
        bahnen.append({
            "bahn_nr": bahn.bahn_nr,
            "team_name": bahn.team.name if bahn.team else None,
            "laeufer": laeufer,
            "gesamtzeit": bahn.gesamtzeit,
        })
    return jsonify(aktiv=True, lauf_id=lauf.id, bezeichnung=lauf.bezeichnung, bahnen=bahnen)


@bp.route("/api/importieren", methods=["POST"])
def api_importieren():
    """Nimmt einen OFFLINE (ohne Netzverbindung zur Webapp) gemessenen Lauf
    von der Desktop-App entgegen - für den Fall, dass die LAN-Verbindung
    während des Wettkampfs ausfällt: die Desktop-App ordnet Teams dann lokal
    per eingetippter Startnummer den Bahnen zu und berechnet die Läuferzeiten
    selbst (identische 5-Auslösungen-Logik wie serverseitig), synct das
    Ergebnis aber erst nach, sobald die Webapp wieder erreichbar ist.

    Idempotent per 'server_lauf_id' (aus einer früheren Antwort dieses
    Endpunkts) - wiederholtes Senden (z.B. weil weitere Bahnen inzwischen
    fertig sind) aktualisiert denselben NotfallLauf statt einen neuen
    anzulegen. Authentifizierung wie bei den anderen Zeitmessung-Endpunkten
    über 'X-API-Key' (kein Benutzerlogin, die Desktop-App hat keinen)."""
    erwarteter_key = current_app.config["ZEITMESSUNG_API_KEY"]
    if request.headers.get("X-API-Key") != erwarteter_key:
        return jsonify(fehler="Ungültiger oder fehlender API-Key."), 401

    daten = request.get_json(silent=True) or {}
    server_lauf_id = _int_or_none(daten.get("server_lauf_id"))
    bezeichnung = str(daten.get("bezeichnung", "")).strip()[:120]
    bahnen_daten = daten.get("bahnen")
    if not isinstance(bahnen_daten, list) or not bahnen_daten:
        return jsonify(fehler="bahnen fehlt oder ist leer."), 400

    lauf = db.session.get(NotfallLauf, server_lauf_id) if server_lauf_id else None
    if lauf is None:
        lauf = NotfallLauf(bezeichnung=bezeichnung or "Offline-Import",
                           erstellt_von="desktop-app-import")
        db.session.add(lauf)
        db.session.flush()   # vergibt lauf.id für die Antwort/künftige Updates

    for eintrag in bahnen_daten:
        bahn_nr = _int_or_none(eintrag.get("bahn_nr"))
        if bahn_nr is None or not (1 <= bahn_nr <= ANZAHL_BAHNEN):
            continue
        bahn = next((b for b in lauf.bahnen if b.bahn_nr == bahn_nr), None)
        if bahn is None:
            bahn = NotfallBahn(bahn_nr=bahn_nr)
            lauf.bahnen.append(bahn)

        team_nummer = _int_or_none(eintrag.get("team_nummer"))
        if team_nummer is not None:
            team = Team.query.filter_by(startnummer=team_nummer).first()
            if team:
                bahn.team_id = team.id

        for i in range(1, 5):
            wert = eintrag.get(f"zeit_laeufer{i}")
            if wert is not None:
                setattr(bahn, f"zeit_laeufer{i}", float(wert))

    db.session.commit()
    return jsonify(server_lauf_id=lauf.id), 200


def _int_or_none(wert):
    try:
        return int(wert) if wert else None
    except (TypeError, ValueError):
        return None


def _float_or_none(wert: str):
    try:
        return float(wert.replace(",", ".")) if wert else None
    except (TypeError, ValueError):
        return None
