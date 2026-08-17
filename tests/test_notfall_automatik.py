"""Tests für die automatische Zuordnung von Zeitmessung-Ereignissen zu
einem aktivierten NotfallLauf (siehe app/blueprints/zeitmessung.py:
_automatische_zuordnung_pruefen)."""
import pytest

from app import create_app
from app.models import db, Benutzer, BenutzerRolle, Team, NotfallLauf, NotfallBahn

API_KEY = "test-key"


@pytest.fixture
def app(tmp_path):
    dbdatei = tmp_path / "wettbewerb.sqlite"
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{dbdatei}",
        "ADMIN_STARTPASSWORT": "admin",
        "ZEITMESSUNG_API_KEY": API_KEY,
    })
    yield app


@pytest.fixture
def client(app):
    return app.test_client()


def _organisator_anlegen_und_anmelden(app, client, username="orga"):
    with app.app_context():
        orga = Benutzer(username=username, aktiv=True)
        orga.set_password("pw")
        orga.rollen.append(BenutzerRolle(rolle="organisator"))
        db.session.add(orga)
        db.session.commit()
    client.post("/anmelden", data={"username": username, "passwort": "pw"})


def _lauf_mit_team_auf_bahn1(app) -> int:
    with app.app_context():
        team = Team(name="Löschgruppe Nord")
        db.session.add(team)
        db.session.flush()
        lauf = NotfallLauf(bezeichnung="Testlauf")
        lauf.bahnen.append(NotfallBahn(bahn_nr=1, team_id=team.id))
        for bahn_nr in range(2, 5):
            lauf.bahnen.append(NotfallBahn(bahn_nr=bahn_nr))
        db.session.add(lauf)
        db.session.commit()
        return lauf.id


def _kontakt_senden(client, bahn=1):
    return client.post("/api/zeitmessung/event",
                       json={"geraet_id": "mega-laptop1", "bahn": bahn, "kontakt": "kontakt"},
                       headers={"X-API-Key": API_KEY})


def test_events_ohne_aktiven_lauf_werden_nicht_zugeordnet(client, app):
    lauf_id = _lauf_mit_team_auf_bahn1(app)
    for _ in range(5):
        _kontakt_senden(client)
    with app.app_context():
        bahn = NotfallBahn.query.filter_by(lauf_id=lauf_id, bahn_nr=1).one()
        assert bahn.zeit_laeufer1 is None


def test_aktivieren_erfordert_rolle(client, app):
    lauf_id = _lauf_mit_team_auf_bahn1(app)
    r = client.post(f"/notfall/{lauf_id}/aktivieren", follow_redirects=True)
    assert "rolle".encode() in r.data.lower() or "anmelden".encode() in r.data.lower()
    with app.app_context():
        assert not NotfallLauf.query.get(lauf_id).aktiv


def test_fuenf_events_fuellen_zeiten_automatisch_aus(client, app):
    lauf_id = _lauf_mit_team_auf_bahn1(app)
    _organisator_anlegen_und_anmelden(app, client)

    r = client.post(f"/notfall/{lauf_id}/aktivieren", follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        assert NotfallLauf.query.get(lauf_id).aktiv

    for _ in range(5):
        r = _kontakt_senden(client)
        assert r.status_code == 201

    with app.app_context():
        bahn = NotfallBahn.query.filter_by(lauf_id=lauf_id, bahn_nr=1).one()
        assert bahn.zeit_laeufer1 is not None
        assert bahn.zeit_laeufer2 is not None
        assert bahn.zeit_laeufer3 is not None
        assert bahn.zeit_laeufer4 is not None
        assert bahn.gesamtzeit is not None
        assert bahn.gesamtzeit >= 0


def test_unbelegte_bahn_wird_nicht_zugeordnet(client, app):
    """Bahn 2 hat in _lauf_mit_team_auf_bahn1 kein Team - Events dafür
    dürfen keine Notfall-Bahn befüllen."""
    lauf_id = _lauf_mit_team_auf_bahn1(app)
    _organisator_anlegen_und_anmelden(app, client)
    client.post(f"/notfall/{lauf_id}/aktivieren")

    for _ in range(5):
        _kontakt_senden(client, bahn=2)

    with app.app_context():
        bahn = NotfallBahn.query.filter_by(lauf_id=lauf_id, bahn_nr=2).one()
        assert bahn.zeit_laeufer1 is None


def test_bereits_vollstaendige_bahn_wird_nicht_ueberschrieben(client, app):
    """Schon manuell eingetragene Zeiten (zeit_laeufer4 gesetzt) dürfen von
    weiteren eintreffenden Ereignissen nicht überschrieben werden."""
    lauf_id = _lauf_mit_team_auf_bahn1(app)
    _organisator_anlegen_und_anmelden(app, client)
    client.post(f"/notfall/{lauf_id}/aktivieren")

    with app.app_context():
        bahn = NotfallBahn.query.filter_by(lauf_id=lauf_id, bahn_nr=1).one()
        bahn.zeit_laeufer1 = 1.0
        bahn.zeit_laeufer2 = 2.0
        bahn.zeit_laeufer3 = 3.0
        bahn.zeit_laeufer4 = 4.0
        db.session.commit()

    for _ in range(5):
        _kontakt_senden(client)

    with app.app_context():
        bahn = NotfallBahn.query.filter_by(lauf_id=lauf_id, bahn_nr=1).one()
        assert bahn.zeit_laeufer1 == 1.0
        assert bahn.zeit_laeufer4 == 4.0


def test_nur_ein_lauf_gleichzeitig_aktiv(client, app):
    lauf1_id = _lauf_mit_team_auf_bahn1(app)
    lauf2_id = _lauf_mit_team_auf_bahn1(app)
    _organisator_anlegen_und_anmelden(app, client)

    client.post(f"/notfall/{lauf1_id}/aktivieren")
    client.post(f"/notfall/{lauf2_id}/aktivieren")

    with app.app_context():
        assert not NotfallLauf.query.get(lauf1_id).aktiv
        assert NotfallLauf.query.get(lauf2_id).aktiv


def test_deaktivieren_stoppt_automatische_zuordnung(client, app):
    lauf_id = _lauf_mit_team_auf_bahn1(app)
    _organisator_anlegen_und_anmelden(app, client)
    client.post(f"/notfall/{lauf_id}/aktivieren")
    client.post(f"/notfall/{lauf_id}/deaktivieren")

    for _ in range(5):
        _kontakt_senden(client)

    with app.app_context():
        bahn = NotfallBahn.query.filter_by(lauf_id=lauf_id, bahn_nr=1).one()
        assert bahn.zeit_laeufer1 is None
