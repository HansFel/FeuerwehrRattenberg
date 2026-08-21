"""Tests für Rolle und Live-Dashboard der Moderation."""
import pytest

from app import create_app
from app.models import (db, Benutzer, BenutzerRolle, Disziplin,
                        ModeratorStatus, Nachricht, Startplatz, Team)


@pytest.fixture
def app():
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "ADMIN_STARTPASSWORT": "admin",
    })
    with app.app_context():
        moderator = Benutzer(username="mod", name="Maria", aktiv=True)
        moderator.set_password("pw")
        moderator.rollen.append(BenutzerRolle(rolle="moderator"))
        organisator = Benutzer(username="orga", name="Olga", aktiv=True)
        organisator.set_password("pw")
        organisator.rollen.append(BenutzerRolle(rolle="organisator"))
        fremd = Benutzer(username="kellner", name="Karl", aktiv=True)
        fremd.set_password("pw")
        fremd.rollen.append(BenutzerRolle(rolle="kellner"))

        disziplin = Disziplin(name="Siloplanen-Race", reihenfolge=1)
        team1 = Team(name="Team Rattenberg", wehr="Rattenberg",
                     motto="Wasser marsch!", lieblingslied="Highway to Hell")
        team2 = Team(name="Team Brixlegg", wehr="Brixlegg")
        db.session.add_all([moderator, organisator, fremd,
                            disziplin, team1, team2])
        db.session.flush()
        db.session.add_all([
            Startplatz(team_id=team1.id, disziplin_id=disziplin.id,
                       startnummer=1, heat="Vorrunde 1"),
            Startplatz(team_id=team2.id, disziplin_id=disziplin.id,
                       startnummer=2, heat="Vorrunde 1"),
        ])
        db.session.commit()
        yield app


@pytest.fixture
def client(app):
    return app.test_client()


def _login(client, username):
    return client.post("/anmelden", data={"username": username,
                                           "passwort": "pw"})


def test_moderator_hat_eigenes_dashboard(client):
    _login(client, "mod")
    response = client.get("/moderator/")
    assert response.status_code == 200
    assert "Moderator-Dashboard".encode() in response.data
    assert "Noch kein aktueller Lauf".encode() in response.data


def test_fremde_rolle_darf_dashboard_nicht_oeffnen(client):
    _login(client, "kellner")
    response = client.get("/moderator/", follow_redirects=True)
    assert "Dafür fehlt dir die nötige Rolle".encode() in response.data


def test_organisator_waehlt_lauf_und_pflegt_informationen(client, app):
    with app.app_context():
        disziplin = Disziplin.query.filter_by(name="Siloplanen-Race").one()
        lauf = f"{disziplin.id}|Vorrunde 1"

    _login(client, "orga")
    response = client.post("/moderator/status", data={
        "lauf": lauf,
        "publikumsinfo": "Als Nächstes folgt das Finale.",
        "sponsoren": "Firma A\nFirma B",
    }, follow_redirects=True)

    assert response.status_code == 200
    assert "Team Rattenberg".encode() in response.data
    assert "Team Brixlegg".encode() in response.data
    assert "Firma A".encode() in response.data
    with app.app_context():
        status = db.session.get(ModeratorStatus, 1)
        assert status.heat == "Vorrunde 1"
        assert status.aktualisiert_von == "orga"


def test_organisator_sendet_nachricht_an_moderator(client, app):
    _login(client, "orga")
    client.post("/moderator/nachricht", data={
        "text": "Bitte jetzt Firma A erwähnen."
    })
    client.post("/abmelden")
    _login(client, "mod")
    response = client.get("/moderator/")

    assert "Bitte jetzt Firma A erwähnen.".encode() in response.data
    with app.app_context():
        nachricht = Nachricht.query.one()
        assert nachricht.ziel_rolle == "moderator"
        assert nachricht.absender == "orga"


def test_allgemeine_nachricht_erscheint_nicht_im_moderator_bereich(client, app):
    with app.app_context():
        db.session.add(Nachricht(text="Allgemeine Admin-Nachricht",
                                 absender="admin"))
        db.session.commit()
    _login(client, "mod")
    response = client.get("/moderator/")
    assert "Allgemeine Admin-Nachricht".encode() not in response.data


