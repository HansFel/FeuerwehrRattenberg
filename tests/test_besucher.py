"""Tests fuer die oeffentliche Besucheransicht (kein Login noetig)."""
import pytest

from app import create_app
from app.models import db, Team, Disziplin, Startplatz, Strafe, Mitglied


@pytest.fixture
def app():
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "ADMIN_STARTPASSWORT": "admin",
    })
    with app.app_context():
        db.create_all()
        yield app


@pytest.fixture
def client(app):
    return app.test_client()


def test_besucheransicht_ohne_login_erreichbar(client):
    r = client.get("/besucher/")
    assert r.status_code == 200
    assert "anmelden".encode() not in r.data.lower() or "🔒".encode() in r.data


def test_besucheransicht_zeigt_gesamtwertung_und_zeitplan(client, app):
    with app.app_context():
        d = Disziplin(name="Siloplanen-Race")
        team = Team(name="Sichtbares Team")
        db.session.add_all([d, team])
        db.session.commit()
        db.session.add(Startplatz(team_id=team.id, disziplin_id=d.id,
                                  startnummer=1, heat="Vorrunde 1",
                                  ergebnis_sekunden=42.0, startzeit="10:00"))
        db.session.commit()

    r = client.get("/besucher/")
    assert r.status_code == 200
    text = r.data.decode("utf-8")
    assert "Sichtbares Team" in text
    assert "Vorrunde 1" in text
    assert "10:00" in text


def test_besucherwertung_zeigt_nur_platz_und_mannschaft(client, app):
    with app.app_context():
        d = Disziplin(name="Siloplanen-Race")
        team = Team(name="Strafteam")
        db.session.add_all([d, team])
        db.session.commit()
        db.session.add(Startplatz(team_id=team.id, disziplin_id=d.id,
                                  startnummer=1, heat="Vorrunde 1",
                                  ergebnis_sekunden=40.0))
        db.session.add(Strafe(team_id=team.id, regel_nr="4",
                              regel_text="Frühstart", sekunden=5.0))
        db.session.commit()

    r = client.get("/besucher/live-fragment")
    text = r.get_json()["wertung_html"]
    assert "Strafteam" in text
    assert "Rennzeit" not in text
    assert "Strafsekunden" not in text
    assert "Gesamtzeit" not in text
    assert "40,00 s" not in text
    assert "45,00 s" not in text


def test_besucheransicht_ohne_daten_zeigt_leer_meldung(client):
    r = client.get("/besucher/")
    assert r.status_code == 200
    assert "leer".encode() in r.data.lower() or "noch keine".encode() in r.data.lower()


def test_besucheransicht_zeigt_keine_admin_aktionen(client, app):
    """Reine Anzeige - keine Formulare/Buttons zum Bearbeiten."""
    with app.app_context():
        d = Disziplin(name="Siloplanen-Race")
        team = Team(name="Team")
        db.session.add_all([d, team])
        db.session.commit()
        db.session.add(Startplatz(team_id=team.id, disziplin_id=d.id,
                                  startnummer=1, heat="Vorrunde 1"))
        db.session.commit()

    r = client.get("/besucher/")
    assert b'method="post"' not in r.data


def test_besucheransicht_zeigt_keine_wehr_und_keine_personennamen(client, app):
    """Datenschutz: in der oeffentlichen Besucheransicht duerfen weder die
    Wehr/Ort-Angabe des Teams noch Namen einzelner Teammitglieder
    erscheinen - nur der Teamname (und die Startnummer/Bahn)."""
    with app.app_context():
        d = Disziplin(name="Siloplanen-Race")
        team = Team(name="Datenschutz-Team", wehr="Geheimort")
        team.mitglieder.append(Mitglied(vorname="Maximilian",
                                        nachname="Musterperson", position=1))
        db.session.add_all([d, team])
        db.session.commit()
        db.session.add(Startplatz(team_id=team.id, disziplin_id=d.id,
                                  startnummer=3, heat="Vorrunde 1",
                                  ergebnis_sekunden=30.0))
        db.session.commit()

    r = client.get("/besucher/")
    text = r.data.decode("utf-8")
    assert "Datenschutz-Team" in text
    assert "Geheimort" not in text
    assert "Maximilian" not in text
    assert "Musterperson" not in text


