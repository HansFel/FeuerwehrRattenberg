"""Tests für PrefixMiddleware: dieselbe Instanz muss sowohl hinter Traefik
(mit Pfad-Präfix per 'X-Script-Name'-Header) als auch direkt im LAN (ohne
Header, z.B. über die zusätzlichen Ports in docker-compose.*.yml) korrekt
funktionieren - siehe app/__init__.py."""
import pytest

from app import create_app


@pytest.fixture
def app(tmp_path):
    dbdatei = tmp_path / "wettbewerb.sqlite"
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{dbdatei}",
        "ADMIN_STARTPASSWORT": "admin",
    })
    yield app


@pytest.fixture
def client(app):
    return app.test_client()


def test_ohne_header_kein_praefix_in_links(client):
    """Direkter Zugriff (z.B. über den LAN-Port ohne Traefik davor) darf
    KEINEN Präfix in generierten Links erzeugen, sonst zeigen alle Links
    ins Leere (echter Bug, der test1/test2/generalprobe beim direkten
    Port-Zugriff betroffen hat)."""
    r = client.get("/")
    assert r.status_code == 200
    assert b'href="/test1/' not in r.data
    assert b'href="/static/css/style.css"' in r.data


def test_mit_header_wird_praefix_angewendet(client):
    """Traefik schickt den 'X-Script-Name'-Header für Pfad-Präfix-Routen -
    dann müssen generierte Links den Präfix enthalten."""
    r = client.get("/", headers={"X-Script-Name": "/test1"})
    assert r.status_code == 200
    assert b'href="/test1/static/css/style.css"' in r.data
