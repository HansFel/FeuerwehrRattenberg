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


def test_pdf_gesamtwertung_enthaelt_gemessene_zeit_und_strafen(app):
    """Der PDF-Export der Gesamtwertung muss dieselben Spalten wie die
    normale Web-Ansicht enthalten (Getraenkepunkte/Strafsekunden/gemessene
    Zeit/Gesamtzeit), nicht nur die alten Rangpunkte."""
    from app.models import db, Disziplin, Team, Startplatz
    with app.app_context():
        d = Disziplin(name="Siloplanen-Race")
        team = Team(name="PDF-Test-Team")
        db.session.add_all([d, team])
        db.session.commit()
        db.session.add(Startplatz(team_id=team.id, disziplin_id=d.id,
                                  startnummer=1, heat="12 Platzierungslauf Platz 9-9",
                                  ergebnis_sekunden=42.0))
        db.session.commit()

    client = app.test_client()
    r = client.get("/pdf/gesamtwertung.pdf")
    assert r.status_code == 200

    # ReportLab komprimiert den Seiteninhalt (ASCII85 + Flate) - zum Prüfen
    # der enthaltenen Spalten muss der Stream erst dekodiert werden.
    import base64
    import re
    import zlib
    match = re.search(rb"stream\r?\n(.*?)endstream", r.data, re.DOTALL)
    roh = match.group(1).strip().rstrip(b"~>")
    dekodiert = zlib.decompress(base64.a85decode(roh, adobe=False))
    text = dekodiert.decode("latin-1")
    # Getraenkepunkte sind seit Build 57 nur noch in der Team-Challenge-Wertung,
    # nicht mehr in der Siloplanen-Race-Gesamtwertung.
    for stichwort in ("Rangpunkte", "Strafsek", "Gemessene Zeit", "Gesamtzeit"):
        assert stichwort in text
