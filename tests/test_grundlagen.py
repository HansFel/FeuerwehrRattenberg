"""Grundlegende Tests: App startet, Seiten laden, Wertung rechnet korrekt."""
import pytest

from app import create_app
from app.models import (db, Team, Mitglied, Disziplin, Ergebnis, WERTUNG_ZEIT,
                        Startplatz, Strafe)
from app.wertung import rangliste_disziplin, gesamtwertung


@pytest.fixture
def app():
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
    })
    with app.app_context():
        db.create_all()
        yield app


@pytest.fixture
def client(app):
    return app.test_client()


def test_startseite(client):
    antwort = client.get("/")
    assert antwort.status_code == 200
    assert "Übersicht".encode() in antwort.data


def test_seiten_laden(client):
    for pfad in ("/teams/", "/disziplinen/", "/wertung/", "/zeitplan/"):
        assert client.get(pfad).status_code == 200


def test_rechtliche_seiten_erreichbar(client):
    """Impressum/Datenschutz müssen ohne Login erreichbar sein (Zwei-Klick-Regel)."""
    for pfad, ueberschrift in (("/impressum", "Impressum"),
                               ("/datenschutz", "Datenschutzerklärung")):
        antwort = client.get(pfad)
        assert antwort.status_code == 200
        assert ueberschrift.encode() in antwort.data
    startseite = client.get("/").data
    assert b'href="/impressum"' in startseite
    assert b'href="/datenschutz"' in startseite


def test_build_kennung_im_footer(client):
    """Build-Nummer/-Zeit müssen sichtbar sein, um Deployments zu prüfen."""
    from app.version import BUILD_NUMMER, BUILD_ZEIT
    antwort = client.get("/")
    assert f"Build {BUILD_NUMMER}".encode() in antwort.data
    assert BUILD_ZEIT.encode() in antwort.data


def test_team_mit_vier_personen(client):
    client.post("/anmelden", data={"username": "admin", "passwort": "admin"})
    client.post("/teams/neu", data={
        "name": "FF Rattenberg 1",
        "person_1_vorname": "Anna", "person_1_nachname": "Huber",
        "person_1_spitzname": "Anni", "person_1_telefon": "0660 1",
        "person_1_alter": "22",
        "person_2_vorname": "Bernd", "person_2_nachname": "Maier",
        "person_3_vorname": "Clara", "person_3_nachname": "Gruber",
        "person_4_vorname": "Dieter", "person_4_nachname": "Bauer",
    })
    from app.models import Team
    team = Team.query.filter_by(name="FF Rattenberg 1").first()
    assert team is not None
    assert [m.voller_name() for m in team.mitglieder] == [
        "Anna Huber", "Bernd Maier", "Clara Gruber", "Dieter Bauer"]
    anna = team.mitglieder[0]
    assert anna.spitzname == "Anni" and anna.telefon == "0660 1" and anna.alter == 22

    # Bearbeiten: Person 2 leeren -> nur noch 3 Mitglieder
    client.post(f"/teams/{team.id}/bearbeiten", data={
        "name": "FF Rattenberg 1",
        "person_1_vorname": "Anna", "person_1_nachname": "Huber",
        "person_3_vorname": "Clara", "person_3_nachname": "Gruber",
        "person_4_vorname": "Dieter", "person_4_nachname": "Bauer",
    })
    assert [m.voller_name() for m in team.mitglieder] == [
        "Anna Huber", "Clara Gruber", "Dieter Bauer"]


def test_team_status_felder(client, app):
    client.post("/anmelden", data={"username": "admin", "passwort": "admin"})
    client.post("/teams/neu", data={
        "name": "Bierbrigade",
        "getraenk": "Bier", "bezahlt": "on", "haftungsausschluss": "on",
        "person_1_vorname": "Anna", "person_1_nachname": "Huber",
    })
    with app.app_context():
        team = Team.query.filter_by(name="Bierbrigade").first()
        assert team.getraenk == "Bier"
        assert team.bezahlt is True
        assert team.haftungsausschluss is True

    # Checkbox nicht mitgeschickt -> muss wieder False werden
    client.post(f"/teams/{team.id}/bearbeiten", data={
        "name": "Bierbrigade", "getraenk": "Bier",
        "person_1_vorname": "Anna", "person_1_nachname": "Huber",
    })
    with app.app_context():
        team = Team.query.filter_by(name="Bierbrigade").first()
        assert team.bezahlt is False
        assert team.haftungsausschluss is False


def test_mitglied_minderjaehrig_und_bearbeiten_erhaelt_haken(client, app):
    """Import setzt Haftungsausschluss/Ausweis/Einv.-Erklärung je Läufer -
    ein simples Speichern im Bearbeiten-Formular (das diese Felder nicht
    kennt) darf diese Haken nicht zurücksetzen."""
    with app.app_context():
        team = Team(name="U18 Team")
        team.mitglieder.append(Mitglied(
            vorname="Lena", nachname="Jung", alter=16, position=1,
            haftungsausschluss=True, ausweis_kontrolliert=True,
            einverstaendniserklaerung=True))
        db.session.add(team)
        db.session.commit()
        assert team.mitglieder[0].ist_minderjaehrig is True
        team_id = team.id

    client.post("/anmelden", data={"username": "admin", "passwort": "admin"})
    client.post(f"/teams/{team_id}/bearbeiten", data={
        "name": "U18 Team",
        "person_1_vorname": "Lena", "person_1_nachname": "Jung",
        "person_1_alter": "16",
    })
    with app.app_context():
        team = db.session.get(Team, team_id)
        lena = team.mitglieder[0]
        assert lena.haftungsausschluss is True
        assert lena.ausweis_kontrolliert is True
        assert lena.einverstaendniserklaerung is True


