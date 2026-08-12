"""Tests für Speisekarte, Gäste-Bestellsystem, Kellner-Abrechnung und
Tisch-QR-Codes."""
import pytest

from app import create_app
from app.models import (db, Artikel, Bestellung, BestellPosition, Team,
                        Benutzer, BenutzerRolle, KATEGORIE_ESSEN,
                        KATEGORIE_GETRAENK)


@pytest.fixture
def app():
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "ADMIN_STARTPASSWORT": "admin",
    })
    with app.app_context():
        db.create_all()
        bier = Artikel(name="Bier", kategorie=KATEGORIE_GETRAENK, preis=3.5,
                       punkte_pro_einheit=2, aktiv=True)
        gulasch = Artikel(name="Gulasch", kategorie=KATEGORIE_ESSEN, preis=9.0,
                          punkte_pro_einheit=0, aktiv=True)
        team_a = Team(name="Team A")
        db.session.add_all([bier, gulasch, team_a])

        kellner = Benutzer(username="kellner1", name="Kelly", aktiv=True)
        kellner.set_password("pw")
        kellner.rollen.append(BenutzerRolle(rolle="kellner"))
        db.session.add(kellner)

        punkterichter = Benutzer(username="punkt", aktiv=True)
        punkterichter.set_password("pw")
        punkterichter.rollen.append(BenutzerRolle(rolle="punkterichter"))
        db.session.add(punkterichter)
        db.session.commit()
        yield app


@pytest.fixture
def client(app):
    return app.test_client()


def _login(client, user, pw):
    return client.post("/anmelden", data={"username": user, "passwort": pw})


def test_bestellseite_oeffentlich_ohne_login(client):
    r = client.get("/bestellen/5")
    assert r.status_code == 200
    assert "Tisch 5".encode() in r.data
    assert "Bier".encode() in r.data


def test_gast_bestellung_mit_teampunkten(client, app):
    with app.app_context():
        bier = Artikel.query.filter_by(name="Bier").first()
        team = Team.query.first()

    r = client.post("/bestellen/7", data={
        f"menge_{bier.id}": "3",
        "team_id": str(team.id),
    }, follow_redirects=True)
    assert r.status_code == 200
    assert "10.50".encode() in r.data or "10,50".encode() in r.data \
        or b"10.50" in r.data

    with app.app_context():
        b = Bestellung.query.filter_by(tisch_nummer=7).first()
        assert b is not None
        assert b.erfasst_von == ""              # Gast-Selbstbestellung
        assert len(b.positionen) == 1
        pos = b.positionen[0]
        assert pos.menge == 3
        assert pos.einzelpreis == 3.5
        assert pos.punkte_gesamt == 6            # 2 Pkt./Stk. * 3
        assert pos.team_id == team.id
        assert b.gesamtbetrag == pytest.approx(10.5)


def test_ein_team_gilt_fuer_gesamte_bestellung(client, app):
    """Ein Team wird EINMAL pro Bestellung gewählt, nicht pro Artikel –
    muss auf allen Positionen derselben Bestellung landen."""
    with app.app_context():
        bier = Artikel.query.filter_by(name="Bier").first()
        gulasch = Artikel.query.filter_by(name="Gulasch").first()
        team = Team.query.first()

    client.post("/bestellen/8", data={
        f"menge_{bier.id}": "2",
        f"menge_{gulasch.id}": "1",
        "team_id": str(team.id),
    })
    with app.app_context():
        b = Bestellung.query.filter_by(tisch_nummer=8).first()
        assert len(b.positionen) == 2
        assert all(p.team_id == team.id for p in b.positionen)


def test_leere_bestellung_wird_abgelehnt(client):
    r = client.post("/bestellen/3", data={}, follow_redirects=True)
    assert "mindestens einen Artikel".encode() in r.data
    assert Bestellung.query.count() == 0


def test_kellner_bestellung_wird_zugeordnet(client, app):
    _login(client, "kellner1", "pw")
    with app.app_context():
        gulasch = Artikel.query.filter_by(name="Gulasch").first()
    client.post("/bestellen/2", data={f"menge_{gulasch.id}": "2"})
    with app.app_context():
        b = Bestellung.query.filter_by(tisch_nummer=2).first()
        assert b.erfasst_von == "kellner1"


