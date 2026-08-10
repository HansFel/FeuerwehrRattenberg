"""Tests für CSV- und PDF-Export (öffentlich lesbar)."""
import pytest

from app import create_app
from app.models import db, Team, Disziplin, Ergebnis, WERTUNG_ZEIT


@pytest.fixture
def app():
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
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
