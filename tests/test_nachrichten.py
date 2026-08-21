"""Tests für Nachrichten von Administratoren an andere Personen."""
import pytest

from app import create_app
from app.models import db, Benutzer, BenutzerRolle, Nachricht


@pytest.fixture
def app():
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "ADMIN_STARTPASSWORT": "admin",
    })
    with app.app_context():
        db.create_all()
        pr = Benutzer(username="punkt", name="Peter", aktiv=True)
        pr.set_password("pw")
        pr.rollen.append(BenutzerRolle(rolle="punkterichter"))
        db.session.add(pr)

        org = Benutzer(username="orga", name="Olga", aktiv=True)
        org.set_password("pw")
        org.rollen.append(BenutzerRolle(rolle="organisator"))
        db.session.add(org)
        db.session.commit()
        yield app


@pytest.fixture
def client(app):
    return app.test_client()


def _login(client, user, pw):
    return client.post("/anmelden", data={"username": user, "passwort": pw})


def test_nur_admin_darf_senden(client):
    _login(client, "punkt", "pw")
    r = client.post("/nachrichten/senden",
                    data={"text": "geheim", "ziel": "alle"},
                    follow_redirects=True)
    assert Nachricht.query.count() == 0


def test_nachricht_an_alle(client, app):
    _login(client, "admin", "admin")
    client.post("/nachrichten/senden",
                data={"text": "Denkt über die Getränkewertung nach.",
                     "ziel": "alle"})
    with app.app_context():
        n = Nachricht.query.first()
        peter = Benutzer.query.filter_by(username="punkt").first()
        olga = Benutzer.query.filter_by(username="orga").first()
        assert n.richtet_sich_an(peter)
        assert n.richtet_sich_an(olga)


def test_nachricht_an_rolle(client, app):
    _login(client, "admin", "admin")
    client.post("/nachrichten/senden",
                data={"text": "Nur für Punkterichter.",
                     "ziel": "rolle:punkterichter"})
    with app.app_context():
        n = Nachricht.query.first()
        peter = Benutzer.query.filter_by(username="punkt").first()
        olga = Benutzer.query.filter_by(username="orga").first()
        assert n.richtet_sich_an(peter)
        assert not n.richtet_sich_an(olga)


def test_nachricht_an_person(client, app):
    with app.app_context():
        olga_id = Benutzer.query.filter_by(username="orga").first().id
    _login(client, "admin", "admin")
    client.post("/nachrichten/senden",
                data={"text": "Nur für Olga.", "ziel": f"person:{olga_id}"})
    with app.app_context():
        n = Nachricht.query.first()
        peter = Benutzer.query.filter_by(username="punkt").first()
        olga = Benutzer.query.filter_by(username="orga").first()
        assert n.richtet_sich_an(olga)
        assert not n.richtet_sich_an(peter)


def test_gelesen_markieren(client, app):
    _login(client, "admin", "admin")
    client.post("/nachrichten/senden", data={"text": "Test", "ziel": "alle"})
    with app.app_context():
        n = Nachricht.query.first()
        nid = n.id
    client.post("/abmelden")

    _login(client, "punkt", "pw")
    r = client.get("/")
    assert "Neue Nachrichten".encode() in r.data
    assert "Test".encode() in r.data

    client.post(f"/nachrichten/{nid}/gelesen")
    r2 = client.get("/")
    assert "Neue Nachrichten".encode() not in r2.data

    with app.app_context():
        n = db.session.get(Nachricht, nid)
        peter = Benutzer.query.filter_by(username="punkt").first()
        assert n.ist_gelesen_von(peter.id)


def test_nachricht_loeschen(client, app):
    _login(client, "admin", "admin")
    client.post("/nachrichten/senden", data={"text": "weg damit", "ziel": "alle"})
    with app.app_context():
        nid = Nachricht.query.first().id
    client.post(f"/nachrichten/{nid}/loeschen")
    with app.app_context():
        assert Nachricht.query.count() == 0
