"""Leitet weitere Webapp-Endpunkt-URLs aus der bekannten Zeitmessung-Event-URL
ab (keine zusätzliche Einstellung pro Endpunkt nötig)."""
from __future__ import annotations

_EVENT_PFAD = "/api/zeitmessung/event"


def basis_url(webapp_url: str) -> str:
    """Entfernt bewusst nur den bekannten Endpunkt-Suffix statt den ganzen
    Pfad (z.B. via urljoin) zu ersetzen - sonst würde ein Instanz-Pfadpräfix
    wie '/test1' verloren gehen."""
    if webapp_url.endswith(_EVENT_PFAD):
        return webapp_url[:-len(_EVENT_PFAD)]
    return webapp_url


def aktiver_lauf_url(webapp_url: str) -> str:
    return basis_url(webapp_url) + "/notfall/api/aktiv"


def importieren_url(webapp_url: str) -> str:
    return basis_url(webapp_url) + "/notfall/api/importieren"
