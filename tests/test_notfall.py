"""Tests für die manuelle Notfall-Zeiterfassung (Fallback, falls die
automatische ESP32-zu-Lauf-Zuordnung ausfällt)."""
import pytest

from app import create_app
from app.models import (db, Team, Mitglied, Benutzer, BenutzerRolle,
                        NotfallLauf, NotfallBahn, Disziplin, Startplatz,
                        ModeratorStatus)


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

        organisator = Benutzer(username="orga", name="Olga", aktiv=True)
        organisator.set_password("pw")
        organisator.rollen.append(BenutzerRolle(rolle="organisator"))
        db.session.add(organisator)

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


def test_api_aktiv_vollstaendig_false_wenn_team_bahn_offen(client, app):
    """Eine Team-Bahn ohne alle 4 Zeiten -> nicht vollstaendig (Licht bleibt
    grün/start), Bahn ohne Team wird ignoriert."""
    with app.app_context():
        t1 = Team.query.filter_by(name="FF Rattenberg").first()
        lauf = NotfallLauf(bezeichnung="V", aktiv=True)
        lauf.bahnen.append(NotfallBahn(bahn_nr=1, team_id=t1.id,
                                       zeit_laeufer1=1.0, zeit_laeufer2=2.0))
        lauf.bahnen.append(NotfallBahn(bahn_nr=2))   # ohne Team - ignoriert
        db.session.add(lauf)
        db.session.commit()

    r = client.get("/notfall/api/aktiv", headers={"X-API-Key": API_KEY})
    assert r.get_json()["vollstaendig"] is False


def test_api_aktiv_vollstaendig_true_wenn_alle_team_bahnen_fertig(client, app):
    """Alle Team-Bahnen haben alle 4 Zeiten -> vollstaendig (Licht -> ROT)."""
    with app.app_context():
        t1 = Team.query.filter_by(name="FF Rattenberg").first()
        t2 = Team.query.filter_by(name="FF Kobenz").first()
        lauf = NotfallLauf(bezeichnung="F", aktiv=True)
        lauf.bahnen.append(NotfallBahn(bahn_nr=1, team_id=t1.id,
                                       zeit_laeufer1=1, zeit_laeufer2=2,
                                       zeit_laeufer3=3, zeit_laeufer4=4))
        lauf.bahnen.append(NotfallBahn(bahn_nr=2, team_id=t2.id,
                                       zeit_laeufer1=5, zeit_laeufer2=6,
                                       zeit_laeufer3=7, zeit_laeufer4=8))
        db.session.add(lauf)
        db.session.commit()

    r = client.get("/notfall/api/aktiv", headers={"X-API-Key": API_KEY})
    assert r.get_json()["vollstaendig"] is True


def test_api_aktiv_ohne_aktiven_lauf_liefert_nur_aktiv_false(client):
    """Der nicht-aktive Fall darf KEIN vollstaendig-Feld enthalten, sonst
    bricht die strenge Gleichheitspruefung der Desktop-App/Tests."""
    r = client.get("/notfall/api/aktiv", headers={"X-API-Key": API_KEY})
    assert r.get_json() == {"aktiv": False}


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


def _moderator_status_setzen(app, disziplin_name="Siloplanen-Race", heat="Vorrunde 1"):
    with app.app_context():
        disziplin = Disziplin(name=disziplin_name)
        db.session.add(disziplin)
        db.session.flush()
        t1 = Team.query.filter_by(name="FF Rattenberg").first()
        t2 = Team.query.filter_by(name="FF Kobenz").first()
        sp1 = Startplatz(team_id=t1.id, disziplin_id=disziplin.id, startnummer=1, heat=heat)
        sp2 = Startplatz(team_id=t2.id, disziplin_id=disziplin.id, startnummer=2, heat=heat)
        db.session.add_all([sp1, sp2])
        db.session.add(ModeratorStatus(id=1, disziplin_id=disziplin.id, heat=heat))
        db.session.commit()
        return sp1.id, sp2.id


def test_aus_startliste_freigeben_erfordert_rolle(client, app):
    _moderator_status_setzen(app)
    r = client.post("/notfall/aus-startliste-freigeben", follow_redirects=True)
    assert "anmelden".encode() in r.data.lower() or "rolle".encode() in r.data.lower()


def test_aus_startliste_freigeben_startrichter_abgewiesen(client, app):
    """Die Lauffreigabe aus der Startliste darf NUR dem Organisator
    zustaehen - der Startrichter wird bewusst abgewiesen (seine manuelle
    Notfall-Erfassung unter /notfall/neu bleibt davon unberuehrt)."""
    _moderator_status_setzen(app)
    _login(client, "richter", "pw")
    r = client.post("/notfall/aus-startliste-freigeben", follow_redirects=True)
    assert "rolle".encode() in r.data.lower()
    with app.app_context():
        assert NotfallLauf.query.count() == 0


def test_aus_startliste_freigeben_ohne_aktuellen_heat(client, app):
    _login(client, "orga", "pw")
    r = client.post("/notfall/aus-startliste-freigeben", follow_redirects=True)
    assert "kein aktueller lauf".encode() in r.data.lower()
    with app.app_context():
        assert NotfallLauf.query.count() == 0