def test_besucheransicht_zeigt_team_challenge(client, app):
    """Getraenkepunkte + Fanpunkte sollen auch in der oeffentlichen
    Besucheransicht als eigene Wertung neben der Siloplanen-Race-
    Gesamtwertung erscheinen, fuer den Dauerbetrieb auf Anzeige-Screens."""
    with app.app_context():
        team = Team(name="Challenge-Team", fanpunkte=7)
        db.session.add(team)
        db.session.commit()

    r = client.get("/besucher/")
    text = r.data.decode("utf-8")
    assert "Team Challenge" in text
    assert "Challenge-Team" in text
    assert "Fanpunkte" in text


def test_besucher_live_fragment_ohne_login_und_ohne_personendaten(client, app):
    """Der /besucher/live-fragment-Endpoint (per JS-Polling auf Anzeige-
    Screens eingebettet) funktioniert ohne Login und liefert frische Zeiten
    ohne Seiten-Reload - unter denselben Datenschutz-Regeln wie die
    Hauptseite (keine Wehr/Personennamen)."""
    with app.app_context():
        d = Disziplin(name="Siloplanen-Race")
        team = Team(name="Screen-Team", wehr="Geheimort", fanpunkte=3)
        team.mitglieder.append(Mitglied(vorname="Maximilian",
                                        nachname="Musterperson", position=1))
        db.session.add_all([d, team])
        db.session.commit()
        db.session.add(Startplatz(team_id=team.id, disziplin_id=d.id,
                                  startnummer=1, heat="Vorrunde 1"))
        db.session.commit()
        team_id = team.id

    r = client.get("/besucher/live-fragment")
    assert r.status_code == 200
    daten = r.get_json()
    assert "Screen-Team" in daten["wertung_html"]
    assert "Geheimort" not in daten["wertung_html"]
    assert "Maximilian" not in daten["wertung_html"]
    assert "Screen-Team" in daten["zeitplan_html"]
    assert "Geheimort" not in daten["zeitplan_html"]

    # Zeit wird erfasst - ohne dass die Hauptseite neu geladen werden muss
    with app.app_context():
        Startplatz.query.filter_by(team_id=team_id).update({"ergebnis_sekunden": 33.5})
        db.session.commit()

    r = client.get("/besucher/live-fragment")
    daten = r.get_json()
    assert "33,50 s" not in daten["wertung_html"]
    assert "33,50 s" in daten["zeitplan_html"]

    hauptseite = client.get("/besucher/")
    assert "/besucher/live-fragment".encode() in hauptseite.data


def test_zeitplan_zeigt_strafsekunden_und_gesamtzeit_pro_lauf(client, app):
    """Strafsekunden/Gesamtzeit sollen auch in der Zeitplan-Tabelle je Lauf
    stehen (gilt fuer alle Laufarten: Vorrunde, Platzierungslauf,
    Halbfinale, Finale - technisch dieselbe Tabelle/Spalte)."""
    with app.app_context():
        d = Disziplin(name="Siloplanen-Race")
        team_a = Team(name="Team A")   # 30s, keine Strafe
        team_b = Team(name="Team B")   # 20s + 8s Strafe = 28s
        db.session.add_all([d, team_a, team_b])
        db.session.commit()
        db.session.add(Startplatz(team_id=team_a.id, disziplin_id=d.id,
                                  startnummer=1,
                                  heat="21 Platzierungslauf Platz 9-10",
                                  ergebnis_sekunden=30.0))
        db.session.add(Startplatz(team_id=team_b.id, disziplin_id=d.id,
                                  startnummer=2,
                                  heat="21 Platzierungslauf Platz 9-10",
                                  ergebnis_sekunden=20.0))
        db.session.add(Strafe(team_id=team_b.id, regel_nr="1",
                              regel_text="Getränk weggeschüttet", sekunden=8.0))
        db.session.commit()

    r = client.get("/besucher/")
    text = r.data.decode("utf-8")
    assert "Platzierungslauf" in text
    assert "20,00 s" in text    # Rennzeit Team B
    assert "28,00 s" in text    # Gesamtzeit Team B (20+8)
    assert "30,00 s" in text    # Rennzeit/Gesamtzeit Team A (keine Strafe)
