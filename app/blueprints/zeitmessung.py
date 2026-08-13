"""Zeitmessung: Empfang der Start-/Ziel-Kontaktereignisse vom ESP32 sowie
eine Live-Übersicht der letzten Ereignisse (zum Testen der Hardware)."""
from flask import Blueprint, current_app, jsonify, render_template, request

from ..models import db, Zeitereignis, KONTAKT_START, KONTAKT_ZIEL
from ..auth import rolle_noetig

bp = Blueprint("zeitmessung", __name__)

ANZAHL_BAHNEN = 4
GUELTIGE_KONTAKTE = {KONTAKT_START, KONTAKT_ZIEL}


@bp.route("/api/zeitmessung/event", methods=["POST"])
def event_empfangen():
    """Nimmt ein Kontaktereignis eines ESP32-Zeitmessgeräts entgegen.

    Authentifizierung über einen gemeinsamen API-Key im Header
    'X-API-Key' (kein Benutzerlogin, da das Gerät keinen Nutzer hat).
    """
    erwarteter_key = current_app.config["ZEITMESSUNG_API_KEY"]
    if request.headers.get("X-API-Key") != erwarteter_key:
        return jsonify(fehler="Ungültiger oder fehlender API-Key."), 401

    daten = request.get_json(silent=True) or {}
    geraet_id = str(daten.get("geraet_id", "")).strip()[:80]
    kontakt = str(daten.get("kontakt", "")).strip().lower()
    try:
        bahn = int(daten.get("bahn"))
    except (TypeError, ValueError):
        bahn = None

    if not geraet_id:
        return jsonify(fehler="geraet_id fehlt."), 400
    if bahn is None or not (1 <= bahn <= ANZAHL_BAHNEN):
        return jsonify(fehler=f"bahn muss 1-{ANZAHL_BAHNEN} sein."), 400
    if kontakt not in GUELTIGE_KONTAKTE:
        return jsonify(fehler="kontakt muss 'start' oder 'ziel' sein."), 400

    ereignis = Zeitereignis(
        geraet_id=geraet_id,
        bahn=bahn,
        kontakt=kontakt,
        geraet_millis=daten.get("geraet_millis"),
        geraet_zeit_iso=str(daten.get("geraet_zeit_iso", ""))[:40],
    )
    db.session.add(ereignis)
    db.session.commit()
    return jsonify(status="ok", id=ereignis.id), 201


@bp.route("/zeitmessung/")
@rolle_noetig("organisator", "startrichter")
def liste():
    ereignisse = (Zeitereignis.query
                  .order_by(Zeitereignis.server_empfangen.desc())
                  .limit(200).all())
    return render_template("zeitmessung/liste.html", ereignisse=ereignisse)
