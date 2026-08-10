"""Authentifizierung & Rollen für die Organisator-Mannschaft.

Konzept aus MGRSoftware übernommen: Benutzer mit Login (flask-login),
Passwort-Hashing (werkzeug) und benannten Rollen. Rollen:
administrator, organisator, startrichter, punkterichter – der Administrator
hat implizit alle Rechte. Das Ansehen der Seiten bleibt frei; nur ändernde
Aktionen erfordern die passende Rolle.
"""
from __future__ import annotations

from functools import wraps

from flask import flash, redirect, request, session, url_for
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
    """True, wenn angemeldet und Administrator oder eine erlaubte Rolle.

    Prüft die tatsächlich zugewiesenen Rollen (nicht die aktive) – ein
    Rollenwechsel ändert die Dashboard-Ansicht, nicht die Berechtigungen.
    """
    return current_user.is_authenticated and current_user.darf(*erlaubte_rollen)


SESSION_ROLLE = "aktive_rolle"


def aktive_rolle() -> str | None:
    """Die aktuell gewählte Rolle des Benutzers (steuert das Dashboard).

    Fällt auf die einzige Rolle zurück, wenn der Benutzer nur eine hat.
    """
    if not current_user.is_authenticated:
        return None
    gewaehlt = session.get(SESSION_ROLLE)
    rollen = current_user.rollen_namen
    if gewaehlt in rollen:
        return gewaehlt
    if len(rollen) == 1:
        return rollen[0]
    return None


def setze_aktive_rolle(rolle: str) -> bool:
    """Setzt die aktive Rolle, wenn sie dem Benutzer zugewiesen ist."""
    if current_user.is_authenticated and rolle in current_user.rollen_namen:
        session[SESSION_ROLLE] = rolle
        return True
    return False


def dashboard_zeigt(*rollen: str) -> bool:
    """True, wenn die aktive Rolle das Dashboard-Element sehen soll.

    Administrator sieht als aktive Rolle alle Bereiche.
    """
    aktiv = aktive_rolle()
    if aktiv == "administrator":
        return True
    return aktiv in rollen


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
