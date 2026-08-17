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
                       punkte_pro_einheit=2, pfand_pro_einheit=1.0, aktiv=True)
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

        ausschank = Benutzer(username="ausschank1", name="Aussi", aktiv=True)
        ausschank.set_password("pw")
        ausschank.rollen.append(BenutzerRolle(rolle="ausschank"))
        db.session.add(ausschank)
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
    # 3 x 3,50 Preis + 3 x 1,00 Pfand = 13,50 Gesamtbetrag
    assert "13.50".encode() in r.data or "13,50".encode() in r.data

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
        assert pos.pfand_pro_einheit == 1.0
        assert pos.pfand_summe == pytest.approx(3.0)
        assert b.gesamtbetrag == pytest.approx(13.5)         # inkl. Pfand
        assert b.pfand_gesamt == pytest.approx(3.0)
        assert b.pfand_offen_betrag == pytest.approx(3.0)    # noch nichts zurück


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


def test_bestellungen_uebersicht_nur_kellner_organisator_ausschank(client, app):
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
    client.post("/abmelden")

    # Ausschank darf ebenfalls
    _login(client, "ausschank1", "pw")
    r = client.get("/bestellungen/")
    assert r.status_code == 200
    assert "Abrechnung".encode() in r.data


def test_ausschank_kein_zugriff_auf_speisekarte(client):
    """Ausschank ist eine eigene Rolle ohne Speisekarten-Verwaltung (Organisator-Sache)."""
    _login(client, "ausschank1", "pw")
    r = client.post("/speisekarte/neu", data={"name": "Verboten", "preis": "1"})
    assert Artikel.query.filter_by(name="Verboten").first() is None


def test_ausschank_startseite_leitet_auf_einfaches_dashboard(client):
    _login(client, "ausschank1", "pw")
    r = client.get("/", follow_redirects=True)
    assert r.status_code == 200
    assert "Gruppe auswählen".encode() in r.data
    assert "Bestellung und Bezahlung".encode() in r.data
    assert "Pfand zurückgeben".encode() not in r.data
    assert "Aktives Dashboard".encode() not in r.data


def test_ausschank_verbucht_getraenke_sofort_bezahlt(client, app):
    _login(client, "ausschank1", "pw")
    with app.app_context():
        bier = Artikel.query.filter_by(name="Bier").first()
        team = Team.query.filter_by(name="Team A").first()
        bier_id, team_id = bier.id, team.id

    r = client.post("/ausschank/", data={
        "team_id": str(team_id),
        f"menge_{bier_id}": "3",
    }, follow_redirects=True)
    assert r.status_code == 200
    assert "Bestellung und Bezahlung bestätigt".encode() in r.data

    with app.app_context():
        bestellung = Bestellung.query.filter_by(tisch_nummer=0).one()
        assert bestellung.erfasst_von == "ausschank1"
        assert bestellung.bezahlt is True
        assert bestellung.bezahlt_am is not None
        assert len(bestellung.positionen) == 1
        assert bestellung.positionen[0].team_id == team_id
        assert bestellung.positionen[0].menge == 3
        assert bestellung.gesamtpunkte == 6


def test_ausschank_braucht_gruppe_und_getraenk(client, app):
    _login(client, "ausschank1", "pw")
    with app.app_context():
        bier = Artikel.query.filter_by(name="Bier").first()
        team = Team.query.filter_by(name="Team A").first()
        bier_id, team_id = bier.id, team.id

    r = client.post("/ausschank/", data={f"menge_{bier_id}": "1"},
                    follow_redirects=True)
    assert "Bitte zuerst eine Gruppe".encode() in r.data
    assert Bestellung.query.count() == 0

    r = client.post("/ausschank/", data={"team_id": str(team_id)},
                    follow_redirects=True)
    assert "mindestens ein Getränk".encode() in r.data
    assert Bestellung.query.count() == 0


def test_ausschank_pfandrueckgabe_wird_nur_berechnet(client, app):
    _login(client, "ausschank1", "pw")
    with app.app_context():
        bier = Artikel.query.filter_by(name="Bier").first()
        team = Team.query.filter_by(name="Team A").first()
        bier_id, team_id = bier.id, team.id

    # 2 Bier: 9,00 Euro inklusive Pfand; 1 Pfand retour: Zahlbetrag 8,00.
    r = client.post("/ausschank/", data={
        "team_id": str(team_id),
        f"menge_{bier_id}": "2",
        "pfand_zurueck": "1",
    }, follow_redirects=True)
    assert "Zahlbetrag 8.00 €".encode() in r.data

    with app.app_context():
        position = BestellPosition.query.one()
        assert position.pfand_zurueckgegeben == 0
        assert position.team_id == team_id


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


