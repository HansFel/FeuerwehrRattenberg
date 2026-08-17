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


def test_client_event_id_muss_eindeutig_sein(db):
    datenbank.ereignis_hinzufuegen(db, bahn=1, geraet_millis=1, empfangen_um="t1",
                                   client_event_id="doppelt")
    with pytest.raises(Exception):
        datenbank.ereignis_hinzufuegen(db, bahn=1, geraet_millis=2, empfangen_um="t2",
                                       client_event_id="doppelt")
