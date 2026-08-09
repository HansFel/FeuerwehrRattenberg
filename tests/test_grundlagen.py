"""Grundlegende Tests: App startet, Seiten laden, Wertung rechnet korrekt."""
import pytest

from app import create_app
from app.models import db, Team, Disziplin, Ergebnis, WERTUNG_ZEIT
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