def test_speisekarte_aushang_pdf_organisator(client, app):
    with app.app_context():
        org = Benutzer(username="orga_pdf", aktiv=True)
        org.set_password("pw")
        org.rollen.append(BenutzerRolle(rolle="organisator"))
        db.session.add(org)
        db.session.commit()

    _login(client, "orga_pdf", "pw")
    r = client.get("/speisekarte/aushang.pdf")
    assert r.status_code == 200
    assert r.headers["Content-Type"] == "application/pdf"
    assert r.headers["Content-Disposition"] == (
        'attachment; filename="speisekarte_aushang.pdf"')
    assert r.data[:4] == b"%PDF"


def test_speisekarte_aushang_pdf_kein_zugriff_ohne_rolle(client):
    r = client.get("/speisekarte/aushang.pdf", follow_redirects=True)
    assert "anmelden".encode() in r.data.lower()


def test_speisekarte_pfand_feld_speicherbar(client, app):
    with app.app_context():
        org = Benutzer(username="orga3", aktiv=True)
        org.set_password("pw")
        org.rollen.append(BenutzerRolle(rolle="organisator"))
        db.session.add(org)
        db.session.commit()

    _login(client, "orga3", "pw")
    client.post("/speisekarte/neu", data={
        "name": "Becher", "kategorie": KATEGORIE_GETRAENK, "preis": "0",
        "punkte_pro_einheit": "0", "pfand_pro_einheit": "2,00",
        "reihenfolge": "0", "aktiv": "on",
    })
    artikel = Artikel.query.filter_by(name="Becher").first()
    assert artikel is not None
    assert artikel.pfand_pro_einheit == 2.0


def test_pfand_tisch_zeigt_offene_positionen(client, app):
    with app.app_context():
        bier = Artikel.query.filter_by(name="Bier").first()
    client.post("/bestellen/4", data={f"menge_{bier.id}": "3"})

    _login(client, "kellner1", "pw")
    r = client.get("/pfand/4")
    assert r.status_code == 200
    assert "3 von 3 offen".encode() in r.data
    assert "3.00".encode() in r.data or "3,00".encode() in r.data


def test_pfand_teilrueckgabe(client, app):
    with app.app_context():
        bier = Artikel.query.filter_by(name="Bier").first()
    client.post("/bestellen/6", data={f"menge_{bier.id}": "3"})
    with app.app_context():
        pos = BestellPosition.query.filter_by(artikel_name="Bier").first()
        pos_id = pos.id

    _login(client, "kellner1", "pw")
    client.post(f"/pfand/position/{pos_id}/rueckgabe")   # -1
    with app.app_context():
        pos = db.session.get(BestellPosition, pos_id)
        assert pos.pfand_zurueckgegeben == 1
        assert pos.pfand_offen_anzahl == 2               # nicht alles kommt zurück

    client.post(f"/pfand/position/{pos_id}/rueckgabe", data={"alle": "1"})
    with app.app_context():
        pos = db.session.get(BestellPosition, pos_id)
        assert pos.pfand_zurueckgegeben == 3
        assert pos.pfand_offen_anzahl == 0

    # Darf nicht ueber die bestellte Menge hinaus zurueckgegeben werden
    client.post(f"/pfand/position/{pos_id}/rueckgabe")
    with app.app_context():
        pos = db.session.get(BestellPosition, pos_id)
        assert pos.pfand_zurueckgegeben == 3             # gedeckelt bei menge


