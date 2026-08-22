"""Tests für CSV- und PDF-Export (öffentlich lesbar)."""
import pytest
import base64
import re
import zlib

from app import create_app
from app.models import (db, Team, Disziplin, Ergebnis, Startplatz,
                        WERTUNG_ZEIT)


def _reportlab_text(pdf: bytes) -> str:
    """Textfragmente aus den komprimierten ReportLab-Seitenströmen lesen.

    Die Tabellenköpfe dürfen durch Paragraph-Umbruch auf mehrere Fragmente
    verteilt sein; für Reihenfolgeprüfungen reicht die Zeichenfolge aller
    ausgegebenen Textoperatoren.
    """
    fragmente = []
    for roh in re.findall(rb"stream\r?\n(.*?)endstream", pdf, re.DOTALL):
        try:
            inhalt = zlib.decompress(base64.a85decode(
                roh.strip().rstrip(b"~>"), adobe=False))
        except (ValueError, zlib.error):
            continue
        fragmente.extend(re.findall(rb"\((.*?)\)\s*Tj", inhalt))
    return " ".join(f.decode("latin-1") for f in fragmente)


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


def test_pdf_gesamtwertung_enthaelt_nur_platz_und_mannschaft(app):
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

    text = _reportlab_text(r.data)
    assert "Rang" in text
    assert "Mannschaft" in text
    assert "PDF-Test-Team" in text
    for stichwort in ("Rangpunkte", "Strafsek", "Gemessene", "Gesamtzeit"):
        assert stichwort not in text


def test_pdf_tabellen_brechen_lange_namen_innerhalb_der_spalte_um():
    """Lange Namen müssen die Zeile erhöhen statt Nachbarspalten zu
    überdecken."""
    from app.blueprints.pdf import _tabelle
    from reportlab.lib.units import mm

    kurz = _tabelle([["Rang", "Mannschaft", "Ort"],
                     ["1", "Kurz", "Rattenberg"]],
                    [18 * mm, 70 * mm, 70 * mm])
    lang = _tabelle([["Rang", "Mannschaft", "Ort"],
                     ["1", "Freiwillige Feuerwehr mit einem besonders langen Mannschaftsnamen",
                      "Sehr langer Orts- und Abschnittsname"]],
                    [18 * mm, 70 * mm, 70 * mm])

    kurz.wrapOn(None, 174 * mm, 250 * mm)
    lang.wrapOn(None, 174 * mm, 250 * mm)
    assert lang._rowHeights[1] > kurz._rowHeights[1]


def test_pdf_startliste_sortiert_lauf_numerisch_bahn_und_alphabetisch(app):
    with app.app_context():
        d = db.session.query(Disziplin).first()
        disziplin_id = d.id
        zulu = Team(name="Zulu mit langem Namen", wehr="Ort Z")
        alpha = Team(name="Alpha", wehr="Ort A")
        ohne = Team(name="Ohne Startnummer", wehr="Ort O")
        db.session.add_all([zulu, alpha, ohne])
        db.session.flush()
        db.session.add_all([
            Startplatz(team_id=zulu.id, disziplin_id=d.id, startnummer=2,
                       heat="Vorrunde 2"),
            Startplatz(team_id=alpha.id, disziplin_id=d.id, startnummer=2,
                       heat="Vorrunde 2"),
            Startplatz(team_id=ohne.id, disziplin_id=d.id, startnummer=1,
                       heat="Vorrunde 10"),
        ])
        db.session.commit()

    antwort = app.test_client().get(f"/pdf/startliste/{disziplin_id}.pdf")
    text = _reportlab_text(antwort.data)
    assert text.index("Alpha") < text.index("Zulu") < text.index("Ohne Startnummer")
