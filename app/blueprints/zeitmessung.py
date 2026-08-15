"""Zeitmessung: Empfang der Start-/Ziel-Kontaktereignisse vom ESP32 sowie
eine Live-Übersicht der letzten Ereignisse (zum Testen der Hardware)."""
from flask import Blueprint, current_app, jsonify, render_template, request

from ..models import db, Zeitereignis, KONTAKT_START, KONTAKT_ZIEL, KONTAKT_KONTAKT
from ..auth import rolle_noetig

bp = Blueprint("zeitmessung", __name__)

ANZAHL_BAHNEN = 4
# KONTAKT_START/KONTAKT_ZIEL bleiben gültig für Geräte mit der alten
# 8-Kontakte-Verkabelung; KONTAKT_KONTAKT ist der aktuelle Regelfall
# (1 Kontakt pro Bahn).
GUELTIGE_KONTAKTE = {KONTAKT_START, KONTAKT_ZIEL, KONTAKT_KONTAKT}


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
        return jsonify(fehler="kontakt muss 'kontakt' (aktuelle Hardware) "
                              "oder 'start'/'ziel' (alte Hardware) sein."), 400

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

    # Laufende Nummer je Bahn (1.-4. Auslösung = Läufer 1-4 Start, 5. =
    # Ziel, danach wieder von vorn) - rein heuristisch, solange es noch
    # kein Lauf/Runden-Datenmodell gibt: zählt fortlaufend ab der ältesten
    # bekannten Auslösung dieser Bahn, unabhängig vom Gerät.
    bahn_zaehler = {}
    zaehlerstand = {}
    alle_chronologisch = (Zeitereignis.query
                          .order_by(Zeitereignis.server_empfangen.asc()).all())
    for e in alle_chronologisch:
        zaehlerstand[e.bahn] = zaehlerstand.get(e.bahn, 0) + 1
        position = ((zaehlerstand[e.bahn] - 1) % 5) + 1
        bahn_zaehler[e.id] = position

    return render_template("zeitmessung/liste.html", ereignisse=ereignisse,
                           bahn_zaehler=bahn_zaehler)
