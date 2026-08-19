"""Hintergrund-Thread: fragt periodisch den aktiven NotfallLauf der Webapp ab
(/notfall/api/aktiv) und liefert Bahn/Team/Läuferzeiten für die Live-Anzeige.
Rein lesend - die eigentliche Zuordnung/Berechnung passiert serverseitig
(siehe app/blueprints/zeitmessung.py:_automatische_zuordnung_pruefen), diese
App zeigt nur an, was die Webapp bereits berechnet hat."""
from __future__ import annotations

import threading
from typing import Callable

import requests

from .webapp_urls import aktiver_lauf_url

HTTP_TIMEOUT_S = 5


class LaufWorker(threading.Thread):
    def __init__(self, webapp_url: str, api_key: str, intervall_s: int,
                 auf_lauf_aktualisiert: Callable[[dict], None],
                 auf_status_geaendert: Callable[[dict], None] | None = None):
        super().__init__(daemon=True)
        self._url = aktiver_lauf_url(webapp_url)
        self._api_key = api_key
        self._intervall_s = intervall_s
        self._auf_lauf_aktualisiert = auf_lauf_aktualisiert
        self._auf_status_geaendert = auf_status_geaendert or (lambda status: None)
        self._stop_angefordert = threading.Event()

    def stoppen(self) -> None:
        self._stop_angefordert.set()

    def run(self) -> None:
        while not self._stop_angefordert.is_set():
            try:
                antwort = requests.get(
                    self._url, headers={"X-API-Key": self._api_key},
                    timeout=HTTP_TIMEOUT_S,
                )
                if antwort.status_code == 200:
                    self._auf_lauf_aktualisiert(antwort.json())
                    self._auf_status_geaendert({"erfolgreich": True})
                else:
                    self._auf_status_geaendert(
                        {"erfolgreich": False, "status_code": antwort.status_code})
            except requests.RequestException as exc:
                self._auf_status_geaendert({"erfolgreich": False, "fehler": str(exc)})
            except Exception as exc:   # niemals den Thread lautlos sterben lassen
                self._auf_status_geaendert({"erfolgreich": False, "fehler": f"unerwartet: {exc}"})
            self._stop_angefordert.wait(self._intervall_s)
