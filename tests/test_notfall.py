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
        assert "47.500".encode() in r.data or "47,500".encode() in r.data


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


API_KEY = "dev-nur-lokal-zeitmessung"


def test_api_aktiv_ohne_api_key_abgelehnt(client):
    r = client.get("/notfall/api/aktiv")
    assert r.status_code == 401


def test_api_aktiv_ohne_aktiven_lauf(client):
    r = client.get("/notfall/api/aktiv", headers={"X-API-Key": API_KEY})
    assert r.status_code == 200
    assert r.get_json() == {"aktiv": False}


def test_api_aktiv_liefert_bahnen_und_laeuferzeiten(client, app):
    with app.app_context():
        t1 = Team.query.filter_by(name="FF Rattenberg").first()
        lauf = NotfallLauf(bezeichnung="API-Test", aktiv=True)
        bahn = NotfallBahn(bahn_nr=1, team_id=t1.id, zeit_laeufer1=10.123,
                           zeit_laeufer2=11.5, zeit_laeufer3=9.75, zeit_laeufer4=12.0)
        lauf.bahnen.append(bahn)
        lauf.bahnen.append(NotfallBahn(bahn_nr=2))
        db.session.add(lauf)
        db.session.commit()
        lauf_id = lauf.id

    r = client.get("/notfall/api/aktiv", headers={"X-API-Key": API_KEY})
    assert r.status_code == 200
    daten = r.get_json()
    assert daten["aktiv"] is True
    assert daten["lauf_id"] == lauf_id
    assert daten["bezeichnung"] == "API-Test"
    assert len(daten["bahnen"]) == 2

    bahn1 = next(b for b in daten["bahnen"] if b["bahn_nr"] == 1)
    assert bahn1["team_name"] == "FF Rattenberg"
    assert bahn1["gesamtzeit"] == pytest.approx(10.123 + 11.5 + 9.75 + 12.0)
    assert len(bahn1["laeufer"]) == 4
    assert bahn1["laeufer"][0]["zeit"] == pytest.approx(10.123)
    assert bahn1["laeufer"][0]["name"] == "Läufer1 FF Rattenberg"

    bahn2 = next(b for b in daten["bahnen"] if b["bahn_nr"] == 2)
    assert bahn2["team_name"] is None
    assert bahn2["laeufer"] == []


def test_api_importieren_ohne_api_key_abgelehnt(client):
    r = client.post("/notfall/api/importieren", json={"bahnen": [{"bahn_nr": 1}]})
    assert r.status_code == 401


def test_api_importieren_legt_neuen_lauf_an(client, app):
    r = client.post("/notfall/api/importieren", headers={"X-API-Key": API_KEY}, json={
        "bezeichnung": "Offline-Test",
        "bahnen": [
            {"bahn_nr": 1, "team_nummer": 1,
             "zeit_laeufer1": 10.123, "zeit_laeufer2": 11.5,
             "zeit_laeufer3": 9.75, "zeit_laeufer4": 12.0},
        ],
    })
    assert r.status_code == 200
    server_lauf_id = r.get_json()["server_lauf_id"]

    with app.app_context():
        lauf = db.session.get(NotfallLauf, server_lauf_id)
        assert lauf.bezeichnung == "Offline-Test"
        bahn = next(b for b in lauf.bahnen if b.bahn_nr == 1)
        assert bahn.team.name == "FF Rattenberg"
        assert bahn.zeit_laeufer1 == pytest.approx(10.123)
        assert bahn.gesamtzeit == pytest.approx(10.123 + 11.5 + 9.75 + 12.0)


def test_api_importieren_ist_idempotent_per_server_lauf_id(client, app):
    r1 = client.post("/notfall/api/importieren", headers={"X-API-Key": API_KEY}, json={
        "bezeichnung": "Wiederholt",
        "bahnen": [{"bahn_nr": 1, "team_nummer": 1, "zeit_laeufer1": 5.0}],
    })
    lauf_id = r1.get_json()["server_lauf_id"]

    r2 = client.post("/notfall/api/importieren", headers={"X-API-Key": API_KEY}, json={
        "server_lauf_id": lauf_id,
        "bahnen": [{"bahn_nr": 1, "team_nummer": 1, "zeit_laeufer2": 6.0}],
    })
    assert r2.get_json()["server_lauf_id"] == lauf_id

    with app.app_context():
        assert NotfallLauf.query.count() == 1
        bahn = NotfallBahn.query.filter_by(lauf_id=lauf_id, bahn_nr=1).one()
        assert bahn.zeit_laeufer1 == pytest.approx(5.0)
        assert bahn.zeit_laeufer2 == pytest.approx(6.0)


def test_api_importieren_unbekannte_startnummer_bleibt_ohne_team(client, app):
    r = client.post("/notfall/api/importieren", headers={"X-API-Key": API_KEY}, json={
        "bahnen": [{"bahn_nr": 1, "team_nummer": 999, "zeit_laeufer1": 1.0}],
    })
    lauf_id = r.get_json()["server_lauf_id"]
    with app.app_context():
        bahn = NotfallBahn.query.filter_by(lauf_id=lauf_id, bahn_nr=1).one()
        assert bahn.team_id is None


def test_api_importieren_ohne_bahnen_abgelehnt(client):
    r = client.post("/notfall/api/importieren", headers={"X-API-Key": API_KEY}, json={})
    assert r.status_code == 400