def test_zeitwertung_mit_strafsekunden(app):
    with app.app_context():
        d = Disziplin(name="Löschangriff", wertungsart=WERTUNG_ZEIT,
                      strafsekunden_pro_fehler=5.0)
        a = Team(name="A")
        b = Team(name="B")
        db.session.add_all([d, a, b])
        db.session.commit()

        # A: 80s + 2 Fehler*5 = 90s Netto ; B: 85s + 0 Fehler = 85s Netto
        db.session.add(Ergebnis(team_id=a.id, disziplin_id=d.id,
                                zeit_sekunden=80, fehlerpunkte=2))
        db.session.add(Ergebnis(team_id=b.id, disziplin_id=d.id,
                                zeit_sekunden=85, fehlerpunkte=0))
        db.session.commit()

        rl = rangliste_disziplin(d)
        assert rl[0].team.name == "B"   # 85s schlägt 90s netto
        assert rl[0].rang == 1
        assert rl[1].team.name == "A"


def test_gesamtwertung_summiert_rangpunkte(app):
    with app.app_context():
        d1 = Disziplin(name="D1", wertungsart=WERTUNG_ZEIT)
        d2 = Disziplin(name="D2", wertungsart=WERTUNG_ZEIT)
        a = Team(name="A")
        b = Team(name="B")
        db.session.add_all([d1, d2, a, b])
        db.session.commit()

        # A gewinnt D1, B gewinnt D2 -> beide 1+2 = 3 Rangpunkte -> Gleichstand
        db.session.add_all([
            Ergebnis(team_id=a.id, disziplin_id=d1.id, zeit_sekunden=10),
            Ergebnis(team_id=b.id, disziplin_id=d1.id, zeit_sekunden=20),
            Ergebnis(team_id=a.id, disziplin_id=d2.id, zeit_sekunden=30),
            Ergebnis(team_id=b.id, disziplin_id=d2.id, zeit_sekunden=15),
        ])
        db.session.commit()

        tabelle = gesamtwertung([a, b], [d1, d2])
        assert {z["punkte"] for z in tabelle} == {3}


def test_wertungsuebersicht_zeigt_gemessene_zeit_und_gesamtzeit(client, app):
    """Gesamtwertung soll die Summe der über die Zeitmessung gemessenen
    Laufzeiten (Startplatz.ergebnis_sekunden, z.B. beide Vorrunden-Läufe)
    plus Strafsekunden als Gesamtzeit ausweisen."""
    with app.app_context():
        d = Disziplin(name="Siloplanen-Race")
        team_a = Team(name="Team A")
        team_b = Team(name="Team B")   # ohne gemessene Zeit
        db.session.add_all([d, team_a, team_b])
        db.session.commit()

        # Team A: zwei Vorrunden-Läufe (30s + 25s = 55s gemessen)
        db.session.add_all([
            Startplatz(team_id=team_a.id, disziplin_id=d.id, startnummer=1,
                      heat="Vorrunde 1", ergebnis_sekunden=30.0),
            Startplatz(team_id=team_a.id, disziplin_id=d.id, startnummer=1,
                      heat="Vorrunde 2", ergebnis_sekunden=25.0),
        ])
        db.session.add(Strafe(team_id=team_a.id, regel_nr="4",
                              regel_text="Frühstart", sekunden=5.0))
        db.session.commit()

    r = client.get("/wertung/")
    assert r.status_code == 200
    # Team A: 55s gemessen + 5s Strafe = 60s = "1:00,00"
    assert "55,00 s".encode() in r.data
    assert "1:00,00".encode() in r.data


def test_gesamtwertung_gereiht_nach_gesamtzeit(app):
    """Rang in der Gesamtwertung muss nach Gesamtzeit (gemessene Zeit +
    Strafsekunden) gehen, nicht nach Rangpunkten - niedrigste Zeit zuerst,
    Teams ohne gemessene Zeit ans Ende."""
    with app.app_context():
        d = Disziplin(name="Siloplanen-Race")
        team_a = Team(name="Team A")   # 55s + 5s Strafe = 60s
        team_b = Team(name="Team B")   # 40s, keine Strafe -> schnellstes Team
        team_c = Team(name="Team C")   # noch keine gemessene Zeit
        db.session.add_all([d, team_a, team_b, team_c])
        db.session.commit()

        db.session.add_all([
            Startplatz(team_id=team_a.id, disziplin_id=d.id, startnummer=1,
                      heat="Vorrunde 1", ergebnis_sekunden=55.0),
            Startplatz(team_id=team_b.id, disziplin_id=d.id, startnummer=2,
                      heat="Vorrunde 1", ergebnis_sekunden=40.0),
        ])
        db.session.add(Strafe(team_id=team_a.id, regel_nr="4",
                              regel_text="Frühstart", sekunden=5.0))
        db.session.commit()

    client = app.test_client()
    r = client.get("/wertung/")
    text = r.data.decode("utf-8")
    # Team B (40s) muss vor Team A (60s) erscheinen, beide vor Team C (ohne Zeit)
    pos_b = text.index("Team B")
    pos_a = text.index("Team A")
    pos_c = text.index("Team C")
    assert pos_b < pos_a < pos_c
