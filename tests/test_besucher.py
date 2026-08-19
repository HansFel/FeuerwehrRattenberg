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


def test_besucheransicht_zeigt_rennzeit_strafen_und_gesamtzeit(client, app):
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

    r = client.get("/besucher/")
    text = r.data.decode("utf-8")
    assert "Rennzeit" in text
    assert "Strafsekunden" in text
    # Rennzeit 40s, Strafe 5s -> Gesamtzeit 45s = "45,00 s"
    assert "40,00 s" in text
    assert "45,00 s" in text


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
