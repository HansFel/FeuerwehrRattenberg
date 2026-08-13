"""Tests für den ESP32-Zeitmessung-Endpoint."""
import pytest

from app import create_app
from app.models import db, Zeitereignis

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
