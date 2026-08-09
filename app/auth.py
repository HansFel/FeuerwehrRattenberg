"""Einfacher Bearbeiter-Schutz per gemeinsamem Passwort.

Ansehen ist für alle frei. Ändernde Aktionen (anlegen/bearbeiten/löschen,
Ergebnisse erfassen, Startlisten speichern) erfordern eine Anmeldung mit dem
gemeinsamen Wettbewerbs-Passwort. Kein Benutzerkonzept – bewusst simpel für
den Einsatz am Eventtag auf ein paar Geräten im WLAN.
"""
from __future__ import annotations

from functools import wraps

from flask import (current_app, flash, redirect, request, session, url_for)


def passwort_korrekt(eingabe: str) -> bool:
    return eingabe == current_app.config["WETTBEWERB_PASSWORT"]


def ist_angemeldet() -> bool:
    return bool(session.get("bearbeiter"))


def bearbeiter_noetig(view):
    """Decorator: leitet nicht angemeldete Nutzer zur Anmeldung um."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not ist_angemeldet():
            flash("Bitte zuerst als Bearbeiter anmelden.", "error")
            return redirect(url_for("auth.login", next=request.full_path))
        return view(*args, **kwargs)
    return wrapper
