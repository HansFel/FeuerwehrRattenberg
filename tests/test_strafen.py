"""Tests fuer den Strafenkatalog fuer Startrichter."""
import pytest

from app import create_app
from app.models import db, Team, Strafe, Benutzer, BenutzerRolle


@pytest.fixture
def app():
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "ADMIN_STARTPASSWORT": "admin",
    })
    with app.app_context():
        db.create_all()
        team_a = Team(name="Team A", startnummer=1)
        team_b = Team(name="Team B", startnummer=2)
        db.session.add_all([team_a, team_b])

        startrichter = Benutzer(username="start1", aktiv=True)
        startrichter.set_password("pw")
        startrichter.rollen.append(BenutzerRolle(rolle="startrichter"))
        db.session.add(startrichter)

        punkterichter = Benutzer(username="punkt1", aktiv=True)
        punkterichter.set_password("pw")
        punkterichter.rollen.append(BenutzerRolle(rolle="punkterichter"))
        db.session.add(punkterichter)
        db.session.commit()
        yield app


@pytest.fixture
def client(app):
    return app.test_client()


def _login(client, user, pw):
    return client.post("/anmelden", data={"username": user, "passwort": pw})


def test_strafen_dashboard_erfordert_startrichter(client):
    _login(client, "punkt1", "pw")
    r = client.get("/strafen/", follow_redirects=True)
    assert r.status_code == 200
    assert "Strafenkatalog".encode() not in r.data


def test_strafen_dashboard_zeigt_katalog(client):
    _login(client, "start1", "pw")
    r = client.get("/strafen/")
    assert r.status_code == 200
    assert "Strafenkatalog".encode() in r.data
    assert "Getränk wird weggeschüttet".encode() in r.data
    assert "Kotzen ins Wasserbecken".encode() in r.data
    assert "+60 s".encode() in r.data or "+60".encode() in r.data


def test_strafe_fest_vergeben(client, app):
    _login(client, "start1", "pw")
    with app.app_context():
        team = Team.query.filter_by(name="Team A").first()
        team_id = team.id

    r = client.post("/strafen/vergeben", data={
        "team_id": str(team_id),
        "regel_nr": "1",
    }, follow_redirects=True)
    assert r.status_code == 200
    assert "Strafe vergeben".encode() in r.data
    assert "+60 s".encode() in r.data

    with app.app_context():
        strafe = Strafe.query.one()
        assert strafe.team_id == team_id
        assert strafe.regel_nr == "1"
        assert strafe.sekunden == 60.0
        assert strafe.erfasst_von == "start1"


def test_strafe_variabel_vergeben(client, app):
    _login(client, "start1", "pw")
    with app.app_context():
        team = Team.query.filter_by(name="Team B").first()
        team_id = team.id

    r = client.post("/strafen/vergeben", data={
        "team_id": str(team_id),
        "regel_nr": "3.1",
        "menge": "15",
    }, follow_redirects=True)
    assert r.status_code == 200
    assert "Strafe vergeben".encode() in r.data

    with app.app_context():
        strafe = Strafe.query.one()
        assert strafe.sekunden == 15.0
        assert strafe.regel_nr == "3.1"


def test_strafe_variabel_ohne_menge_abgelehnt(client, app):
    _login(client, "start1", "pw")
    with app.app_context():
        team = Team.query.first()
        team_id = team.id

    r = client.post("/strafen/vergeben", data={
        "team_id": str(team_id),
        "regel_nr": "3.1",
    }, follow_redirects=True)
    assert "Bitte eine Menge".encode() in r.data
    assert Strafe.query.count() == 0


def test_strafe_ohne_team_abgelehnt(client):
    _login(client, "start1", "pw")
    r = client.post("/strafen/vergeben", data={
        "regel_nr": "1",
    }, follow_redirects=True)
    assert "Bitte ein Team".encode() in r.data
    assert Strafe.query.count() == 0


def test_strafe_loeschen(client, app):
    _login(client, "start1", "pw")
    with app.app_context():
        team = Team.query.first()
        team_id = team.id

    client.post("/strafen/vergeben", data={
        "team_id": str(team_id),
        "regel_nr": "4",
    }, follow_redirects=True)

    with app.app_context():
        strafe = Strafe.query.one()
        strafe_id = strafe.id

    r = client.post(f"/strafen/{strafe_id}/loeschen", follow_redirects=True)
    assert r.status_code == 200
    assert "geloescht".encode() in r.data or "gelöscht".encode() in r.data
    assert Strafe.query.count() == 0


def test_strafen_summe_je_team(client, app):
    _login(client, "start1", "pw")
    with app.app_context():
        team = Team.query.filter_by(name="Team A").first()
        team_id = team.id

    client.post("/strafen/vergeben", data={
        "team_id": str(team_id), "regel_nr": "4",
    }, follow_redirects=True)
    client.post("/strafen/vergeben", data={
        "team_id": str(team_id), "regel_nr": "5",
    }, follow_redirects=True)

    r = client.get("/strafen/")
    assert r.status_code == 200
    with app.app_context():
        total = sum(s.sekunden for s in Strafe.query.filter_by(team_id=team_id))
        assert total == 15.0

