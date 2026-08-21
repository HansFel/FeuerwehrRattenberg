"""Tests für den ESP32-Zeitmessung-Endpoint."""
import pytest

from app import create_app
from app.blueprints import zeitmessung
from app.models import db, Zeitereignis, ZeitmessungAbonnent

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


class _SofortigerThread:
    """Ersetzt threading.Thread in Tests: führt das Ziel sofort synchron aus,
    statt einen echten Hintergrund-Thread zu starten - macht die
    Fire-and-forget-Weiterleitung in Tests deterministisch prüfbar."""

    def __init__(self, target, args=(), kwargs=None, daemon=None):
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}

    def start(self):
        self._target(*self._args, **self._kwargs)


def test_event_ohne_api_key_abgelehnt(client):
    r = client.post("/api/zeitmessung/event",
                    json={"geraet_id": "esp32-1", "bahn": 1, "kontakt": "start"})
    assert r.status_code == 401


def test_event_mit_falschem_api_key_abgelehnt(client):
    r = client.post("/api/zeitmessung/event",
                    json={"geraet_id": "esp32-1", "bahn": 1, "kontakt": "start"},
                    headers={"X-API-Key": "falsch"})
    assert r.status_code == 401


def test_event_wird_gespeichert(client, app):
    r = client.post("/api/zeitmessung/event",
                    json={"geraet_id": "esp32-1", "bahn": 2, "kontakt": "ziel",
                          "geraet_millis": 12345, "geraet_zeit_iso": "2026-08-12T10:00:00"},
                    headers={"X-API-Key": API_KEY})
    assert r.status_code == 201
    with app.app_context():
        e = Zeitereignis.query.one()
        assert e.geraet_id == "esp32-1"
        assert e.bahn == 2
        assert e.kontakt == "ziel"
        assert e.geraet_millis == 12345


@pytest.mark.parametrize("nutzlast,erwarteter_status", [
    ({"geraet_id": "", "bahn": 1, "kontakt": "start"}, 400),
    ({"geraet_id": "esp32-1", "bahn": 0, "kontakt": "start"}, 400),
    ({"geraet_id": "esp32-1", "bahn": 5, "kontakt": "start"}, 400),
    ({"geraet_id": "esp32-1", "bahn": 1, "kontakt": "unsinn"}, 400),
])
def test_event_validierung(client, nutzlast, erwarteter_status):
    r = client.post("/api/zeitmessung/event", json=nutzlast,
                    headers={"X-API-Key": API_KEY})
    assert r.status_code == erwarteter_status


def test_liste_erfordert_rolle(client):
    r = client.get("/zeitmessung/", follow_redirects=True)
    assert r.status_code == 200
    assert b"Bitte zuerst anmelden" in r.data


def test_event_mit_neuem_kontakttyp_wird_akzeptiert(client, app):
    """Aktuelle Hardware hat nur noch 1 Kontakt pro Bahn und meldet
    kontakt='kontakt' statt 'start'/'ziel'."""
    r = client.post("/api/zeitmessung/event",
                    json={"geraet_id": "esp32-1", "bahn": 3, "kontakt": "kontakt",
                          "geraet_millis": 999},
                    headers={"X-API-Key": API_KEY})
    assert r.status_code == 201
    with app.app_context():
        e = Zeitereignis.query.one()
        assert e.kontakt == "kontakt"


def test_liste_zeigt_laufende_nummer_je_bahn(client, app):
    """1.-4. Auslösung einer Bahn = Läufer 1-4 Start, 5. = Ziel, danach
    beginnt die Zählung für den nächsten Lauf wieder bei 1."""
    with app.app_context():
        from app.models import Benutzer, BenutzerRolle
        orga = Benutzer(username="orga", aktiv=True)
        orga.set_password("pw")
        orga.rollen.append(BenutzerRolle(rolle="organisator"))
        db.session.add(orga)
        db.session.commit()

    for _ in range(6):
        client.post("/api/zeitmessung/event",
                    json={"geraet_id": "esp32-1", "bahn": 1, "kontakt": "kontakt"},
                    headers={"X-API-Key": API_KEY})

    client.post("/anmelden", data={"username": "orga", "passwort": "pw"})
    r = client.get("/zeitmessung/")
    assert r.status_code == 200
    assert "Läufer 1".encode() in r.data
    assert "Läufer 4".encode() in r.data
    assert "(Ziel)".encode() in r.data


def test_liste_zeigt_abstand_zur_vorherigen_ausloesung(client, app):
    from datetime import datetime, timedelta, timezone
    from app.models import Benutzer, BenutzerRolle

    with app.app_context():
        orga = Benutzer(username="orga3", aktiv=True)
        orga.set_password("pw")
        orga.rollen.append(BenutzerRolle(rolle="organisator"))
        db.session.add(orga)
        basis = datetime(2026, 8, 22, 10, 0, 0)
        db.session.add(Zeitereignis(geraet_id="esp32-1", bahn=1, kontakt="kontakt",
                                    server_empfangen=basis))
        db.session.add(Zeitereignis(geraet_id="esp32-1", bahn=1, kontakt="kontakt",
                                    server_empfangen=basis + timedelta(seconds=12.5)))
        db.session.commit()

    client.post("/anmelden", data={"username": "orga3", "passwort": "pw"})
    r = client.get("/zeitmessung/")
    assert r.status_code == 200
    assert "12.50 s".encode() in r.data


