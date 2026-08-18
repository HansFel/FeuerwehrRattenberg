"""Tests fuer die oeffentliche Besucheransicht (kein Login noetig)."""
import pytest

from app import create_app
from app.models import db, Team, Disziplin, Startplatz


@pytest.fixture
def app():
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "ADMIN_STARTPASSWORT": "admin",
    })
    with app.app_context():
        db.create_all()
        yield app


@pytest.fixture
def client(app):
    return app.test_client()


def test_besucheransicht_ohne_login_erreichbar(client):
    r = client.get("/besucher/")
    assert r.status_code == 200
    assert "anmelden".encode() not in r.data.lower() or "🔒".encode() in r.data


def test_besucheransicht_zeigt_gesamtwertung_und_zeitplan(client, app):
    with app.app_context():
        d = Disziplin(name="Siloplanen-Race")
        team = Team(name="Sichtbares Team")
        db.session.add_all([d, team])
        db.session.commit()
        db.session.add(Startplatz(team_id=team.id, disziplin_id=d.id,
                                  startnummer=1, heat="Vorrunde 1",
                                  ergebnis_sekunden=42.0, startzeit="10:00"))
        db.session.commit()

    r = client.get("/besucher/")
    assert r.status_code == 200
    text = r.data.decode("utf-8")
    assert "Sichtbares Team" in text
    assert "Vorrunde 1" in text
    assert "10:00" in text


def test_besucheransicht_ohne_daten_zeigt_leer_meldung(client):
    r = client.get("/besucher/")
    assert r.status_code == 200
    assert "leer".encode() in r.data.lower() or "noch keine".encode() in r.data.lower()


def test_besucheransicht_zeigt_keine_admin_aktionen(client, app):
    """Reine Anzeige - keine Formulare/Buttons zum Bearbeiten."""
    with app.app_context():
        d = Disziplin(name="Siloplanen-Race")
        team = Team(name="Team")
        db.session.add_all([d, team])
        db.session.commit()
        db.session.add(Startplatz(team_id=team.id, disziplin_id=d.id,
                                  startnummer=1, heat="Vorrunde 1"))
        db.session.commit()

    r = client.get("/besucher/")
    assert b'method="post"' not in r.data
