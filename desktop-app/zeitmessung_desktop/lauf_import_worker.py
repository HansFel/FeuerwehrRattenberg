"""Hintergrund-Thread: meldet lokal (offline, ohne Webapp-Verbindung)
gemessene Läufe nach, sobald die Webapp wieder erreichbar ist - siehe
lokale_zuordnung.py für die lokale Zuordnungslogik und
app/blueprints/notfall.py:api_importieren für den Server-Endpunkt.

Sendet den aktuellen Stand bei jedem Zyklus erneut (idempotent per
server_lauf_id), bis alle Bahnen vollständig zugeordnet sind - so kommen
auch Bahnen an, die erst nach dem ersten Sync-Versuch fertig werden."""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Callable

import requests

from . import datenbank
from .webapp_urls import importieren_url

HTTP_TIMEOUT_S = 5


def lauf_zu_nutzlast(lauf, bahnen) -> dict:
    return {
        "server_lauf_id": lauf["server_lauf_id"],
        "bezeichnung": lauf["bezeichnung"],
        "bahnen": [
            {
                "bahn_nr": b["bahn_nr"],
                "team_nummer": b["team_nummer"],
                "zeit_laeufer1": b["zeit_laeufer1"],
                "zeit_laeufer2": b["zeit_laeufer2"],
                "zeit_laeufer3": b["zeit_laeufer3"],
                "zeit_laeufer4": b["zeit_laeufer4"],
            }
            for b in bahnen
        ],
    }


class LaufImportWorker(threading.Thread):
    def __init__(self, db_verbindung, webapp_url: str, api_key: str, intervall_s: int,
                 auf_status_geaendert: Callable[[dict], None] | None = None):
        super().__init__(daemon=True)
        self._db = db_verbindung
        self._url = importieren_url(webapp_url)
        self._api_key = api_key
        self._intervall_s = intervall_s
        self._auf_status_geaendert = auf_status_geaendert or (lambda status: None)
        self._stop_angefordert = threading.Event()

    def stoppen(self) -> None:
        self._stop_angefordert.set()

    def run(self) -> None:
        while not self._stop_angefordert.is_set():
            try:
                self._zyklus_durchfuehren()
            except Exception as exc:   # darf die App nie zum Absturz bringen
                self._auf_status_geaendert({"fehler": str(exc)})
            self._stop_angefordert.wait(self._intervall_s)

    def _zyklus_durchfuehren(self) -> None:
        for lauf in datenbank.offene_lokale_laeufe(self._db):
            self._lauf_senden(lauf)

    def _lauf_senden(self, lauf) -> None:
        bahnen = datenbank.lokale_bahnen(self._db, lauf["id"])
        nutzlast = lauf_zu_nutzlast(lauf, bahnen)
        versucht_um = datetime.now(timezone.utc).isoformat()
        try:
            antwort = requests.post(
                self._url, json=nutzlast, headers={"X-API-Key": self._api_key},
                timeout=HTTP_TIMEOUT_S,
            )
        except requests.RequestException as exc:
            self._auf_status_geaendert({"gesendet": False, "fehler": str(exc)})
            return

        if antwort.status_code != 200:
            self._auf_status_geaendert({"gesendet": False, "status_code": antwort.status_code})
            return

        server_lauf_id = antwort.json()["server_lauf_id"]
        alle_fertig = bool(bahnen) and all(b["zeit_laeufer4"] is not None for b in bahnen)
        if alle_fertig:
            datenbank.lokalen_lauf_als_gesendet_markieren(
                self._db, lauf["id"], server_lauf_id, versucht_um)
        else:
            datenbank.lokalen_lauf_versuch_vermerken(
                self._db, lauf["id"], server_lauf_id, versucht_um)
        self._auf_status_geaendert({"gesendet": True, "vollstaendig": alle_fertig})
