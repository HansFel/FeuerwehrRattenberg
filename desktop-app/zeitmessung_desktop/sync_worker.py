"""Hintergrund-Thread: sendet gepufferte Ereignisse an den bestehenden
/api/zeitmessung/event-Endpoint der Webapp. Läuft unabhängig vom seriellen
Empfang - ein Netzausfall verzögert nur den Sync, verliert aber keine
Ereignisse (die bleiben einfach 'ausstehend' in der lokalen Datenbank und
werden beim nächsten Zyklus erneut versucht)."""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Callable

import requests

from . import datenbank

HTTP_TIMEOUT_S = 5


def ereignis_zu_nutzlast(zeile, geraet_id: str) -> dict:
    return {
        "geraet_id": geraet_id,
        "bahn": zeile["bahn"],
        "kontakt": "kontakt",
        "geraet_millis": zeile["geraet_millis"],
        "geraet_zeit_iso": "",
        "client_event_id": zeile["client_event_id"],
    }


class SyncWorker(threading.Thread):
    def __init__(self, db_verbindung, webapp_url: str, api_key: str, geraet_id: str,
                 intervall_s: int, auf_status_geaendert: Callable[[dict], None] | None = None):
        super().__init__(daemon=True)
        self._db = db_verbindung
        self._webapp_url = webapp_url
        self._api_key = api_key
        self._geraet_id = geraet_id
        self._intervall_s = intervall_s
        self._auf_status_geaendert = auf_status_geaendert or (lambda status: None)
        self._stop_angefordert = threading.Event()

    def stoppen(self) -> None:
        self._stop_angefordert.set()

    def run(self) -> None:
        while not self._stop_angefordert.is_set():
            try:
                self._zyklus_durchfuehren()
            except Exception as exc:   # Sync darf die App nie zum Absturz bringen
                self._auf_status_geaendert({"fehler": str(exc)})
            self._stop_angefordert.wait(self._intervall_s)

    def _zyklus_durchfuehren(self) -> None:
        ausstehend = datenbank.ausstehende_ereignisse(self._db)
        for zeile in ausstehend:
            self._ereignis_senden(zeile)

    def _ereignis_senden(self, zeile) -> None:
        versucht_um = datetime.now(timezone.utc).isoformat()
        nutzlast = ereignis_zu_nutzlast(zeile, self._geraet_id)
        try:
            antwort = requests.post(
                self._webapp_url, json=nutzlast,
                headers={"X-API-Key": self._api_key}, timeout=HTTP_TIMEOUT_S,
            )
        except requests.RequestException as exc:
            datenbank.versuch_vermerken(self._db, zeile["id"], versucht_um)
            self._auf_status_geaendert({"gesendet": False, "fehler": str(exc)})
            return

        if antwort.status_code in (200, 201):
            server_id = (antwort.json() or {}).get("id")
            datenbank.als_gesendet_markieren(self._db, zeile["id"], server_id, versucht_um)
            self._auf_status_geaendert({"gesendet": True, "id": zeile["id"]})
        else:
            datenbank.versuch_vermerken(self._db, zeile["id"], versucht_um)
            self._auf_status_geaendert({"gesendet": False, "status_code": antwort.status_code})
