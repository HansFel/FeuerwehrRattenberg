"""Tests für die manuelle Notfall-Zeiterfassung (Fallback, falls die
automatische ESP32-zu-Lauf-Zuordnung ausfällt)."""
import pytest

from app import create_app
from app.models import (db, Team, Mitglied, Benutzer, BenutzerRolle,
                        NotfallLauf, NotfallBahn)


@pytest.fixture
def app():
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "ADMIN_STARTPASSWORT": "admin",
    })
    with app.app_context():
        db.create_all()
        for i, name in enumerate(("FF Rattenberg", "FF Kobenz"), start=1):
            team = Team(name=name, startnummer=i)
            for pos in range(1, 5):
                team.mitglieder.append(Mitglied(
                    vorname=f"Läufer{pos}", nachname=name, position=pos,
                    name=f"Läufer{pos} {name}"))
            db.session.add(team)

        startrichter = Benutzer(username="richter", name="Rita", aktiv=True)
        startrichter.set_password("pw")
        startrichter.rollen.append(BenutzerRolle(rolle="startrichter"))
        db.session.add(startrichter)

        kellner = Benutzer(username="kellner1", aktiv=True)
        kellner.set_password("pw")
        kellner.rollen.append(BenutzerRolle(rolle="kellner"))
        db.session.add(kellner)
        db.session.commit()
        yield app


@pytest.fixture
def client(app):
    return app.test_client()


def _login(client, username, pw):
    return client.post("/anmelden", data={"username": username, "passwort": pw})


def test_notfall_erfordert_rolle(client):
    r = client.get("/notfall/", follow_redirects=True)
    assert "anmelden".encode() in r.data.lower()

    _login(client, "kellner1", "pw")
    r = client.get("/notfall/", follow_redirects=True)
    assert "Notfall-Zeiterfassung".encode() not in r.data


def test_lauf_anlegen_und_bahnen_erstellt(client, app):
    _login(client, "richter", "pw")
    with app.app_context():
        t1 = Team.query.filter_by(name="FF Rattenberg").first()
        t2 = Team.query.filter_by(name="FF Kobenz").first()

    r = client.post("/notfall/neu", data={
        "bezeichnung": "Vorrunde Lauf 1",
        "team_1": str(t1.id), "team_2": str(t2.id),
        "team_3": "", "team_4": "",
    }, follow_redirects=True)
    assert r.status_code == 200

    with app.app_context():
        lauf = NotfallLauf.query.filter_by(bezeichnung="Vorrunde Lauf 1").first()
        assert lauf is not None
        assert len(lauf.bahnen) == 4
        bahn1 = next(b for b in lauf.bahnen if b.bahn_nr == 1)
        bahn3 = next(b for b in lauf.bahnen if b.bahn_nr == 3)
        assert bahn1.team_id == t1.id
        assert bahn3.team_id is None


def test_leerer_lauf_wird_abgelehnt(client, app):
    _login(client, "richter", "pw")
    r = client.post("/notfall/neu", data={
        "bezeichnung": "Nichts", "team_1": "", "team_2": "", "team_3": "", "team_4": "",
    }, follow_redirects=True)
    assert "mindestens eine Bahn".encode() in r.data
    with app.app_context():
        assert NotfallLauf.query.count() == 0


def test_zeiten_erfassen_und_summe(client, app):
    _login(client, "richter", "pw")
    with app.app_context():
        t1 = Team.query.filter_by(name="FF Rattenberg").first()
        lauf = NotfallLauf(bezeichnung="Test")
        lauf.bahnen.append(NotfallBahn(bahn_nr=1, team_id=t1.id))
        lauf.bahnen.append(NotfallBahn(bahn_nr=2))
        lauf.bahnen.append(NotfallBahn(bahn_nr=3))
        lauf.bahnen.append(NotfallBahn(bahn_nr=4))
        db.session.add(lauf)
        db.session.commit()
        lauf_id = lauf.id
        bahn1_id = lauf.bahnen[0].id

    r = client.post(f"/notfall/{lauf_id}", data={
        f"zeit_{bahn1_id}_1": "12,5",
        f"zeit_{bahn1_id}_2": "11.20",
        f"zeit_{bahn1_id}_3": "13",
        f"zeit_{bahn1_id}_4": "10,8",
    }, follow_redirects=True)
    assert r.status_code == 200

    with app.app_context():
        bahn = db.session.get(NotfallBahn, bahn1_id)
        assert bahn.zeit_laeufer1 == pytest.approx(12.5)
        assert bahn.zeit_laeufer2 == pytest.approx(11.2)
        assert bahn.zeit_laeufer3 == pytest.approx(13.0)
        assert bahn.zeit_laeufer4 == pytest.approx(10.8)
        assert bahn.gesamtzeit == pytest.approx(12.5 + 11.2 + 13.0 + 10.8)
        assert "47.50".encode() in r.data or "47,50".encode() in r.data


def test_teilweise_erfasste_zeiten_keine_summe(client, app):
    _login(client, "richter", "pw")
    with app.app_context():
        t1 = Team.query.filter_by(name="FF Rattenberg").first()
        lauf = NotfallLauf(bezeichnung="Teilweise")
        lauf.bahnen.append(NotfallBahn(bahn_nr=1, team_id=t1.id))
        db.session.add(lauf)
        db.session.commit()
        lauf_id = lauf.id
        bahn_id = lauf.bahnen[0].id

    client.post(f"/notfall/{lauf_id}", data={
        f"zeit_{bahn_id}_1": "10", f"zeit_{bahn_id}_2": "11",
    })
    with app.app_context():
        bahn = db.session.get(NotfallBahn, bahn_id)
        assert bahn.zeit_laeufer1 == 10.0
        assert bahn.zeit_laeufer2 == 11.0
        assert bahn.zeit_laeufer3 is None
        assert bahn.gesamtzeit is None


def test_organisator_darf_loeschen_startrichter_nicht(client, app):
    with app.app_context():
        lauf = NotfallLauf(bezeichnung="Zu löschen")
        db.session.add(lauf)
        db.session.commit()
        lauf_id = lauf.id

    _login(client, "richter", "pw")
    r = client.post(f"/notfall/{lauf_id}/loeschen", follow_redirects=True)
    assert "rolle".encode() in r.data.lower()
    with app.app_context():
        assert db.session.get(NotfallLauf, lauf_id) is not None
