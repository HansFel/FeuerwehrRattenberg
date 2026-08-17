import pytest

from zeitmessung_desktop import datenbank


@pytest.fixture
def db(tmp_path):
    return datenbank.verbinden(str(tmp_path / "test.sqlite"))


def test_ereignis_hinzufuegen_und_lesen(db):
    datenbank.ereignis_hinzufuegen(db, bahn=2, geraet_millis=1000,
                                   empfangen_um="2026-08-16T10:00:00", client_event_id="a1")
    zeilen = datenbank.letzte_ereignisse(db)
    assert len(zeilen) == 1
    assert zeilen[0]["bahn"] == 2
    assert zeilen[0]["sync_status"] == "ausstehend"


def test_ausstehende_ereignisse_und_markieren(db):
    id1 = datenbank.ereignis_hinzufuegen(db, bahn=1, geraet_millis=1, empfangen_um="t1",
                                         client_event_id="a")
    datenbank.ereignis_hinzufuegen(db, bahn=1, geraet_millis=2, empfangen_um="t2",
                                   client_event_id="b")
    assert datenbank.anzahl_ausstehend(db) == 2

    datenbank.als_gesendet_markieren(db, id1, server_id=42, versucht_um="t3")
    assert datenbank.anzahl_ausstehend(db) == 1
    ausstehend = datenbank.ausstehende_ereignisse(db)
    assert len(ausstehend) == 1
    assert ausstehend[0]["client_event_id"] == "b"


def test_versuch_vermerken_aendert_status_nicht(db):
    id1 = datenbank.ereignis_hinzufuegen(db, bahn=1, geraet_millis=1, empfangen_um="t1",
                                         client_event_id="a")
    datenbank.versuch_vermerken(db, id1, "t2")
    assert datenbank.anzahl_ausstehend(db) == 1
    zeile = datenbank.letzte_ereignisse(db)[0]
    assert zeile["sync_versucht_um"] == "t2"
    assert zeile["sync_status"] == "ausstehend"


def test_alle_loeschen(db):
    datenbank.ereignis_hinzufuegen(db, bahn=1, geraet_millis=1, empfangen_um="t1",
                                   client_event_id="a")
    datenbank.ereignis_hinzufuegen(db, bahn=2, geraet_millis=2, empfangen_um="t2",
                                   client_event_id="b")
    anzahl = datenbank.alle_loeschen(db)
    assert anzahl == 2
    assert datenbank.letzte_ereignisse(db) == []
    assert datenbank.anzahl_ausstehend(db) == 0


def test_lokalen_lauf_starten_und_lesen(db):
    lauf_id = datenbank.lokalen_lauf_starten(
        db, bezeichnung="Test", team_nummern={1: "12", 2: "7"},
        aktiviert_um="2026-08-17T10:00:00+00:00")
    lauf = datenbank.aktiver_lokaler_lauf(db)
    assert lauf["id"] == lauf_id
    assert lauf["bezeichnung"] == "Test"
    assert lauf["aktiv"] == 1

    bahnen = datenbank.lokale_bahnen(db, lauf_id)
    assert len(bahnen) == 2
    assert {b["bahn_nr"] for b in bahnen} == {1, 2}
    assert next(b for b in bahnen if b["bahn_nr"] == 1)["team_nummer"] == "12"


def test_neuer_lokaler_lauf_deaktiviert_alten(db):
    erster_id = datenbank.lokalen_lauf_starten(
        db, bezeichnung="Erster", team_nummern={1: "1"}, aktiviert_um="2026-08-17T10:00:00+00:00")
    zweiter_id = datenbank.lokalen_lauf_starten(
        db, bezeichnung="Zweiter", team_nummern={1: "2"}, aktiviert_um="2026-08-17T10:05:00+00:00")

    aktiv = datenbank.aktiver_lokaler_lauf(db)
    assert aktiv["id"] == zweiter_id
    assert aktiv["id"] != erster_id


def test_lokale_bahn_zeiten_setzen(db):
    lauf_id = datenbank.lokalen_lauf_starten(
        db, bezeichnung="Test", team_nummern={1: "1"}, aktiviert_um="2026-08-17T10:00:00+00:00")
    bahn = datenbank.lokale_bahnen(db, lauf_id)[0]

    datenbank.lokale_bahn_zeiten_setzen(db, bahn["id"], [10.1, 11.2, 9.9, 12.0])

    aktualisiert = datenbank.lokale_bahnen(db, lauf_id)[0]
    assert aktualisiert["zeit_laeufer1"] == pytest.approx(10.1)
    assert aktualisiert["zeit_laeufer4"] == pytest.approx(12.0)


def test_offene_lokale_laeufe_und_als_gesendet_markieren(db):
    lauf_id = datenbank.lokalen_lauf_starten(
        db, bezeichnung="Test", team_nummern={1: "1"}, aktiviert_um="2026-08-17T10:00:00+00:00")
    assert len(datenbank.offene_lokale_laeufe(db)) == 1

    datenbank.lokalen_lauf_als_gesendet_markieren(db, lauf_id, server_lauf_id=42,
                                                  versucht_um="2026-08-17T10:10:00+00:00")
    assert datenbank.offene_lokale_laeufe(db) == []


def test_client_event_id_muss_eindeutig_sein(db):
    datenbank.ereignis_hinzufuegen(db, bahn=1, geraet_millis=1, empfangen_um="t1",
                                   client_event_id="doppelt")
    with pytest.raises(Exception):
        datenbank.ereignis_hinzufuegen(db, bahn=1, geraet_millis=2, empfangen_um="t2",
                                       client_event_id="doppelt")