def test_ereignisse_loeschen_nur_organisator(client, app):
    with app.app_context():
        from app.models import Benutzer, BenutzerRolle
        orga = Benutzer(username="orga2", aktiv=True)
        orga.set_password("pw")
        orga.rollen.append(BenutzerRolle(rolle="organisator"))
        db.session.add(orga)
        richter = Benutzer(username="richter", aktiv=True)
        richter.set_password("pw")
        richter.rollen.append(BenutzerRolle(rolle="startrichter"))
        db.session.add(richter)
        db.session.commit()

    client.post("/api/zeitmessung/event",
               json={"geraet_id": "esp32-1", "bahn": 1, "kontakt": "kontakt"},
               headers={"X-API-Key": API_KEY})

    # Startrichter darf nicht löschen
    client.post("/anmelden", data={"username": "richter", "passwort": "pw"})
    r = client.post("/zeitmessung/loeschen", follow_redirects=True)
    assert "rolle".encode() in r.data.lower()
    with app.app_context():
        assert Zeitereignis.query.count() == 1
    client.post("/abmelden")

    # Organisator darf
    client.post("/anmelden", data={"username": "orga2", "passwort": "pw"})
    r = client.post("/zeitmessung/loeschen", follow_redirects=True)
    assert r.status_code == 200
    assert "gelöscht".encode() in r.data
    with app.app_context():
        assert Zeitereignis.query.count() == 0


def test_event_mit_client_event_id_wird_gespeichert(client, app):
    r = client.post("/api/zeitmessung/event",
                    json={"geraet_id": "mega-laptop1", "bahn": 1, "kontakt": "kontakt",
                          "client_event_id": "abc-123"},
                    headers={"X-API-Key": API_KEY})
    assert r.status_code == 201
    with app.app_context():
        e = Zeitereignis.query.one()
        assert e.client_event_id == "abc-123"


def test_event_mit_gleicher_client_event_id_wird_nicht_dupliziert(client, app):
    """Simuliert einen Sync-Retry der Desktop-App: dieselbe client_event_id
    zweimal gesendet darf nur EINE Zeile anlegen."""
    nutzlast = {"geraet_id": "mega-laptop1", "bahn": 1, "kontakt": "kontakt",
                "client_event_id": "retry-1"}
    r1 = client.post("/api/zeitmessung/event", json=nutzlast, headers={"X-API-Key": API_KEY})
    r2 = client.post("/api/zeitmessung/event", json=nutzlast, headers={"X-API-Key": API_KEY})
    assert r1.status_code == 201
    assert r2.status_code == 200
    assert r2.get_json()["bereits_vorhanden"] is True
    with app.app_context():
        assert Zeitereignis.query.count() == 1


def test_abonnieren_ohne_api_key_abgelehnt(client):
    r = client.post("/api/zeitmessung/abonnieren",
                    json={"ziel_url": "http://app-test1:8000/api/zeitmessung/event",
                          "api_key": "irgendwas"})
    assert r.status_code == 401


@pytest.mark.parametrize("nutzlast,erwarteter_status", [
    ({"ziel_url": "", "api_key": "x"}, 400),
    ({"ziel_url": "keine-url", "api_key": "x"}, 400),
    ({"ziel_url": "http://app-test1:8000/api/zeitmessung/event", "api_key": ""}, 400),
])
def test_abonnieren_validierung(client, nutzlast, erwarteter_status):
    r = client.post("/api/zeitmessung/abonnieren", json=nutzlast,
                    headers={"X-API-Key": API_KEY})
    assert r.status_code == erwarteter_status


def test_abonnieren_erfolgreich(client, app):
    r = client.post("/api/zeitmessung/abonnieren",
                    json={"ziel_url": "http://app-test1:8000/api/zeitmessung/event",
                          "api_key": "ziel-key"},
                    headers={"X-API-Key": API_KEY})
    assert r.status_code == 200
    with app.app_context():
        abonnent = ZeitmessungAbonnent.query.filter_by(
            ziel_url="http://app-test1:8000/api/zeitmessung/event").one()
        assert abonnent.api_key == "ziel-key"


def test_abonnieren_erneuert_bestehenden_eintrag_statt_duplikat(client, app):
    """Wiederholtes Anmelden derselben ziel_url (Selbst-Anmeldung alle 60s)
    darf keine Duplikate anlegen, sondern nur die Ablaufzeit verlängern."""
    for _ in range(3):
        client.post("/api/zeitmessung/abonnieren",
                    json={"ziel_url": "http://app-test1:8000/api/zeitmessung/event",
                          "api_key": "ziel-key"},
                    headers={"X-API-Key": API_KEY})
    with app.app_context():
        assert ZeitmessungAbonnent.query.count() == 1


