"""Authentifizierung & Rollen für die Organisator-Mannschaft.

Konzept aus MGRSoftware übernommen: Benutzer mit Login (flask-login),
Passwort-Hashing (werkzeug) und benannten Rollen. Rollen:
administrator, organisator, startrichter, punkterichter – der Administrator
hat implizit alle Rechte. Das Ansehen der Seiten bleibt frei; nur ändernde
Aktionen erfordern die passende Rolle.
"""
from __future__ import annotations

from functools import wraps

from flask import flash, redirect, request, url_for
from flask_login import LoginManager, current_user

from .models import Benutzer

login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Bitte zuerst anmelden."
login_manager.login_message_category = "error"


@login_manager.user_loader
def _benutzer_laden(benutzer_id: str):
    return db_get_benutzer(int(benutzer_id))


def db_get_benutzer(benutzer_id: int):
    return Benutzer.query.get(benutzer_id)


def authentifiziere(username: str, passwort: str):
    """Prüft Login-Daten, gibt aktiven Benutzer zurück oder None."""
    benutzer = Benutzer.query.filter_by(username=username, aktiv=True).first()
    if benutzer and benutzer.check_password(passwort):
        return benutzer
    return None


def ist_angemeldet() -> bool:
    return current_user.is_authenticated


def darf(*erlaubte_rollen: str) -> bool:
    """True, wenn angemeldet und Administrator oder eine erlaubte Rolle."""
    return current_user.is_authenticated and current_user.darf(*erlaubte_rollen)


def rolle_noetig(*erlaubte_rollen: str):
    """Decorator: verlangt Anmeldung und eine der erlaubten Rollen.

    Administrator kommt immer durch. Nicht angemeldet -> Anmeldung;
    angemeldet ohne Recht -> Hinweis und zurück zur Übersicht.
    """
    def deco(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                flash("Bitte zuerst anmelden.", "error")
                return redirect(url_for("auth.login", next=request.full_path))
            if not current_user.darf(*erlaubte_rollen):
                flash("Dafür fehlt dir die nötige Rolle.", "error")
                return redirect(url_for("start.index"))
            return view(*args, **kwargs)
        return wrapper
    return deco
