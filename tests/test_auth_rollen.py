"""Tests für Login und Rollensystem (Konzept aus MGRSoftware)."""
import pytest

from app import create_app
from app.models import db, Team, Disziplin, Benutzer, BenutzerRolle, WERTUNG_ZEIT


@pytest.fixture
def app():
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "ADMIN_STARTPASSWORT": "admin",
    })
    with app.app_context():
        db.create_all()
        d = Disziplin(name="Löschangriff", wertungsart=WERTUNG_ZEIT)
        db.session.add(d)
        # Punkterichter-Benutzer anlegen
        pr = Benutzer(username="punkt", name="Peter", aktiv=True)
        pr.set_password("pw")
        pr.rollen.append(BenutzerRolle(rolle="punkterichter"))
        db.session.add(pr)
        db.session.commit()
        yield app


@pytest.fixture
def client(app):
    return app.test_client()


def _login(client, username, passwort):
    return client.post("/anmelden",
                       data={"username": username, "passwort": passwort},
                       follow_redirects=True)


def test_standard_admin_wurde_angelegt(app):
    with app.app_context():
        admin = Benutzer.query.filter_by(username="admin").first()
        assert admin is not None
        assert admin.ist_admin()
        assert admin.check_password("admin")


def test_ohne_login_kein_schreiben(client):
    antwort = client.post("/teams/neu", data={"name": "X"},
                          follow_redirects=True)
    assert "anmelden".encode() in antwort.data.lower()
    assert Team.query.filter_by(name="X").first() is None


def test_falsche_zugangsdaten(client):
    antwort = _login(client, "admin", "falsch")
    assert "falsch".encode() in antwort.data.lower()


def test_admin_darf_team_anlegen(client):
    _login(client, "admin", "admin")
    client.post("/teams/neu", data={"name": "FF Admin"})
    assert Team.query.filter_by(name="FF Admin").first() is not None


def test_rolle_reicht_nicht_fuer_fremde_aktion(client):
    # Punkterichter darf KEINE Mannschaft anlegen (das ist Organisator/Admin)
    _login(client, "punkt", "pw")
    antwort = client.post("/teams/neu", data={"name": "Verboten"},
                          follow_redirects=True)
    assert Team.query.filter_by(name="Verboten").first() is None
    assert "rolle".encode() in antwort.data.lower()


def test_punkterichter_darf_ergebnis_erfassen(client):
    _login(client, "punkt", "pw")
    team = Team(name="Team1")
    db.session.add(team)
    db.session.commit()
    d = Disziplin.query.first()
    client.post(f"/wertung/disziplin/{d.id}",
                data={"team_id": team.id, "zeit_sekunden": "42"})
    from app.models import Ergebnis
    assert Ergebnis.query.filter_by(team_id=team.id).first() is not None


def test_person_anlegen_ohne_rollen(client):
    _login(client, "admin", "admin")
    client.post("/benutzer/neu", data={"username": "neu1", "name": "Neu Eins",
                                       "passwort": "pw12", "aktiv": "on"})
    b = Benutzer.query.filter_by(username="neu1").first()
    assert b is not None
    assert b.rollen_namen == []          # Rollen kommen separat per Dropdown


def test_rolle_per_dropdown_zuweisen_und_entfernen(client):
    _login(client, "admin", "admin")
    ziel = Benutzer.query.filter_by(username="punkt").first()
    # zuweisen: startrichter
    client.post("/benutzer/rollen/neu",
                data={"benutzer_id": ziel.id, "rolle": "startrichter"})
    assert "startrichter" in ziel.rollen_namen
    # doppelte Zuweisung wird abgelehnt
    client.post("/benutzer/rollen/neu",
                data={"benutzer_id": ziel.id, "rolle": "startrichter"})
    assert ziel.rollen_namen.count("startrichter") == 1
    # entfernen
    from app.models import BenutzerRolle
    zuw = BenutzerRolle.query.filter_by(benutzer_id=ziel.id,
                                        rolle="startrichter").first()
    client.post(f"/benutzer/rollen/{zuw.id}/loeschen")
    assert "startrichter" not in ziel.rollen_namen


def test_letzte_admin_rolle_geschuetzt(client):
    _login(client, "admin", "admin")
    from app.models import BenutzerRolle
    admin = Benutzer.query.filter_by(username="admin").first()
    zuw = BenutzerRolle.query.filter_by(benutzer_id=admin.id,
                                        rolle="administrator").first()
    client.post(f"/benutzer/rollen/{zuw.id}/loeschen")
    # letzte Admin-Rolle bleibt bestehen
    assert admin.ist_admin()


def test_dashboard_punkterichter_sieht_nur_seine_rolle(client):
    _login(client, "punkt", "pw")
    r = client.get("/")
    assert "Deine Rollen".encode() in r.data
    assert "Ergebnisse erfassen".encode() in r.data      # Punkterichter-Karte
    assert "Verwaltung".encode() not in r.data           # keine Admin-Karte
    assert "🎯 Disziplinen".encode() not in r.data        # keine Organisator-Karte


def test_dashboard_admin_sieht_alles(client):
    _login(client, "admin", "admin")
    r = client.get("/")
    assert "Ergebnisse erfassen".encode() in r.data
    assert "Verwaltung".encode() in r.data
    assert "Mannschaften".encode() in r.data


def test_mehrrollen_login_fuehrt_zur_rollenwahl(client, app):
    with app.app_context():
        from app.models import BenutzerRolle
        u = Benutzer(username="multi", name="Multi", aktiv=True)
        u.set_password("pw")
        u.rollen.append(BenutzerRolle(rolle="organisator"))
        u.rollen.append(BenutzerRolle(rolle="punkterichter"))
        db.session.add(u)
        db.session.commit()

    # Login mit mehreren Rollen -> Auswahlseite
    r = client.post("/anmelden", data={"username": "multi", "passwort": "pw"},
                    follow_redirects=True)
    assert "Rolle wählen".encode() in r.data

    # Aktive Rolle: Punkterichter -> nur dessen Karte
    r = client.post("/rolle-setzen", data={"rolle": "punkterichter"},
                    follow_redirects=True)
    assert "Ergebnisse erfassen".encode() in r.data
    assert "Stationen verwalten".encode() not in r.data      # keine Organisator-Karte

    # Wechsel auf Organisator -> dessen Karten, keine Erfassen-Karte
    r = client.post("/rolle-setzen", data={"rolle": "organisator"},
                    follow_redirects=True)
    assert "Stationen verwalten".encode() in r.data
    assert "Ergebnisse erfassen".encode() not in r.data

    # Fremde Rolle lässt sich nicht setzen
    client.post("/rolle-setzen", data={"rolle": "administrator"})
    r = client.get("/")
    assert "🛡️ Verwaltung".encode() not in r.data


def test_dashboard_oeffentlich_ohne_login(client):
    r = client.get("/")
    assert "Deine Rollen".encode() not in r.data
    assert "Anmelden".encode() in r.data


def test_benutzerverwaltung_nur_admin(client):
    # Punkterichter kommt nicht in die Benutzerverwaltung
    _login(client, "punkt", "pw")
    antwort = client.get("/benutzer/", follow_redirects=True)
    assert "Benutzer der Organisator".encode() not in antwort.data
    # Admin schon
    client.post("/abmelden")
    _login(client, "admin", "admin")
    antwort = client.get("/benutzer/")
    assert antwort.status_code == 200
    assert "Organisator-Mannschaft".encode() in antwort.data
