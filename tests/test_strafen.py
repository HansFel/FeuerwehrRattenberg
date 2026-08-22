"""Tests fuer den Strafenkatalog fuer Punkterichter."""
import pytest

from app import create_app
from app.models import (db, Team, Strafe, Benutzer, BenutzerRolle,
                        Disziplin, Startplatz, ModeratorStatus)


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
        team_c = Team(name="Team C", startnummer=3)   # NICHT im aktuellen Heat
        db.session.add_all([team_a, team_b, team_c])

        startrichter = Benutzer(username="start1", aktiv=True)
        startrichter.set_password("pw")
        startrichter.rollen.append(BenutzerRolle(rolle="startrichter"))
        db.session.add(startrichter)

        punkterichter = Benutzer(username="punkt1", aktiv=True)
        punkterichter.set_password("pw")
        punkterichter.rollen.append(BenutzerRolle(rolle="punkterichter"))
        db.session.add(punkterichter)
        db.session.commit()

        # Team A + B laufen im aktuellen Heat, Team C in einem anderen.
        disziplin = Disziplin(name="Siloplanen-Race")
        db.session.add(disziplin)
        db.session.commit()
        db.session.add_all([
            Startplatz(team_id=team_a.id, disziplin_id=disziplin.id,
                      startnummer=1, heat="Vorrunde 1"),
            Startplatz(team_id=team_b.id, disziplin_id=disziplin.id,
                      startnummer=2, heat="Vorrunde 1"),
            Startplatz(team_id=team_c.id, disziplin_id=disziplin.id,
                      startnummer=1, heat="Vorrunde 2"),
        ])
        db.session.add(ModeratorStatus(id=1, disziplin_id=disziplin.id,
                                       heat="Vorrunde 1"))
        db.session.commit()
        yield app


@pytest.fixture
def client(app):
    return app.test_client()


def _login(client, user, pw):
    return client.post("/anmelden", data={"username": user, "passwort": pw})


def test_strafen_dashboard_erfordert_punkterichter(client):
    _login(client, "start1", "pw")
    r = client.get("/strafen/", follow_redirects=True)
    assert r.status_code == 200
    assert "Strafenkatalog".encode() not in r.data


def test_strafen_dashboard_zeigt_katalog(client):
    _login(client, "punkt1", "pw")
    r = client.get("/strafen/")
    assert r.status_code == 200
    assert "Strafenkatalog".encode() in r.data
    assert "Getränk wird weggeschüttet".encode() in r.data
    assert "Kotzen ins Wasserbecken".encode() in r.data
    assert "+60 s".encode() in r.data or "+60".encode() in r.data


def test_strafe_fest_vergeben(client, app):
    _login(client, "punkt1", "pw")
    with app.app_context():
        team = Team.query.filter_by(name="Team A").first()
        team_id = team.id

    r = client.post("/strafen/vergeben", data={
        "team_id": str(team_id),
        "regel_nr": "1",
    }, follow_redirects=True)
    assert r.status_code == 200
    assert "Strafe(n) vergeben".encode() in r.data
    assert "+60 s".encode() in r.data

    with app.app_context():
        strafe = Strafe.query.one()
        assert strafe.team_id == team_id
        assert strafe.regel_nr == "1"
        assert strafe.sekunden == 60.0
        assert strafe.erfasst_von == "punkt1"


def test_strafe_variabel_vergeben(client, app):
    _login(client, "punkt1", "pw")
    with app.app_context():
        team = Team.query.filter_by(name="Team B").first()
        team_id = team.id

    r = client.post("/strafen/vergeben", data={
        "team_id": str(team_id),
        "regel_nr": "3.1",
        "menge_3.1": "15",
    }, follow_redirects=True)
    assert r.status_code == 200
    assert "Strafe(n) vergeben".encode() in r.data

    with app.app_context():
        strafe = Strafe.query.one()
        assert strafe.sekunden == 15.0
        assert strafe.regel_nr == "3.1"


def test_strafe_variabel_ohne_menge_abgelehnt(client, app):
    _login(client, "punkt1", "pw")
    with app.app_context():
        team = Team.query.first()
        team_id = team.id

    r = client.post("/strafen/vergeben", data={
        "team_id": str(team_id),
        "regel_nr": "3.1",
    }, follow_redirects=True)
    assert "Bitte eine Menge".encode() in r.data
    assert Strafe.query.count() == 0


def test_strafe_mehrfachauswahl_erzeugt_mehrere_strafen(client, app):
    """Mehrere Regeln (fest + variabel) in einem Absenden auswaehlen -
    jede erzeugt eine eigene Strafe."""
    _login(client, "punkt1", "pw")
    with app.app_context():
        team = Team.query.filter_by(name="Team A").first()
        team_id = team.id

    r = client.post("/strafen/vergeben", data={
        "team_id": str(team_id),
        "regel_nr": ["1", "4", "3.1"],
        "menge_3.1": "10",
    }, follow_redirects=True)
    assert r.status_code == 200
    assert "3 Strafe(n) vergeben".encode() in r.data

    with app.app_context():
        strafen = Strafe.query.filter_by(team_id=team_id).order_by(Strafe.regel_nr).all()
        assert len(strafen) == 3
        nach_regel = {s.regel_nr: s.sekunden for s in strafen}
        assert nach_regel["1"] == 60.0
        assert nach_regel["4"] == 5.0
        assert nach_regel["3.1"] == 10.0