def test_kellner_kann_keine_moderator_nachricht_senden(client, app):
    _login(client, "kellner")
    client.post("/moderator/nachricht", data={"text": "Nicht erlaubt"})
    with app.app_context():
        assert Nachricht.query.count() == 0


def test_dashboard_zeigt_motto_und_lieblingslied(client, app):
    """Motto/Lieblingslied eines Teams sollen bei den laufenden Bahnen im
    Moderator-Dashboard erscheinen, wenn gepflegt - fehlen sie, kein
    leerer Platzhalter (Team Brixlegg hat keine)."""
    with app.app_context():
        disziplin = Disziplin.query.filter_by(name="Siloplanen-Race").one()
        lauf = f"{disziplin.id}|Vorrunde 1"

    _login(client, "orga")
    client.post("/moderator/status", data={"lauf": lauf,
                                           "publikumsinfo": "",
                                           "sponsoren": ""})
    r = client.get("/moderator/")
    assert "Wasser marsch!".encode() in r.data
    assert "Highway to Hell".encode() in r.data


def test_live_fragment_zeigt_neue_zeiten_ohne_seiten_reload(client, app):
    """Der /moderator/live-fragment-Endpoint (per JS-Polling eingebettet)
    liefert die aktuelle Rangliste, sobald neue Zeiten erfasst sind - ohne
    dass die Hauptseite neu geladen werden muss."""
    with app.app_context():
        disziplin = Disziplin.query.filter_by(name="Siloplanen-Race").one()
        team1 = Team.query.filter_by(name="Team Rattenberg").one()
        team2 = Team.query.filter_by(name="Team Brixlegg").one()
        lauf = f"{disziplin.id}|Vorrunde 1"

    _login(client, "orga")
    client.post("/moderator/status", data={"lauf": lauf,
                                           "publikumsinfo": "",
                                           "sponsoren": ""})

    # Zeiten werden erfasst (z.B. durch die Zeitmessung-Automatik)
    with app.app_context():
        Startplatz.query.filter_by(team_id=team1.id).update({"ergebnis_sekunden": 42.5})
        Startplatz.query.filter_by(team_id=team2.id).update({"ergebnis_sekunden": 39.1})
        db.session.commit()

    r = client.get("/moderator/live-fragment")
    assert r.status_code == 200
    daten = r.get_json()
    # Siloplanen-Race-Zwischenwertung: noch kein Ziellauf -> "vorläufig"
    assert "Siloplanen-Race".encode() in daten["rangliste_html"].encode()
    assert "vorläufig".encode() in daten["rangliste_html"].encode()
    assert "39,10 s".encode() in daten["rangliste_html"].encode()
    # Team Challenge erscheint als eigene, unabhaengige Wertung daneben
    assert "Team Challenge".encode() in daten["rangliste_html"].encode()

    # Die Hauptseite selbst zeigt beim ersten Laden dasselbe und bindet das
    # Polling auf den Fragment-Endpoint ein
    hauptseite = client.get("/moderator/")
    assert "/moderator/live-fragment".encode() in hauptseite.data


def test_dashboard_zeigt_definitive_gesamtwertung_nach_ziellauf(client, app):
    """Sobald ein Team einen Ziellauf (Platzierungslauf/Finale) absolviert
    hat, zeigt das Moderator-Dashboard die endgueltige Platzierung ohne
    "(vorläufig)" - dieselbe Berechnung wie auf /wertung/, damit am Ende
    des Bewerbs dort automatisch die Gesamtwertung steht. Team Challenge
    (Getraenke- + Fanpunkte) zeigt unabhaengig davon ihre eigene Wertung."""
    with app.app_context():
        disziplin = Disziplin.query.filter_by(name="Siloplanen-Race").one()
        team1 = Team.query.filter_by(name="Team Rattenberg").one()
        team2 = Team.query.filter_by(name="Team Brixlegg").one()
        team1.fanpunkte = 5
        Startplatz.query.filter_by(team_id=team1.id).delete()
        Startplatz.query.filter_by(team_id=team2.id).delete()
        db.session.add_all([
            Startplatz(team_id=team1.id, disziplin_id=disziplin.id,
                       startnummer=1, heat="1 Platzierungslauf Platz 1-2",
                       ergebnis_sekunden=20.0),
            Startplatz(team_id=team2.id, disziplin_id=disziplin.id,
                       startnummer=2, heat="1 Platzierungslauf Platz 1-2",
                       ergebnis_sekunden=25.0),
        ])
        db.session.commit()

    _login(client, "orga")
    r = client.get("/moderator/")
    assert "Team Rattenberg".encode() in r.data
    assert "vorläufig".encode() not in r.data
    # Team Challenge: Fanpunkte fliessen ein, unabhaengig vom Ziellauf
    assert "🏆 Team Challenge".encode() in r.data


