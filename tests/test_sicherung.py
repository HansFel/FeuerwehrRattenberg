"""Tests für die Datensicherung (SQLite-Backup)."""
import os

import pytest

from app import create_app
from app.models import db, Team, Sicherung
from app import sicherung as dienst


@pytest.fixture
def app(tmp_path):
    dbdatei = tmp_path / "wettbewerb.sqlite"
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{dbdatei}",
        "ADMIN_STARTPASSWORT": "admin",
    })
    app.instance_path = str(tmp_path)      # Sicherungen isoliert im Temp-Ordner
    yield app


@pytest.fixture
def client(app):
    return app.test_client()


def _login(client):
    return client.post("/anmelden",
                       data={"username": "admin", "passwort": "admin"})


def test_sicherung_nur_admin(client):
    r = client.get("/sicherung/", follow_redirects=True)
    assert "anmelden".encode() in r.data.lower()


def test_sicherung_erstellen_erzeugt_datei(client, app):
    _login(client)
    client.post("/sicherung/erstellen")
    with app.app_context():
        alle = Sicherung.query.all()
        assert len(alle) == 1
        pfad = os.path.join(app.instance_path, "sicherungen", alle[0].dateiname)
        assert os.path.exists(pfad)
        assert alle[0].checksum                       # Prüfsumme gesetzt
        assert alle[0].erstellt_von == "admin"


def test_wiederherstellen_holt_geloeschte_daten_zurueck(app):
    with app.app_context():
        db.session.add(Team(name="Wiederkehr"))
        db.session.commit()

        s = dienst.erstellen(typ="manuell", von="admin")

        # Team löschen …
        db.session.delete(Team.query.filter_by(name="Wiederkehr").first())
        db.session.commit()
        assert Team.query.filter_by(name="Wiederkehr").first() is None

        # … und aus der Sicherung wiederherstellen
        dienst.wiederherstellen(s.id)
        assert Team.query.filter_by(name="Wiederkehr").first() is not None
        # Nach dem Abgleich sind beide Dateien (Original + Vorher-Sicherung)
        # in der Liste sichtbar
        assert Sicherung.query.count() == 2
        import os as _os
        dateien = _os.listdir(_os.path.join(app.instance_path, "sicherungen"))
        assert len([d for d in dateien if d.endswith(".sqlite.gz")]) == 2


def test_aufbewahrung_begrenzt_anzahl(app):
    with app.app_context():
        for _ in range(3):
            dienst.erstellen(typ="manuell", von="admin")
        assert dienst.aufraeumen(max_sicherungen=2) == 1
        assert Sicherung.query.count() == 2


def test_groesse_formatiert():
    s = Sicherung(dateigroesse=2048)
    assert s.groesse_formatiert == "2.0 KB"
