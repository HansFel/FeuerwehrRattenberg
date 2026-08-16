"""Zeitmessung: Empfang der Start-/Ziel-Kontaktereignisse vom ESP32 sowie
eine Live-Übersicht der letzten Ereignisse (zum Testen der Hardware)."""
import json
import logging
import threading
import time
import urllib.request
from urllib.error import URLError

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, url_for

from ..models import db, Zeitereignis, KONTAKT_START, KONTAKT_ZIEL, KONTAKT_KONTAKT
from ..auth import rolle_noetig

bp = Blueprint("zeitmessung", __name__)
_log = logging.getLogger(__name__)

ANZAHL_BAHNEN = 4
# KONTAKT_START/KONTAKT_ZIEL bleiben gültig für Geräte mit der alten
# 8-Kontakte-Verkabelung; KONTAKT_KONTAKT ist der aktuelle Regelfall
# (1 Kontakt pro Bahn).
GUELTIGE_KONTAKTE = {KONTAKT_START, KONTAKT_ZIEL, KONTAKT_KONTAKT}

# Abonnenten für die Weiterleitung von ESP32-Ereignissen an andere Instanzen
# auf demselben Server (z.B. test1/test2/generalprobe wollen dieselben
# Ereignisse wie die Produktion sehen, ohne dass der ESP32 selbst mehrere
# Ziele kennen muss). Bewusst nur im Prozessspeicher, kein DB-Modell: jeder
# Abonnent meldet sich selbst regelmäßig neu an (siehe
# app/__init__.py:_bei_quelle_anmelden) - ein Neustart dieser Instanz ODER
# des Abonnenten heilt sich dadurch von selbst innerhalb der Ablaufzeit,
# ohne dass irgendwo Zustand persistiert/aufgeräumt werden muss.
ABONNEMENT_GUELTIGKEIT_S = 180
_abonnenten: dict[str, dict] = {}
_abonnenten_lock = threading.Lock()


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
    _an_abonnenten_weiterleiten({
        "geraet_id": ereignis.geraet_id,
        "bahn": ereignis.bahn,
        "kontakt": ereignis.kontakt,
        "geraet_millis": ereignis.geraet_millis,
        "geraet_zeit_iso": ereignis.geraet_zeit_iso,
    })
    return jsonify(status="ok", id=ereignis.id), 201


@bp.route("/api/zeitmessung/abonnieren", methods=["POST"])
def abonnieren():
    """Meldet eine andere Instanz als Weiterleitungs-Ziel für ESP32-Ereignisse an.

    Für test1/test2/generalprobe gedacht, die sich selbst bei der
    Produktions-Instanz anmelden (siehe app/__init__.py), damit sie
    dieselben Live-Ereignisse sehen, ohne dass der ESP32 mehrere Ziele
    kennen muss. Authentifizierung über den eigenen API-Key DIESER
    (empfangenden) Instanz - wie beim ESP32-Endpunkt oben.
    """
    erwarteter_key = current_app.config["ZEITMESSUNG_API_KEY"]
    if request.headers.get("X-API-Key") != erwarteter_key:
        return jsonify(fehler="Ungültiger oder fehlender API-Key."), 401

    daten = request.get_json(silent=True) or {}
    ziel_url = str(daten.get("ziel_url", "")).strip()
    ziel_api_key = str(daten.get("api_key", "")).strip()
    if not (ziel_url.startswith("http://") or ziel_url.startswith("https://")):
        return jsonify(fehler="ziel_url fehlt oder ungültig."), 400
    if not ziel_api_key:
        return jsonify(fehler="api_key fehlt."), 400

    with _abonnenten_lock:
        _abonnenten[ziel_url] = {
            "api_key": ziel_api_key,
            "ablauf": time.monotonic() + ABONNEMENT_GUELTIGKEIT_S,
        }
    return jsonify(status="ok", gueltig_s=ABONNEMENT_GUELTIGKEIT_S)


def _aktive_abonnenten() -> list[tuple[str, str]]:
    jetzt = time.monotonic()
    with _abonnenten_lock:
        return [(url, info["api_key"]) for url, info in _abonnenten.items()
                if info["ablauf"] > jetzt]


def _an_abonnenten_weiterleiten(nutzlast: dict) -> None:
    """Reicht ein Ereignis an alle aktiven Abonnenten weiter (fire-and-forget,
    je Abonnent in einem eigenen Thread, damit ein nicht erreichbarer
    Abonnent nicht die Antwort an den ESP32 verzögert)."""
    abonnenten = _aktive_abonnenten()
    if not abonnenten:
        return
    rohdaten = json.dumps(nutzlast).encode("utf-8")

    def senden(ziel_url: str, api_key: str) -> None:
        try:
            anfrage = urllib.request.Request(
                ziel_url, data=rohdaten, method="POST",
                headers={"Content-Type": "application/json", "X-API-Key": api_key})
            urllib.request.urlopen(anfrage, timeout=3)
        except (URLError, OSError, ValueError) as exc:
            _log.warning("Weiterleitung an Abonnent %s fehlgeschlagen: %s", ziel_url, exc)

    for ziel_url, api_key in abonnenten:
        threading.Thread(target=senden, args=(ziel_url, api_key), daemon=True).start()


@bp.route("/zeitmessung/")
@rolle_noetig("organisator", "startrichter")
def liste():
    ereignisse = (Zeitereignis.query
                  .order_by(Zeitereignis.server_empfangen.desc())
                  .limit(200).all())

    # Laufende Nummer je Bahn (1.-4. Auslösung = Läufer 1-4 Start, 5. =
    # Ziel, danach wieder von vorn) sowie Abstand zur vorherigen Auslösung
    # derselben Bahn (= grobe Zwischen-/Beinzeit) - rein heuristisch,
    # solange es noch kein Lauf/Runden-Datenmodell gibt: zählt/misst
    # fortlaufend ab der ältesten bekannten Auslösung dieser Bahn,
    # unabhängig vom Gerät. Basiert auf server_empfangen (nicht
    # geraet_millis/geraet_zeit_iso), da das über einen Geräte-Neustart
    # hinweg konsistent bleibt.
    bahn_zaehler = {}
    bahn_abstand = {}
    zaehlerstand = {}
    letzte_zeit = {}
    alle_chronologisch = (Zeitereignis.query
                          .order_by(Zeitereignis.server_empfangen.asc()).all())
    for e in alle_chronologisch:
        zaehlerstand[e.bahn] = zaehlerstand.get(e.bahn, 0) + 1
        position = ((zaehlerstand[e.bahn] - 1) % 5) + 1
        bahn_zaehler[e.id] = position
        if position == 1:
            bahn_abstand[e.id] = None   # erste Auslösung eines neuen Laufs
        elif e.bahn in letzte_zeit:
            bahn_abstand[e.id] = (e.server_empfangen - letzte_zeit[e.bahn]).total_seconds()
        letzte_zeit[e.bahn] = e.server_empfangen

    return render_template("zeitmessung/liste.html", ereignisse=ereignisse,
                           bahn_zaehler=bahn_zaehler, bahn_abstand=bahn_abstand)


@bp.route("/zeitmessung/loeschen", methods=["POST"])
@rolle_noetig("organisator")
def loeschen():
    """Löscht ALLE rohen Zeitmessung-Ereignisse (z.B. nach einem Testlauf,
    bevor der echte Wettkampf beginnt)."""
    anzahl = Zeitereignis.query.delete()
    db.session.commit()
    flash(f"{anzahl} Zeitmessung-Ereignis(se) gelöscht.", "ok")
    return redirect(url_for("zeitmessung.liste"))
