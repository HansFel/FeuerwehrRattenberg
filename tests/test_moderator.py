"""Tests für Rolle und Live-Dashboard der Moderation."""
import pytest

from app import create_app
from app.models import (db, Benutzer, BenutzerRolle, Disziplin,
                        ModeratorStatus, Nachricht, Startplatz, Team)


@pytest.fixture
def app():
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "ADMIN_STARTPASSWORT": "admin",
    })
    with app.app_context():
        moderator = Benutzer(username="mod", name="Maria", aktiv=True)
        moderator.set_password("pw")
        moderator.rollen.append(BenutzerRolle(rolle="moderator"))
        organisator = Benutzer(username="orga", name="Olga", aktiv=True)
        organisator.set_password("pw")
        organisator.rollen.append(BenutzerRolle(rolle="organisator"))
        fremd = Benutzer(username="kellner", name="Karl", aktiv=True)
        fremd.set_password("pw")
        fremd.rollen.append(BenutzerRolle(rolle="kellner"))

        disziplin = Disziplin(name="Siloplanen-Race", reihenfolge=1)
        team1 = Team(name="Team Rattenberg", wehr="Rattenberg")
        team2 = Team(name="Team Brixlegg", wehr="Brixlegg")
        db.session.add_all([moderator, organisator, fremd,
                            disziplin, team1, team2])
        db.session.flush()
        db.session.add_all([
            Startplatz(team_id=team1.id, disziplin_id=disziplin.id,
                       startnummer=1, heat="Vorrunde 1"),
            Startplatz(team_id=team2.id, disziplin_id=disziplin.id,
                       startnummer=2, heat="Vorrunde 1"),
        ])
        db.session.commit()
        yield app


@pytest.fixture
def client(app):
    return app.test_client()


def _login(client, username):
    return client.post("/anmelden", data={"username": username,
                                           "passwort": "pw"})


def test_moderator_hat_eigenes_dashboard(client):
    _login(client, "mod")
    response = client.get("/moderator/")
    assert response.status_code == 200
    assert "Moderator-Dashboard".encode() in response.data
    assert "Noch kein aktueller Lauf".encode() in response.data


def test_fremde_rolle_darf_dashboard_nicht_oeffnen(client):
    _login(client, "kellner")
    response = client.get("/moderator/", follow_redirects=True)
    assert "Dafür fehlt dir die nötige Rolle".encode() in response.data


def test_organisator_waehlt_lauf_und_pflegt_informationen(client, app):
    with app.app_context():
        disziplin = Disziplin.query.filter_by(name="Siloplanen-Race").one()
        lauf = f"{disziplin.id}|Vorrunde 1"

    _login(client, "orga")
    response = client.post("/moderator/status", data={
        "lauf": lauf,
        "publikumsinfo": "Als Nächstes folgt das Finale.",
        "sponsoren": "Firma A\nFirma B",
    }, follow_redirects=True)

    assert response.status_code == 200
    assert "Team Rattenberg".encode() in response.data
    assert "Team Brixlegg".encode() in response.data
    assert "Firma A".encode() in response.data
    with app.app_context():
        status = db.session.get(ModeratorStatus, 1)
        assert status.heat == "Vorrunde 1"
        assert status.aktualisiert_von == "orga"


def test_organisator_sendet_nachricht_an_moderator(client, app):
    _login(client, "orga")
    client.post("/moderator/nachricht", data={
        "text": "Bitte jetzt Firma A erwähnen."
    })
    client.post("/abmelden")
    _login(client, "mod")
    response = client.get("/moderator/")

    assert "Bitte jetzt Firma A erwähnen.".encode() in response.data
    with app.app_context():
        nachricht = Nachricht.query.one()
        assert nachricht.ziel_rolle == "moderator"
        assert nachricht.absender == "orga"


def test_allgemeine_nachricht_erscheint_nicht_im_moderator_bereich(client, app):
    with app.app_context():
        db.session.add(Nachricht(text="Allgemeine Admin-Nachricht",
                                 absender="admin"))
        db.session.commit()
    _login(client, "mod")
    response = client.get("/moderator/")
    assert "Allgemeine Admin-Nachricht".encode() not in response.data


def test_kellner_kann_keine_moderator_nachricht_senden(client, app):
    _login(client, "kellner")
    client.post("/moderator/nachricht", data={"text": "Nicht erlaubt"})
    with app.app_context():
        assert Nachricht.query.count() == 0
