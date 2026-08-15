"""Tests für die Startlisten-Auslosung (Vorrunde) und manuelle Pflege."""
import pytest

from app import create_app
from app.models import (db, Team, Disziplin, Startplatz, Benutzer,
                        BenutzerRolle, WERTUNG_ZEIT)


@pytest.fixture
def app():
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "ADMIN_STARTPASSWORT": "admin",
    })
    with app.app_context():
        db.create_all()
        d = Disziplin(name="Siloplanen-Race", wertungsart=WERTUNG_ZEIT)
        db.session.add(d)
        for i in range(1, 9):   # 8 Teams -> 2 Runden à 2 Läufen bei 4 Bahnen
            db.session.add(Team(name=f"Team {i}", startnummer=i))

        orga = Benutzer(username="orga", aktiv=True)
        orga.set_password("pw")
        orga.rollen.append(BenutzerRolle(rolle="organisator"))
        db.session.add(orga)

        richter = Benutzer(username="richter", aktiv=True)
        richter.set_password("pw")
        richter.rollen.append(BenutzerRolle(rolle="startrichter"))
        db.session.add(richter)

        punkt = Benutzer(username="punkt", aktiv=True)
        punkt.set_password("pw")
        punkt.rollen.append(BenutzerRolle(rolle="punkterichter"))
        db.session.add(punkt)
        db.session.commit()
        yield app


@pytest.fixture
def client(app):
    return app.test_client()


def _login(client, username, pw):
    return client.post("/anmelden", data={"username": username, "passwort": pw})


def test_auslosen_erfordert_rolle(client, app):
    with app.app_context():
        d = Disziplin.query.first()
        d_id = d.id
    _login(client, "punkt", "pw")
    r = client.post(f"/zeitplan/disziplin/{d_id}", data={"aktion": "auslosen"},
                    follow_redirects=True)
    assert "rolle".encode() in r.data.lower()
    with app.app_context():
        assert Startplatz.query.count() == 0


def test_auslosen_erzeugt_zwei_laeufe_je_team(client, app):
    with app.app_context():
        d = Disziplin.query.first()
        d_id = d.id
        anzahl_teams = Team.query.count()

    _login(client, "richter", "pw")
    r = client.post(f"/zeitplan/disziplin/{d_id}", data={"aktion": "auslosen"},
                    follow_redirects=True)
    assert r.status_code == 200
    assert "neu ausgelost".encode() in r.data

    with app.app_context():
        alle = Startplatz.query.filter_by(disziplin_id=d_id).all()
        # 8 Teams, 4 Bahnen, 2 Runden -> 2 Läufe, je 4 Startplätze = 8 gesamt
        assert len(alle) == anzahl_teams * 2

        # Jedes Team kommt genau 2x vor
        from collections import Counter
        zaehler = Counter(sp.team_id for sp in alle)
        assert all(anzahl == 2 for anzahl in zaehler.values())

        # Jeder Lauf (heat) hat maximal 4 Bahnen und eindeutige Startnummern
        heats = {}
        for sp in alle:
            heats.setdefault(sp.heat, []).append(sp)
        for heat_name, eintraege in heats.items():
            assert len(eintraege) <= 4
            bahnen = [e.startnummer for e in eintraege]
            assert len(bahnen) == len(set(bahnen))


def test_auslosen_ersetzt_vorhandene_startliste(client, app):
    with app.app_context():
        d = Disziplin.query.first()
        d_id = d.id
        team = Team.query.first()
        db.session.add(Startplatz(team_id=team.id, disziplin_id=d_id,
                                  startnummer=99, heat="Alter Eintrag"))
        db.session.commit()

    _login(client, "richter", "pw")
    client.post(f"/zeitplan/disziplin/{d_id}", data={"aktion": "auslosen"})

    with app.app_context():
        alte = Startplatz.query.filter_by(heat="Alter Eintrag").count()
        assert alte == 0


