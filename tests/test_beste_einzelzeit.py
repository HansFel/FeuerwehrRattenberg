"""Tests für die laufende beste Einzelzeit über alle Läufe."""
import base64
import re
import zlib

from app import create_app
from app.models import db, Team, Mitglied, NotfallLauf, NotfallBahn
from app.wertung import beste_einzelzeit


def _app_mit_zeiten():
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
    })
    with app.app_context():
        team_a = Team(name="Team A")
        team_b = Team(name="Team B")
        for pos, name in enumerate(("Anna", "Berta", "Clara", "Dora"), 1):
            team_a.mitglieder.append(Mitglied(vorname=name, position=pos))
        for pos, name in enumerate(("Emil", "Franz", "Gustav", "Hans"), 1):
            team_b.mitglieder.append(Mitglied(vorname=name, position=pos))

        lauf_1 = NotfallLauf(bezeichnung="Vorrunde 1")
        lauf_1.bahnen.append(NotfallBahn(
            bahn_nr=1, team=team_a, zeit_laeufer1=5.0, zeit_laeufer2=4.8,
            zeit_laeufer3=5.1, zeit_laeufer4=5.2))
        # Schnellere 3,0 s in einer unvollständigen Bahn dürfen nicht zählen.
        lauf_1.bahnen.append(NotfallBahn(
            bahn_nr=2, team=team_b, zeit_laeufer1=3.0))

        lauf_2 = NotfallLauf(bezeichnung="Vorrunde 2")
        lauf_2.bahnen.append(NotfallBahn(
            bahn_nr=3, team=team_b, zeit_laeufer1=4.7, zeit_laeufer2=4.6,
            zeit_laeufer3=4.9, zeit_laeufer4=5.0))
        db.session.add_all([team_a, team_b, lauf_1, lauf_2])
        db.session.commit()
    return app


def _pdf_text(pdf: bytes) -> str:
    fragmente = []
    for roh in re.findall(rb"stream\r?\n(.*?)endstream", pdf, re.DOTALL):
        try:
            inhalt = zlib.decompress(base64.a85decode(
                roh.strip().rstrip(b"~>"), adobe=False))
        except (ValueError, zlib.error):
            continue
        fragmente.extend(re.findall(rb"\((.*?)\)\s*Tj", inhalt))
    return " ".join(f.decode("latin-1") for f in fragmente)


def test_beste_einzelzeit_ueber_alle_vollstaendigen_laeufe():
    app = _app_mit_zeiten()
    with app.app_context():
        beste = beste_einzelzeit()
        assert beste["zeit"] == 4.6
        assert beste["laeufer_name"] == "Franz"
        assert beste["team"].name == "Team B"
        assert beste["lauf"].bezeichnung == "Vorrunde 2"
        assert beste["bahn_nr"] == 3
        assert beste["laeufer_nr"] == 2


def test_beste_einzelzeit_in_web_besucheransicht_und_pdf():
    app = _app_mit_zeiten()
    client = app.test_client()

    for pfad in ("/wertung/", "/besucher/", "/besucher/live-fragment"):
        antwort = client.get(pfad)
        assert antwort.status_code == 200
        text = antwort.get_data(as_text=True)
        assert "Franz" in text
        assert "4,60 s" in text

    pdf = client.get("/pdf/gesamtwertung.pdf")
    assert pdf.status_code == 200
    text = _pdf_text(pdf.data)
    assert "Beste Einzelzeit" in text
    assert "Franz" in text
    assert "4,60 s" in text
