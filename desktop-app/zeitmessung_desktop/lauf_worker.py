"""Hintergrund-Thread: fragt periodisch den aktiven NotfallLauf der Webapp ab
(/notfall/api/aktiv) und liefert Bahn/Team/Läuferzeiten für die Live-Anzeige.
Rein lesend - die eigentliche Zuordnung/Berechnung passiert serverseitig
(siehe app/blueprints/zeitmessung.py:_automatische_zuordnung_pruefen), diese
App zeigt nur an, was die Webapp bereits berechnet hat."""
from __future__ import annotations

import threading
from typing import Callable

import requests

HTTP_TIMEOUT_S = 5

_EVENT_PFAD = "/api/zeitmessung/event"


def aktiver_lauf_url(webapp_url: str) -> str:
    """Leitet die Notfall-API-URL aus der bekannten Zeitmessung-Event-URL ab
    (keine zusätzliche Einstellung nötig). Ersetzt bewusst nur den bekannten
    Endpunkt-Suffix statt den ganzen Pfad (z.B. via urljoin) zu ersetzen -
    sonst würde ein Instanz-Pfadpräfix wie '/test1' verloren gehen."""
    basis = webapp_url[:-len(_EVENT_PFAD)] if webapp_url.endswith(_EVENT_PFAD) else webapp_url
    return basis + "/notfall/api/aktiv"


class LaufWorker(threading.Thread):
    def __init__(self, webapp_url: str, api_key: str, intervall_s: int,
                 auf_lauf_aktualisiert: Callable[[dict], None]):
        super().__init__(daemon=True)
        self._url = aktiver_lauf_url(webapp_url)
        self._api_key = api_key
        self._intervall_s = intervall_s
        self._auf_lauf_aktualisiert = auf_lauf_aktualisiert
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
            except requests.RequestException:
                pass   # naechster Versuch beim naechsten Intervall
            self._stop_angefordert.wait(self._intervall_s)