def test_moderator_sieht_keinen_freigabe_button_organisator_schon(client, app):
    """Die aktive Rolle `moderator` sieht das Dashboard rein Lese-Ansicht:
    Live-Teams + Team-Infos, aber KEINEN Lauffreigabe-Button und nicht die
    'Anzeige als Organisator steuern'-Steuerung. Die Lauffreigabe und die
    Anzeige-Steuerung duerfen nur als aktive Rolle `organisator` erscheinen."""
    with app.app_context():
        disziplin = Disziplin.query.filter_by(name="Siloplanen-Race").one()
        lauf = f"{disziplin.id}|Vorrunde 1"

    _login(client, "orga")
    client.post("/moderator/status", data={"lauf": lauf,
                                           "publikumsinfo": "",
                                           "sponsoren": ""})
    client.post("/abmelden")

    _login(client, "mod")
    r = client.get("/moderator/")
    assert "Team Rattenberg".encode() in r.data          # Live-Teams sichtbar
    assert "Team Brixlegg".encode() in r.data
    assert "Zeitmessung für diesen Lauf freigeben".encode() not in r.data
    assert "Anzeige als Organisator steuern".encode() not in r.data

    client.post("/abmelden")
    _login(client, "orga")
    r = client.get("/moderator/")
    assert "Zeitmessung für diesen Lauf freigeben".encode() in r.data
    assert "Anzeige als Organisator steuern".encode() in r.data


def test_moderator_sieht_naechsten_lauf_unter_aktuellem_lauf(client, app):
    """Der Moderator soll den naechsten geplanten Lauf sehen (nicht nur der
    Organisator) - als reine Info direkt unter 'GERADE IM BEWERB', ohne die
    Aktions-Buttons dafuer (die bleiben Organisator vorbehalten)."""
    with app.app_context():
        disziplin = Disziplin.query.filter_by(name="Siloplanen-Race").one()
        team1 = Team.query.filter_by(name="Team Rattenberg").one()
        team2 = Team.query.filter_by(name="Team Brixlegg").one()
        db.session.add_all([
            Startplatz(team_id=team1.id, disziplin_id=disziplin.id,
                       startnummer=1, heat="Vorrunde 2"),
            Startplatz(team_id=team2.id, disziplin_id=disziplin.id,
                       startnummer=2, heat="Vorrunde 2"),
        ])
        db.session.commit()
        lauf = f"{disziplin.id}|Vorrunde 1"

    _login(client, "orga")
    client.post("/moderator/status", data={"lauf": lauf,
                                           "publikumsinfo": "",
                                           "sponsoren": ""})
    client.post("/abmelden")

    _login(client, "mod")
    r = client.get("/moderator/")
    assert "NÄCHSTER LAUF".encode() in r.data
    assert "Vorrunde 2".encode() in r.data
    assert "Als aktuellen Lauf setzen".encode() not in r.data
    assert "⏱️ Zeitmessung freigeben".encode() not in r.data

    client.post("/abmelden")
    _login(client, "orga")
    r = client.get("/moderator/")
    assert "NÄCHSTER LAUF".encode() in r.data
    assert "Vorrunde 2".encode() in r.data
    assert "Als aktuellen Lauf setzen".encode() in r.data
    assert "⏱️ Zeitmessung freigeben".encode() in r.data
