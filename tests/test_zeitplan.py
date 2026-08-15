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
