"""Tests für Passwortsperre, CSV- und PDF-Export."""
import pytest

from app import create_app
from app.models import db, Team, Disziplin, Ergebnis, WERTUNG_ZEIT


@pytest.fixture
def app():
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "WETTBEWERB_PASSWORT": "geheim",
    })
    with app.app_context():
        db.create_all()
        d = Disziplin(name="Löschangriff", wertungsart=WERTUNG_ZEIT,
                      strafsekunden_pro_fehler=5.0)
        a = Team(name="A", wehr="Rattenberg")
        db.session.add_all([d, a])
        db.session.commit()
        db.session.add(Ergebnis(team_id=a.id, disziplin_id=d.id,
                                zeit_sekunden=80, fehlerpunkte=1))
        db.session.commit()
        yield app


@pytest.fixture
def client(app):
    return app.test_client()


def _anmelden(client, passwort="geheim"):
    return client.post("/anmelden", data={"passwort": passwort},
                       follow_redirects=True)


def test_sperre_blockt_ohne_anmeldung(client):
    # Team anlegen ohne Anmeldung -> Umleitung zur Anmeldung, nichts gespeichert
    antwort = client.post("/teams/neu", data={"name": "Heimlich"},
                          follow_redirects=True)
    assert "anmelden".encode() in antwort.data.lower()
    assert Team.query.filter_by(name="Heimlich").first() is None


def test_falsches_passwort(client):
    antwort = _anmelden(client, "falsch")
    assert "Falsches Passwort".encode() in antwort.data


def test_anmeldung_schaltet_frei(client):
    _anmelden(client)
    antwort = client.post("/teams/neu",
                          data={"name": "FF Neu", "wehr": "Ort"},
                          follow_redirects=True)
    assert antwort.status_code == 200
    assert Team.query.filter_by(name="FF Neu").first() is not None


def test_csv_export(client):
    antwort = client.get("/export/gesamtwertung.csv")
    assert antwort.status_code == 200
    assert "text/csv" in antwort.headers["Content-Type"]
    assert antwort.data.startswith("﻿".encode())   # BOM für Excel


def test_pdf_export(client):
    for pfad in ("/pdf/gesamtwertung.pdf", "/pdf/disziplin/1.pdf",
                 "/pdf/startliste/1.pdf"):
        antwort = client.get(pfad)
        assert antwort.status_code == 200, pfad
        assert antwort.headers["Content-Type"] == "application/pdf"
        assert antwort.data[:4] == b"%PDF"