def test_bestellungen_uebersicht_nur_kellner_oder_organisator(client, app):
    with app.app_context():
        gulasch = Artikel.query.filter_by(name="Gulasch").first()
    client.post("/bestellen/1", data={f"menge_{gulasch.id}": "1"})

    # Punkterichter darf nicht
    _login(client, "punkt", "pw")
    r = client.get("/bestellungen/", follow_redirects=True)
    assert "Abrechnung".encode() not in r.data
    client.post("/abmelden")

    # Kellner darf
    _login(client, "kellner1", "pw")
    r = client.get("/bestellungen/")
    assert r.status_code == 200
    assert "Abrechnung".encode() in r.data


def test_bezahlt_umschalten(client, app):
    with app.app_context():
        gulasch = Artikel.query.filter_by(name="Gulasch").first()
    client.post("/bestellen/1", data={f"menge_{gulasch.id}": "1"})
    with app.app_context():
        b = Bestellung.query.first()
        bid = b.id
        assert b.bezahlt is False

    _login(client, "kellner1", "pw")
    client.post(f"/bestellungen/{bid}/bezahlt")
    with app.app_context():
        b = db.session.get(Bestellung, bid)
        assert b.bezahlt is True
        assert b.bezahlt_am is not None

    client.post(f"/bestellungen/{bid}/bezahlt")
    with app.app_context():
        b = db.session.get(Bestellung, bid)
        assert b.bezahlt is False
        assert b.bezahlt_am is None


def test_speisekarte_crud_nur_organisator(client, app):
    with app.app_context():
        org = Benutzer(username="orga", aktiv=True)
        org.set_password("pw")
        org.rollen.append(BenutzerRolle(rolle="organisator"))
        db.session.add(org)
        db.session.commit()

    # Punkterichter darf keinen Artikel anlegen
    _login(client, "punkt", "pw")
    client.post("/speisekarte/neu", data={"name": "Verboten", "preis": "1"})
    assert Artikel.query.filter_by(name="Verboten").first() is None
    client.post("/abmelden")

    # Organisator darf
    _login(client, "orga", "pw")
    r = client.post("/speisekarte/neu", data={
        "name": "Limo", "kategorie": KATEGORIE_GETRAENK, "preis": "2,50",
        "punkte_pro_einheit": "1", "reihenfolge": "0", "aktiv": "on",
    }, follow_redirects=True)
    assert r.status_code == 200
    artikel = Artikel.query.filter_by(name="Limo").first()
    assert artikel is not None
    assert artikel.preis == 2.5


def test_qrcode_pdf_organisator(client, app):
    with app.app_context():
        org = Benutzer(username="orga2", aktiv=True)
        org.set_password("pw")
        org.rollen.append(BenutzerRolle(rolle="organisator"))
        db.session.add(org)
        db.session.commit()

    _login(client, "orga2", "pw")
    r = client.get("/speisekarte/tische/qrcodes.pdf?von=1&bis=3")
    assert r.status_code == 200
    assert r.headers["Content-Type"] == "application/pdf"
    assert r.data[:4] == b"%PDF"


def test_qrcode_pdf_kein_zugriff_ohne_rolle(client):
    r = client.get("/speisekarte/tische/qrcodes.pdf?von=1&bis=3",
                   follow_redirects=True)
    assert "anmelden".encode() in r.data.lower()


def test_artikel_snapshot_bleibt_nach_preisaenderung_stabil(client, app):
    """Ändert der Organisator später den Preis, dürfen bereits aufgegebene
    Bestellungen nicht rückwirkend betroffen sein."""
    with app.app_context():
        bier = Artikel.query.filter_by(name="Bier").first()
        bier_id = bier.id

    client.post("/bestellen/9", data={f"menge_{bier_id}": "2"})
    with app.app_context():
        pos = BestellPosition.query.first()
        assert pos.einzelpreis == 3.5

        artikel = db.session.get(Artikel, bier_id)
        artikel.preis = 99.0
        db.session.commit()

        pos = BestellPosition.query.first()
        assert pos.einzelpreis == 3.5          # unverändert trotz Preisänderung
