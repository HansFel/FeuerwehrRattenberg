"""Tests für den Admin-Bereich „Anforderungen an die App"."""
import os

import pytest

from app import create_app
from app.models import db, Anforderung, Benutzer, BenutzerRolle


@pytest.fixture
def app(tmp_path):
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "ADMIN_STARTPASSWORT": "admin",
        "ANFORDERUNGEN_PFAD": str(tmp_path / "ANFORDERUNGEN.md"),
    })
    with app.app_context():
        db.create_all()
        # Nicht-Admin für Zugriffstest
        b = Benutzer(username="orga", aktiv=True)
        b.set_password("pw")
        b.rollen.append(BenutzerRolle(rolle="organisator"))
        db.session.add(b)
        db.session.commit()
        yield app


@pytest.fixture
def client(app):
    return app.test_client()


def _login(client, user="admin", pw="admin"):
    return client.post("/anmelden", data={"username": user, "passwort": pw})


def test_nur_admin(client):
    _login(client, "orga", "pw")
    r = client.get("/anforderungen/", follow_redirects=True)
    assert "Anforderungen an die App".encode() not in r.data


def test_eintragen_schreibt_db_und_datei(client, app):
    _login(client)
    client.post("/anforderungen/neu",
                data={"text": "Getränke zählen 1 Punkt pro Stück."})
    with app.app_context():
        eintraege = Anforderung.query.all()
        assert len(eintraege) == 1
        assert eintraege[0].autor == "admin"
    # Export-Datei geschrieben und Inhalt vorhanden
    pfad = app.config["ANFORDERUNGEN_PFAD"]
    assert os.path.exists(pfad)
    with open(pfad, encoding="utf-8") as f:
        inhalt = f.read()
    assert "Getränke zählen 1 Punkt" in inhalt
    assert "## Offen (1)" in inhalt


def test_erledigt_und_loeschen(client, app):
    _login(client)
    client.post("/anforderungen/neu", data={"text": "Testwunsch"})
    with app.app_context():
        a = Anforderung.query.first()
        aid = a.id
    client.post(f"/anforderungen/{aid}/erledigt")
    with app.app_context():
        assert Anforderung.query.get(aid).erledigt is True
    client.post(f"/anforderungen/{aid}/loeschen")
    with app.app_context():
        assert Anforderung.query.get(aid) is None