def test_strafe_ohne_team_abgelehnt(client):
    _login(client, "punkt1", "pw")
    r = client.post("/strafen/vergeben", data={
        "regel_nr": "1",
    }, follow_redirects=True)
    assert "Bitte ein Team".encode() in r.data
    assert Strafe.query.count() == 0


def test_strafe_fuer_team_ausserhalb_des_aktuellen_heats_abgelehnt(client, app):
    """Team C laeuft laut Fixture im Heat 'Vorrunde 2', der Moderator hat
    aber 'Vorrunde 1' aktiv - Team C darf keine Strafe bekommen."""
    _login(client, "punkt1", "pw")
    with app.app_context():
        team_c = Team.query.filter_by(name="Team C").first()
        team_c_id = team_c.id

    r = client.post("/strafen/vergeben", data={
        "team_id": str(team_c_id),
        "regel_nr": "1",
    }, follow_redirects=True)
    assert "nicht im aktuellen Lauf".encode() in r.data
    assert Strafe.query.count() == 0


def test_team_auswahl_zeigt_nur_aktuellen_heat(client):
    _login(client, "punkt1", "pw")
    r = client.get("/strafen/")
    assert "Team A".encode() in r.data
    assert "Team B".encode() in r.data
    assert "Team C".encode() not in r.data


def test_strafe_loeschen(client, app):
    _login(client, "punkt1", "pw")
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


def test_strafe_fuer_team_des_unmittelbar_vorherigen_heats_erlaubt(client, app):
    """Bugfix 2026-08-21: das automatische Weiterschalten des Moderator-
    Status (moderator.py:_lauf_automatisch_weiterruecken) springt sofort
    zum naechsten Heat, sobald alle Zeiten eines Laufs da sind - ohne
    dieses Fenster wuerde ein Team fuer eine Strafe unerreichbar, kaum dass
    sein eigener Lauf fertig ist. Team C (Vorrunde 2) muss also erlaubt
    sein, wenn der Moderator-Status inzwischen auf 'Vorrunde 3' steht."""
    with app.app_context():
        team_c = Team.query.filter_by(name="Team C").first()
        team_c_id = team_c.id
        disziplin = Disziplin.query.first()
        # Team D laeuft in einer dritten Runde - wird selbst zum aktuellen
        # Heat, "Vorrunde 2" (Team C) ist dann das unmittelbar VORHERIGE.
        team_d = Team(name="Team D", startnummer=4)
        db.session.add(team_d)
        db.session.flush()
        db.session.add(Startplatz(team_id=team_d.id, disziplin_id=disziplin.id,
                                  startnummer=1, heat="Vorrunde 3"))
        status = db.session.get(ModeratorStatus, 1)
        status.heat = "Vorrunde 3"
        db.session.commit()

    _login(client, "punkt1", "pw")
    r = client.post("/strafen/vergeben", data={
        "team_id": str(team_c_id),
        "regel_nr": "1",
    }, follow_redirects=True)
    assert "Strafe(n) vergeben".encode() in r.data
    with app.app_context():
        assert Strafe.query.filter_by(team_id=team_c_id).count() == 1


def test_strafe_fuer_team_zwei_heats_zurueck_bleibt_abgelehnt(client, app):
    """Das Gnadenfenster gilt nur fuer den unmittelbar VORHERIGEN Lauf, nicht
    beliebig weit zurueck - Team A (Vorrunde 1) darf keine Strafe mehr
    bekommen, sobald 'Vorrunde 3' aktuell ist (Vorrunde 2 liegt dazwischen)."""
    with app.app_context():
        team_a = Team.query.filter_by(name="Team A").first()
        team_a_id = team_a.id
        disziplin = Disziplin.query.first()
        team_d = Team(name="Team D", startnummer=4)
        db.session.add(team_d)
        db.session.flush()
        db.session.add(Startplatz(team_id=team_d.id, disziplin_id=disziplin.id,
                                  startnummer=1, heat="Vorrunde 3"))
        status = db.session.get(ModeratorStatus, 1)
        status.heat = "Vorrunde 3"
        db.session.commit()

    _login(client, "punkt1", "pw")
    r = client.post("/strafen/vergeben", data={
        "team_id": str(team_a_id),
        "regel_nr": "1",
    }, follow_redirects=True)
    assert "nicht im aktuellen Lauf".encode() in r.data
    assert Strafe.query.count() == 0


def test_strafen_summe_je_team(client, app):
    _login(client, "punkt1", "pw")
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

