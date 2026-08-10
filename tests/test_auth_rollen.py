"""Tests für Login und Rollensystem (Konzept aus MGRSoftware)."""
import pytest

from app import create_app
from app.models import db, Team, Disziplin, Benutzer, BenutzerRolle, WERTUNG_ZEIT


@pytest.fixture
def app():
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "ADMIN_STARTPASSWORT": "admin",
    })
    with app.app_context():
        db.create_all()
        d = Disziplin(name="Löschangriff", wertungsart=WERTUNG_ZEIT)
        db.session.add(d)
        # Punkterichter-Benutzer anlegen
        pr = Benutzer(username="punkt", name="Peter", aktiv=True)
        pr.set_password("pw")
        pr.rollen.append(BenutzerRolle(rolle="punkterichter"))
        db.session.add(pr)
        db.session.commit()
        yield app


@pytest.fixture
def client(app):
    return app.test_client()


def _login(client, username, passwort):
    return client.post("/anmelden",
                       data={"username": username, "passwort": passwort},
                       follow_redirects=True)


def test_standard_admin_wurde_angelegt(app):
    with app.app_context():
        admin = Benutzer.query.filter_by(username="admin").first()
        assert admin is not None
        assert admin.ist_admin()
        assert admin.check_password("admin")


def test_ohne_login_kein_schreiben(client):
    antwort = client.post("/teams/neu", data={"name": "X"},
                          follow_redirects=True)
    assert "anmelden".encode() in antwort.data.lower()
    assert Team.query.filter_by(name="X").first() is None


def test_falsche_zugangsdaten(client):
    antwort = _login(client, "admin", "falsch")
    assert "falsch".encode() in antwort.data.lower()


def test_admin_darf_team_anlegen(client):
    _login(client, "admin", "admin")
    client.post("/teams/neu", data={"name": "FF Admin"})
    assert Team.query.filter_by(name="FF Admin").first() is not None


def test_rolle_reicht_nicht_fuer_fremde_aktion(client):
    # Punkterichter darf KEINE Mannschaft anlegen (das ist Organisator/Admin)
    _login(client, "punkt", "pw")
    antwort = client.post("/teams/neu", data={"name": "Verboten"},
                          follow_redirects=True)
    assert Team.query.filter_by(name="Verboten").first() is None
    assert "rolle".encode() in antwort.data.lower()


def test_punkterichter_darf_ergebnis_erfassen(client):
    _login(client, "punkt", "pw")
    team = Team(name="Team1")
    db.session.add(team)
    db.session.commit()
    d = Disziplin.query.first()
    client.post(f"/wertung/disziplin/{d.id}",
                data={"team_id": team.id, "zeit_sekunden": "42"})
    from app.models import Ergebnis
    assert Ergebnis.query.filter_by(team_id=team.id).first() is not None


def test_benutzerverwaltung_nur_admin(client):
    # Punkterichter kommt nicht in die Benutzerverwaltung
    _login(client, "punkt", "pw")
    antwort = client.get("/benutzer/", follow_redirects=True)
    assert "Benutzer der Organisator".encode() not in antwort.data
    # Admin schon
    client.post("/abmelden")
    _login(client, "admin", "admin")
    antwort = client.get("/benutzer/")
    assert antwort.status_code == 200
    assert "Organisator-Mannschaft".encode() in antwort.data