def test_pfand_rueckgabe_auch_fuer_ausschank(client, app):
    with app.app_context():
        bier = Artikel.query.filter_by(name="Bier").first()
    client.post("/bestellen/10", data={f"menge_{bier.id}": "1"})
    with app.app_context():
        pos_id = BestellPosition.query.filter_by(artikel_name="Bier").first().id

    _login(client, "ausschank1", "pw")
    r = client.post(f"/pfand/position/{pos_id}/rueckgabe", data={"alle": "1"},
                    follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        pos = db.session.get(BestellPosition, pos_id)
        assert pos.pfand_offen_anzahl == 0


def test_pfand_route_erfordert_rolle(client, app):
    with app.app_context():
        bier = Artikel.query.filter_by(name="Bier").first()
    client.post("/bestellen/11", data={f"menge_{bier.id}": "1"})

    # Punkterichter hat keinen Zugriff auf die Pfand-Rueckgabe
    _login(client, "punkt", "pw")
    r = client.get("/pfand/11", follow_redirects=True)
    assert "anmelden".encode() in r.data.lower() or "Pfand-Rückgabe".encode() not in r.data


def test_artikel_loeschen_trotz_bestehender_bestellung(client, app):
    """Ein bereits bestellter Artikel muss loeschbar sein, ohne dass die
    Bestellhistorie (Fremdschluessel-Fehler) das verhindert."""
    with app.app_context():
        org = Benutzer(username="orga4", aktiv=True)
        org.set_password("pw")
        org.rollen.append(BenutzerRolle(rolle="organisator"))
        db.session.add(org)
        db.session.commit()
        bier_id = Artikel.query.filter_by(name="Bier").first().id

    client.post("/bestellen/5", data={f"menge_{bier_id}": "1"})

    _login(client, "orga4", "pw")
    r = client.post(f"/speisekarte/{bier_id}/loeschen", follow_redirects=True)
    assert r.status_code == 200
    assert Artikel.query.filter_by(name="Bier").first() is None

    with app.app_context():
        pos = BestellPosition.query.filter_by(artikel_name="Bier").first()
        assert pos is not None                # Bestellhistorie bleibt erhalten
        assert pos.artikel_id is None          # Referenz gekappt
        assert pos.einzelpreis == 3.5          # Schnappschuss unveraendert


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


# ── Kassen-Ansicht (kombinierte Bestellung + Pfand-Rückgabe) ─────────────────

def test_kasse_route_erfordert_rolle(client):
    r = client.get("/bestellen/1/kasse", follow_redirects=True)
    assert "anmelden".encode() in r.data.lower()


def test_kasse_get_zeigt_formular(client, app):
    _login(client, "kellner1", "pw")
    r = client.get("/bestellen/1/kasse")
    assert r.status_code == 200
    assert "Kasse".encode() in r.data
    assert "Bier".encode() in r.data
    assert "Becher-Gutschrift".encode() in r.data  # Bier hat Pfand -> Rückgabe-Kachel


def test_kasse_bestellung_erstellt_und_erfasst_von_gesetzt(client, app):
    with app.app_context():
        gulasch = Artikel.query.filter_by(name="Gulasch").first()
        gulasch_id = gulasch.id

    _login(client, "kellner1", "pw")
    r = client.post("/bestellen/2/kasse", data={f"menge_{gulasch_id}": "2"},
                    follow_redirects=True)
    assert r.status_code == 200

    with app.app_context():
        b = Bestellung.query.filter_by(tisch_nummer=2).first()
        assert b is not None
        assert b.erfasst_von == "kellner1"
        assert len(b.positionen) == 1
        assert b.positionen[0].menge == 2


def test_kasse_pfand_rueckgabe_ohne_neue_bestellung(client, app):
    """Reine Pfand-Rückgabe über die Kasse, ohne dass etwas Neues bestellt wird."""
    with app.app_context():
        bier = Artikel.query.filter_by(name="Bier").first()
        bier_id = bier.id
    client.post("/bestellen/3", data={f"menge_{bier_id}": "2"})
    vor_anzahl = Bestellung.query.count()

    _login(client, "kellner1", "pw")
    r = client.post("/bestellen/3/kasse", data={f"rueckgabe_{bier_id}": "1"},
                    follow_redirects=True)
    assert r.status_code == 200
    # Auszahlung an Gast, da nur Rückgabe ohne neue Bestellung
    assert "Auszahlung an Gast".encode() in r.data
    assert "1.00".encode() in r.data or "1,00".encode() in r.data

    with app.app_context():
        # Es wurde keine neue Bestellung angelegt, nur die alte Position aktualisiert
        assert Bestellung.query.count() == vor_anzahl
        pos = BestellPosition.query.filter_by(artikel_name="Bier").first()
        assert pos.pfand_zurueckgegeben == 1


def test_kasse_kombiniert_bestellung_und_pfand_rueckgabe(client, app):
    """Kernszenario aus der Anforderung: Kellner nimmt neue Getränke auf UND
    nimmt gleichzeitig Pfand zurück -> eine korrekte Endsumme."""
    with app.app_context():
        bier = Artikel.query.filter_by(name="Bier").first()
        bier_id = bier.id
    # Erste Runde: Gast bestellt 2 Bier (2 x 3,50 + 2 x 1,00 Pfand = 9,00)
    client.post("/bestellen/4", data={f"menge_{bier_id}": "2"})

    _login(client, "kellner1", "pw")
    # Kellner nimmt 1 neues Bier auf UND bekommt 2 leere Becher zurück
    r = client.post("/bestellen/4/kasse", data={
        f"menge_{bier_id}": "1", f"rueckgabe_{bier_id}": "2",
    }, follow_redirects=True)
    assert r.status_code == 200

    # Neue Bestellung: 1 x 3,50 + 1 x 1,00 Pfand = 4,50
    # Pfand-Gutschrift: 2 x 1,00 = 2,00
    # Netto: 4,50 - 2,00 = 2,50 -> "Zu kassieren"
    assert "Zu kassieren".encode() in r.data
    assert "2.50".encode() in r.data or "2,50".encode() in r.data

    with app.app_context():
        alle_bier_positionen = BestellPosition.query.filter_by(
            artikel_name="Bier").order_by(BestellPosition.id).all()
        assert len(alle_bier_positionen) == 2
        # Die älteste (erste) Bestellung sollte die Pfand-Rückgabe erhalten (FIFO)
        assert alle_bier_positionen[0].pfand_zurueckgegeben == 2
        assert alle_bier_positionen[1].pfand_zurueckgegeben == 0


def test_kasse_beleg_zeigt_pfand_anteil_separat(client, app):
    """Auf dem Kassenbeleg muss ersichtlich sein, wie viel vom neuen
    Bestellbetrag Pfand ist – nicht nur die Endsumme."""
    with app.app_context():
        bier = Artikel.query.filter_by(name="Bier").first()
        bier_id = bier.id

    _login(client, "kellner1", "pw")
    r = client.post("/bestellen/12/kasse", data={f"menge_{bier_id}": "2"},
                    follow_redirects=True)
    assert r.status_code == 200
    # 2 x 3,50 + 2 x 1,00 Pfand = 9,00 Zwischensumme, davon 2,00 Pfand
    assert "davon".encode() in r.data
    assert "2.00".encode() in r.data or "2,00".encode() in r.data


def test_pfand_automatisch_zurueckgeben_ueber_mehrere_bestellungen_fifo(app):
    """FIFO über mehrere Bestellungen hinweg, inkl. Deckelung wenn mehr
    verlangt wird als tatsächlich offen ist."""
    from app.blueprints.bestellung import _pfand_automatisch_zurueckgeben

    with app.app_context():
        bier = Artikel.query.filter_by(name="Bier").first()

        b1 = Bestellung(tisch_nummer=20)
        b1.positionen.append(BestellPosition(
            artikel_id=bier.id, artikel_name="Bier", einzelpreis=3.5, menge=1,
            pfand_pro_einheit=1.0))
        b2 = Bestellung(tisch_nummer=20)
        b2.positionen.append(BestellPosition(
            artikel_id=bier.id, artikel_name="Bier", einzelpreis=3.5, menge=2,
            pfand_pro_einheit=1.0))
        db.session.add_all([b1, b2])
        db.session.commit()

        # 2 zurückgeben -> zuerst die ältere Bestellung (1 Stk.) komplett,
        # dann 1 Stk. von der zweiten Bestellung
        gutschrift = _pfand_automatisch_zurueckgeben(20, bier.id, 2)
        assert gutschrift == pytest.approx(2.0)

        pos1 = BestellPosition.query.join(Bestellung).filter(
            Bestellung.id == b1.id).first()
        pos2 = BestellPosition.query.join(Bestellung).filter(
            Bestellung.id == b2.id).first()
        assert pos1.pfand_zurueckgegeben == 1
        assert pos2.pfand_zurueckgegeben == 1

        # Nochmal 5 verlangen, obwohl nur noch 1 offen ist (Deckelung)
        gutschrift2 = _pfand_automatisch_zurueckgeben(20, bier.id, 5)
        assert gutschrift2 == pytest.approx(1.0)
        pos2 = BestellPosition.query.join(Bestellung).filter(
            Bestellung.id == b2.id).first()
        assert pos2.pfand_zurueckgegeben == 2

        # Jetzt ist nichts mehr offen -> 0 Gutschrift
        gutschrift3 = _pfand_automatisch_zurueckgeben(20, bier.id, 1)
        assert gutschrift3 == pytest.approx(0.0)


def test_kasse_bestaetigung_leert_session_und_leitet_ohne_beleg_weiter(client, app):
    with app.app_context():
        gulasch = Artikel.query.filter_by(name="Gulasch").first()
        gulasch_id = gulasch.id

    _login(client, "kellner1", "pw")
    client.post("/bestellen/2/kasse", data={f"menge_{gulasch_id}": "1"})
    r = client.get("/bestellen/kasse/bestaetigung")
    assert r.status_code == 200
    assert "Kassenbeleg".encode() in r.data

    # Zweiter Aufruf ohne neue Bestellung -> Session ist geleert -> Weiterleitung
    r2 = client.get("/bestellen/kasse/bestaetigung", follow_redirects=True)
    assert r2.status_code == 200
    assert "Kassenbeleg".encode() not in r2.data


def test_kasse_leere_eingabe_wird_abgelehnt(client, app):
    _login(client, "kellner1", "pw")
    r = client.post("/bestellen/1/kasse", data={}, follow_redirects=True)
    assert "mindestens einen Artikel".encode() in r.data


def test_formular_ansicht_zeigt_kasse_link_nur_fuer_personal(client, app):
    r = client.get("/bestellen/1")
    assert "Kassen-Ansicht".encode() not in r.data

    _login(client, "kellner1", "pw")
    r = client.get("/bestellen/1")
    assert "Kassen-Ansicht".encode() in r.data