def test_event_wird_an_abonnenten_weitergeleitet(client, monkeypatch):
    monkeypatch.setattr(zeitmessung.threading, "Thread", _SofortigerThread)
    aufrufe = []

    class GefaelschteAntwort:
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def gefaelschtes_urlopen(anfrage, timeout=None):
        aufrufe.append({
            "url": anfrage.full_url,
            "api_key": anfrage.get_header("X-api-key"),
            "body": anfrage.data,
            "weitergeleitet_markiert": anfrage.get_header("X-weitergeleitet"),
        })
        return GefaelschteAntwort()

    monkeypatch.setattr(zeitmessung.urllib.request, "urlopen", gefaelschtes_urlopen)

    client.post("/api/zeitmessung/abonnieren",
               json={"ziel_url": "http://app-test1:8000/api/zeitmessung/event",
                     "api_key": "ziel-key"},
               headers={"X-API-Key": API_KEY})

    client.post("/api/zeitmessung/event",
               json={"geraet_id": "esp32-1", "bahn": 1, "kontakt": "kontakt",
                     "geraet_millis": 42},
               headers={"X-API-Key": API_KEY})

    assert len(aufrufe) == 1
    assert aufrufe[0]["url"] == "http://app-test1:8000/api/zeitmessung/event"
    assert aufrufe[0]["api_key"] == "ziel-key"
    assert b'"bahn": 1' in aufrufe[0]["body"]
    assert aufrufe[0]["weitergeleitet_markiert"] == "1"


def test_weitergeleitetes_ereignis_wird_nicht_erneut_weitergeleitet(client, monkeypatch):
    """Verhindert Endlosschleifen bei fehlerhafter Abonnenten-Verkettung
    (z.B. eine versehentliche Selbst-Anmeldung, wie real passiert): ein
    bereits weitergeleitetes Ereignis (X-Weitergeleitet-Header) darf NICHT
    noch einmal weitergereicht werden, egal wie viele Abonnenten
    registriert sind."""
    monkeypatch.setattr(zeitmessung.threading, "Thread", _SofortigerThread)

    def urlopen_darf_nicht_aufgerufen_werden(*a, **kw):
        raise AssertionError("ein weitergeleitetes Ereignis darf nicht erneut weitergeleitet werden")

    monkeypatch.setattr(zeitmessung.urllib.request, "urlopen", urlopen_darf_nicht_aufgerufen_werden)

    client.post("/api/zeitmessung/abonnieren",
               json={"ziel_url": "http://app-test1:8000/api/zeitmessung/event",
                     "api_key": "ziel-key"},
               headers={"X-API-Key": API_KEY})

    r = client.post("/api/zeitmessung/event",
                    json={"geraet_id": "esp32-1", "bahn": 1, "kontakt": "kontakt"},
                    headers={"X-API-Key": API_KEY, "X-Weitergeleitet": "1"})
    assert r.status_code == 201


def test_event_ohne_abonnenten_keine_weiterleitung(client, monkeypatch):
    monkeypatch.setattr(zeitmessung.threading, "Thread", _SofortigerThread)

    def urlopen_darf_nicht_aufgerufen_werden(*a, **kw):
        raise AssertionError("urlopen sollte ohne Abonnenten nicht aufgerufen werden")

    monkeypatch.setattr(zeitmessung.urllib.request, "urlopen", urlopen_darf_nicht_aufgerufen_werden)

    r = client.post("/api/zeitmessung/event",
                    json={"geraet_id": "esp32-1", "bahn": 1, "kontakt": "kontakt"},
                    headers={"X-API-Key": API_KEY})
    assert r.status_code == 201


def test_abgelaufenes_abonnement_wird_nicht_mehr_beliefert(client, app, monkeypatch):
    from datetime import datetime, timedelta, timezone
    monkeypatch.setattr(zeitmessung.threading, "Thread", _SofortigerThread)
    with app.app_context():
        db.session.add(ZeitmessungAbonnent(
            ziel_url="http://abgelaufen:8000/api/zeitmessung/event", api_key="x",
            ablauf=datetime.now(timezone.utc) - timedelta(seconds=1)))
        db.session.commit()

    def urlopen_darf_nicht_aufgerufen_werden(*a, **kw):
        raise AssertionError("abgelaufenes Abonnement darf nicht beliefert werden")

    monkeypatch.setattr(zeitmessung.urllib.request, "urlopen", urlopen_darf_nicht_aufgerufen_werden)

    r = client.post("/api/zeitmessung/event",
                    json={"geraet_id": "esp32-1", "bahn": 1, "kontakt": "kontakt"},
                    headers={"X-API-Key": API_KEY})
    assert r.status_code == 201