def test_manuell_hinzufuegen_und_loeschen(client, app):
    with app.app_context():
        d = Disziplin.query.first()
        d_id = d.id
        team = Team.query.first()
        team_id = team.id

    _login(client, "orga", "pw")
    r = client.post(f"/zeitplan/disziplin/{d_id}", data={
        "aktion": "hinzufuegen", "team_id": str(team_id),
        "neu_heat": "Kleines Finale", "neu_nr": "2", "neu_zeit": "15:00",
    }, follow_redirects=True)
    assert r.status_code == 200
    assert "hinzugefügt".encode() in r.data

    with app.app_context():
        sp = Startplatz.query.filter_by(heat="Kleines Finale").first()
        assert sp is not None
        assert sp.team_id == team_id
        assert sp.startnummer == 2
        assert sp.startzeit == "15:00"
        sp_id = sp.id

    r = client.post(f"/zeitplan/startplatz/{sp_id}/loeschen", follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        assert db.session.get(Startplatz, sp_id) is None


def test_loeschen_erfordert_rolle(client, app):
    with app.app_context():
        d = Disziplin.query.first()
        team = Team.query.first()
        sp = Startplatz(team_id=team.id, disziplin_id=d.id, startnummer=1)
        db.session.add(sp)
        db.session.commit()
        sp_id = sp.id

    _login(client, "punkt", "pw")
    r = client.post(f"/zeitplan/startplatz/{sp_id}/loeschen", follow_redirects=True)
    assert "rolle".encode() in r.data.lower()
    with app.app_context():
        assert db.session.get(Startplatz, sp_id) is not None


def test_ergebnis_speichern(client, app):
    with app.app_context():
        d = Disziplin.query.first()
        d_id = d.id
        team = Team.query.first()
        sp = Startplatz(team_id=team.id, disziplin_id=d_id, startnummer=1,
                        heat="Vorrunde 1")
        db.session.add(sp)
        db.session.commit()
        sp_id = sp.id

    _login(client, "richter", "pw")
    client.post(f"/zeitplan/disziplin/{d_id}", data={
        "aktion": "speichern",
        f"nr_{sp_id}": "1", f"zeit_{sp_id}": "10:00",
        f"heat_{sp_id}": "Vorrunde 1", f"erg_{sp_id}": "42,50",
    })
    with app.app_context():
        sp = db.session.get(Startplatz, sp_id)
        assert sp.ergebnis_sekunden == pytest.approx(42.5)


def test_rangliste_summiert_zwei_laeufe_und_markiert_unvollstaendig(client, app):
    with app.app_context():
        d = Disziplin.query.first()
        d_id = d.id
        t1, t2 = Team.query.order_by(Team.startnummer).limit(2).all()
        # Team 1: beide Vorrunden-Läufe erfasst -> vollständig, Gesamtzeit 90
        db.session.add(Startplatz(team_id=t1.id, disziplin_id=d_id,
                                  heat="Vorrunde 1", ergebnis_sekunden=40.0))
        db.session.add(Startplatz(team_id=t1.id, disziplin_id=d_id,
                                  heat="Vorrunde 2", ergebnis_sekunden=50.0))
        # Team 2: nur 1 von 2 Läufen erfasst -> unvollständig
        db.session.add(Startplatz(team_id=t2.id, disziplin_id=d_id,
                                  heat="Vorrunde 1", ergebnis_sekunden=30.0))
        db.session.add(Startplatz(team_id=t2.id, disziplin_id=d_id,
                                  heat="Vorrunde 2", ergebnis_sekunden=None))
        db.session.commit()

    _login(client, "orga", "pw")
    r = client.get(f"/zeitplan/disziplin/{d_id}/rangliste?quelle=Vorrunde")
    assert r.status_code == 200
    assert "90.00".encode() in r.data
    assert "unvollständig".encode() in r.data


def test_naechste_runde_aus_rangliste_anlegen(client, app):
    with app.app_context():
        d = Disziplin.query.first()
        d_id = d.id
        teams = Team.query.order_by(Team.startnummer).limit(4).all()
        team_ids = [t.id for t in teams]
        for t in teams:
            db.session.add(Startplatz(team_id=t.id, disziplin_id=d_id,
                                      heat="Vorrunde 1", ergebnis_sekunden=float(t.id)))
        db.session.commit()

    _login(client, "orga", "pw")
    r = client.post(f"/zeitplan/disziplin/{d_id}/rangliste", data={
        "team_id": [str(i) for i in team_ids],
        "neuer_heat": "Halbfinale 1",
    }, follow_redirects=True)
    assert r.status_code == 200
    assert "angelegt".encode() in r.data

    with app.app_context():
        neue = Startplatz.query.filter_by(disziplin_id=d_id, heat="Halbfinale 1").all()
        assert len(neue) == 4
        assert {sp.team_id for sp in neue} == set(team_ids)
        bahnen = [sp.startnummer for sp in neue]
        assert sorted(bahnen) == [1, 2, 3, 4]


def test_naechste_runde_lehnt_zu_viele_teams_ab(client, app):
    with app.app_context():
        d = Disziplin.query.first()
        d_id = d.id
        teams = Team.query.all()
        team_ids = [t.id for t in teams]   # 8 Teams, mehr als 4 Bahnen

    _login(client, "orga", "pw")
    r = client.post(f"/zeitplan/disziplin/{d_id}/rangliste", data={
        "team_id": [str(i) for i in team_ids],
        "neuer_heat": "Zu viele",
    }, follow_redirects=True)
    assert "maximal".encode() in r.data
    with app.app_context():
        assert Startplatz.query.filter_by(heat="Zu viele").count() == 0
