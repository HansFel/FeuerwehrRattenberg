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


def test_teams_liste_zeigt_personen_nur_angemeldet(client, app):
    """Die Mannschaftsliste /teams/ ist auch ohne Login erreichbar (ueber den
    Nav-Link "Mannschaften" auch fuer Besucher). Namen der Teammitglieder
    sind personenbezogene Daten und duerfen dort nur angemeldetem Personal
    angezeigt werden, nicht anonymen Besuchern."""
    with app.app_context():
        team = Team(name="Sichtbares Team")
        team.mitglieder.append(Mitglied(vorname="Maximilian",
                                        nachname="Musterperson", position=1))
        db.session.add(team)
        db.session.commit()

    ohne_login = client.get("/teams/")
    assert ohne_login.status_code == 200
    assert "Sichtbares Team".encode() in ohne_login.data
    assert "Maximilian".encode() not in ohne_login.data
    assert "Musterperson".encode() not in ohne_login.data
    assert "Personen".encode() not in ohne_login.data

    client.post("/anmelden", data={"username": "admin", "passwort": "admin"})
    mit_login = client.get("/teams/")
    assert "Maximilian Musterperson".encode() in mit_login.data


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


def test_team_motto_und_lieblingslied_anlegen_und_bearbeiten(client, app):
    client.post("/anmelden", data={"username": "admin", "passwort": "admin"})
    client.post("/teams/neu", data={
        "name": "Discofeger",
        "motto": "Wir loeschen jedes Feuer",
        "lieblingslied": "Highway to Hell",
        "person_1_vorname": "Anna", "person_1_nachname": "Huber",
    })
    with app.app_context():
        team = Team.query.filter_by(name="Discofeger").first()
        assert team.motto == "Wir loeschen jedes Feuer"
        assert team.lieblingslied == "Highway to Hell"
        team_id = team.id

    client.post(f"/teams/{team_id}/bearbeiten", data={
        "name": "Discofeger",
        "motto": "Neues Motto",
        "lieblingslied": "Neues Lied",
        "person_1_vorname": "Anna", "person_1_nachname": "Huber",
    })
    with app.app_context():
        team = db.session.get(Team, team_id)
        assert team.motto == "Neues Motto"
        assert team.lieblingslied == "Neues Lied"


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


def test_gesamtwertung_definitive_platzierung_aus_platzierungslauf(app):
    """Sobald ein Team einen Ziellauf (Heat mit "Platz von-bis") absolviert
    hat, ist das die endgueltige Platzierung - inkl. Strafsekunden als
    Sortierkriterium INNERHALB dieses einen Laufs."""
    with app.app_context():
        d = Disziplin(name="Siloplanen-Race")
        team_e = Team(name="Team E")   # 20s, kein Strafe -> Platz 9
        team_f = Team(name="Team F")   # 21s + 5s Strafe = 26s -> schlechtester -> Platz 12
        team_g = Team(name="Team G")   # 22s -> Platz 10
        team_h = Team(name="Team H")   # 23s -> Platz 11
        db.session.add_all([d, team_e, team_f, team_g, team_h])
        db.session.commit()

        heat = "12 Platzierungslauf Platz 9-12"
        db.session.add_all([
            Startplatz(team_id=team_e.id, disziplin_id=d.id, startnummer=1,
                      heat=heat, ergebnis_sekunden=20.0),
            Startplatz(team_id=team_f.id, disziplin_id=d.id, startnummer=2,
                      heat=heat, ergebnis_sekunden=21.0),
            Startplatz(team_id=team_g.id, disziplin_id=d.id, startnummer=3,
                      heat=heat, ergebnis_sekunden=22.0),
            Startplatz(team_id=team_h.id, disziplin_id=d.id, startnummer=4,
                      heat=heat, ergebnis_sekunden=23.0),
        ])
        db.session.add(Strafe(team_id=team_f.id, regel_nr="4",
                              regel_text="Frühstart", sekunden=5.0))
        db.session.commit()

    client = app.test_client()
    r = client.get("/wertung/")
    assert r.status_code == 200

    from app.wertung import finale_platzierung
    with app.app_context():
        team_e = Team.query.filter_by(name="Team E").first()
        team_f = Team.query.filter_by(name="Team F").first()
        team_g = Team.query.filter_by(name="Team G").first()
        team_h = Team.query.filter_by(name="Team H").first()
        strafsekunden = {team_f.id: 5.0}
        assert finale_platzierung(team_e, strafsekunden) == 9
        assert finale_platzierung(team_g, strafsekunden) == 10
        assert finale_platzierung(team_h, strafsekunden) == 11
        assert finale_platzierung(team_f, strafsekunden) == 12   # Strafe wirft es ans Ende

        # Eine ausdrückliche Korrektur ändert nur den offiziellen Platz;
        # Laufzuordnung, Messzeit und Strafen bleiben unverändert erhalten.
        sp_g = Startplatz.query.filter_by(team_id=team_g.id, heat=heat).one()
        alte_zeit = sp_g.ergebnis_sekunden
        sp_g.platz_override = 15
        db.session.commit()
        assert finale_platzierung(team_g, strafsekunden) == 15
        assert sp_g.heat == heat
        assert sp_g.ergebnis_sekunden == alte_zeit


def test_gesamtwertung_ohne_ziellauf_bleibt_vorlaeufig(app):
    with app.app_context():
        d = Disziplin(name="Siloplanen-Race")
        team = Team(name="Team Nurvorrunde")
        db.session.add_all([d, team])
        db.session.commit()
        db.session.add(Startplatz(team_id=team.id, disziplin_id=d.id,
                                  startnummer=1, heat="Vorrunde 1",
                                  ergebnis_sekunden=30.0))
        db.session.commit()

    client = app.test_client()
    r = client.get("/wertung/")
    text = r.data.decode("utf-8")
    assert "Team Nurvorrunde" in text
    assert "(vorläufig)" in text
