import pytest

from zeitmessung_desktop import datenbank
from zeitmessung_desktop.lauf_import_worker import LaufImportWorker, lauf_zu_nutzlast


@pytest.fixture
def db(tmp_path):
    return datenbank.verbinden(str(tmp_path / "test.sqlite"))


def test_lauf_zu_nutzlast_baut_erwartetes_format(db):
    lauf_id = datenbank.lokalen_lauf_starten(
        db, bezeichnung="Test", team_nummern={1: "12", 2: "7"},
        aktiviert_um="2026-08-17T10:00:00+00:00")
    lauf = datenbank.aktiver_lokaler_lauf(db)
    bahnen = datenbank.lokale_bahnen(db, lauf_id)

    nutzlast = lauf_zu_nutzlast(lauf, bahnen)
    assert nutzlast["server_lauf_id"] is None
    assert nutzlast["bezeichnung"] == "Test"
    assert len(nutzlast["bahnen"]) == 2
    bahn1 = next(b for b in nutzlast["bahnen"] if b["bahn_nr"] == 1)
    assert bahn1["team_nummer"] == "12"
    assert bahn1["zeit_laeufer1"] is None


def test_worker_markiert_unvollstaendigen_lauf_nicht_als_gesendet(db, monkeypatch):
    lauf_id = datenbank.lokalen_lauf_starten(
        db, bezeichnung="Test", team_nummern={1: "12"},
        aktiviert_um="2026-08-17T10:00:00+00:00")

    class GefaelschteAntwort:
        status_code = 200
        def json(self): return {"server_lauf_id": 99}

    monkeypatch.setattr(
        "zeitmessung_desktop.lauf_import_worker.requests.post",
        lambda *a, **kw: GefaelschteAntwort(),
    )

    worker = LaufImportWorker(db, "http://server/api/zeitmessung/event", "key", 999)
    worker._zyklus_durchfuehren()

    # Unvollstaendig (keine Zeiten gesetzt) -> bleibt 'ausstehend', aber
    # server_lauf_id wird schon vermerkt fuer den naechsten (idempotenten) Versuch
    laeufe = datenbank.offene_lokale_laeufe(db)
    assert len(laeufe) == 1
    assert laeufe[0]["server_lauf_id"] == 99


def test_worker_markiert_vollstaendigen_lauf_als_gesendet(db, monkeypatch):
    lauf_id = datenbank.lokalen_lauf_starten(
        db, bezeichnung="Test", team_nummern={1: "12"},
        aktiviert_um="2026-08-17T10:00:00+00:00")
    bahn = datenbank.lokale_bahnen(db, lauf_id)[0]
    datenbank.lokale_bahn_zeiten_setzen(db, bahn["id"], [1.0, 2.0, 3.0, 4.0])

    class GefaelschteAntwort:
        status_code = 200
        def json(self): return {"server_lauf_id": 100}

    monkeypatch.setattr(
        "zeitmessung_desktop.lauf_import_worker.requests.post",
        lambda *a, **kw: GefaelschteAntwort(),
    )

    worker = LaufImportWorker(db, "http://server/api/zeitmessung/event", "key", 999)
    worker._zyklus_durchfuehren()

    assert datenbank.offene_lokale_laeufe(db) == []


def test_worker_bei_netzfehler_bleibt_ausstehend(db, monkeypatch):
    import requests
    datenbank.lokalen_lauf_starten(
        db, bezeichnung="Test", team_nummern={1: "12"},
        aktiviert_um="2026-08-17T10:00:00+00:00")

    def kaputt(*a, **kw):
        raise requests.RequestException("kein Netz")

    monkeypatch.setattr("zeitmessung_desktop.lauf_import_worker.requests.post", kaputt)

    worker = LaufImportWorker(db, "http://server/api/zeitmessung/event", "key", 999)
    worker._zyklus_durchfuehren()   # darf nicht werfen

    assert len(datenbank.offene_lokale_laeufe(db)) == 1