def test_aus_startliste_freigeben_erzeugt_und_aktiviert_lauf(client, app):
    sp1_id, sp2_id = _moderator_status_setzen(app)
    _login(client, "orga", "pw")

    r = client.post("/notfall/aus-startliste-freigeben", follow_redirects=True)
    assert r.status_code == 200
    assert "freigegeben".encode() in r.data.lower()

    with app.app_context():
        lauf = NotfallLauf.query.filter_by(aktiv=True).one()
        assert "Vorrunde 1" in lauf.bezeichnung
        bahn1 = next(b for b in lauf.bahnen if b.bahn_nr == 1)
        assert bahn1.team.name == "FF Rattenberg"
        assert bahn1.startplatz_id == sp1_id
        bahn2 = next(b for b in lauf.bahnen if b.bahn_nr == 2)
        assert bahn2.startplatz_id == sp2_id


def test_aus_startliste_freigeben_deaktiviert_vorherigen_lauf(client, app):
    _moderator_status_setzen(app)
    _login(client, "orga", "pw")
    with app.app_context():
        alter_lauf = NotfallLauf(bezeichnung="Alt", aktiv=True)
        db.session.add(alter_lauf)
        db.session.commit()
        alter_lauf_id = alter_lauf.id

    client.post("/notfall/aus-startliste-freigeben")

    with app.app_context():
        assert db.session.get(NotfallLauf, alter_lauf_id).aktiv is False
        assert NotfallLauf.query.filter_by(aktiv=True).count() == 1


def test_automatische_zuordnung_schreibt_ergebnis_in_startplatz_zurueck(client, app):
    sp1_id, _ = _moderator_status_setzen(app)
    _login(client, "orga", "pw")
    client.post("/notfall/aus-startliste-freigeben")

    for _ in range(5):
        r = client.post("/api/zeitmessung/event",
                        json={"geraet_id": "test", "bahn": 1, "kontakt": "kontakt"},
                        headers={"X-API-Key": "dev-nur-lokal-zeitmessung"})
        assert r.status_code == 201

    with app.app_context():
        sp1 = db.session.get(Startplatz, sp1_id)
        assert sp1.ergebnis_sekunden is not None
        assert sp1.ergebnis_sekunden >= 0


def _vier_bahnen_heat(app, disziplin_id, heat):
    """4 Startplätze (Bahn 1-4) mit je einem Team für einen Heat."""
    from datetime import datetime
    sp_ids = []
    with app.app_context():
        for bahn in range(1, 5):
            team = Team(name=f"Team {heat}/{bahn}", startnummer=bahn)
            db.session.add(team)
            db.session.flush()
            sp = Startplatz(team_id=team.id, disziplin_id=disziplin_id,
                            startnummer=bahn, heat=heat)
            db.session.add(sp)
            db.session.flush()
            sp_ids.append(sp.id)
        db.session.commit()
    return sp_ids


def test_laufabschluss_rueckt_gerade_im_bewerb_auf_naechsten_heat(client, app):
    """Sobald alle 4 Bahnen des aktuellen Heats zu Ende gemessen sind,
    rückt 'Gerade im Bewerb' serverseitig sofort auf den nächsten Heat -
    ohne auf das Dashboard-Polling zu warten (siehe zeitmessung.py:
    _automatische_zuordnung_pruefen -> moderator._lauf_automatisch_
    weiterruecken). Der fertige Lauf bleibt aktiviert (Licht bleibt ROT),
    bis der nächste freigegeben wird."""
    from datetime import datetime
    with app.app_context():
        d = Disziplin(name="Siloplanen-Race", reihenfolge=1)
        db.session.add(d)
        db.session.flush()
        disziplin_id = d.id
        sp_heat1 = _vier_bahnen_heat(app, disziplin_id, "1")
        _vier_bahnen_heat(app, disziplin_id, "2")           # der nächste Heat

        db.session.add(ModeratorStatus(id=1, disziplin_id=disziplin_id, heat="1"))
        db.session.commit()

        lauf = NotfallLauf(bezeichnung="Heat 1", aktiv=True,
                           aktiviert_um=datetime.utcnow())
        for bahn_nr, sp_id in enumerate(sp_heat1, start=1):
            sp = db.session.get(Startplatz, sp_id)
            lauf.bahnen.append(NotfallBahn(bahn_nr=bahn_nr, team_id=sp.team_id,
                                           startplatz_id=sp_id))
        db.session.add(lauf)
        db.session.commit()
        lauf_id = lauf.id

    for bahn in range(1, 5):
        for _ in range(5):
            r = client.post("/api/zeitmessung/event",
                            json={"geraet_id": "mega", "bahn": bahn,
                                  "kontakt": "kontakt"},
                            headers={"X-API-Key": API_KEY})
            assert r.status_code == 201

    with app.app_context():
        assert all(sp.ergebnis_sekunden is not None
                   for sp in Startplatz.query
                   .filter_by(disziplin_id=disziplin_id, heat="1").all())
        assert db.session.get(ModeratorStatus, 1).heat == "2"
        assert db.session.get(NotfallLauf, lauf_id).aktiv is True
