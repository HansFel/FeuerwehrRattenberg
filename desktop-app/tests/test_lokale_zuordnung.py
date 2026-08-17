import pytest

from zeitmessung_desktop import datenbank
from zeitmessung_desktop.lokale_zuordnung import zuordnung_pruefen


@pytest.fixture
def db(tmp_path):
    return datenbank.verbinden(str(tmp_path / "test.sqlite"))


def _ereignis(db, bahn, empfangen_um):
    datenbank.ereignis_hinzufuegen(db, bahn=bahn, geraet_millis=1, empfangen_um=empfangen_um,
                                   client_event_id=empfangen_um + str(bahn))


def test_ohne_aktiven_lauf_passiert_nichts(db):
    _ereignis(db, 1, "2026-08-17T10:00:00+00:00")
    zuordnung_pruefen(db, 1)   # darf nicht abstürzen


def test_fuenf_events_fuellen_lokale_bahn_aus(db):
    lauf_id = datenbank.lokalen_lauf_starten(
        db, bezeichnung="Test", team_nummern={1: "12"},
        aktiviert_um="2026-08-17T10:00:00+00:00")

    zeiten = ["2026-08-17T10:00:01+00:00", "2026-08-17T10:00:03+00:00",
             "2026-08-17T10:00:06+00:00", "2026-08-17T10:00:10+00:00",
             "2026-08-17T10:00:15+00:00"]
    for t in zeiten:
        _ereignis(db, 1, t)
        zuordnung_pruefen(db, 1)

    bahn = datenbank.lokale_bahnen(db, lauf_id)[0]
    assert bahn["zeit_laeufer1"] == pytest.approx(2.0)
    assert bahn["zeit_laeufer2"] == pytest.approx(3.0)
    assert bahn["zeit_laeufer3"] == pytest.approx(4.0)
    assert bahn["zeit_laeufer4"] == pytest.approx(5.0)


def test_events_vor_aktivierung_zaehlen_nicht(db):
    _ereignis(db, 1, "2026-08-17T09:59:00+00:00")   # vor Aktivierung
    lauf_id = datenbank.lokalen_lauf_starten(
        db, bezeichnung="Test", team_nummern={1: "12"},
        aktiviert_um="2026-08-17T10:00:00+00:00")

    for t in ["2026-08-17T10:00:01+00:00", "2026-08-17T10:00:02+00:00",
             "2026-08-17T10:00:03+00:00", "2026-08-17T10:00:04+00:00"]:
        _ereignis(db, 1, t)
        zuordnung_pruefen(db, 1)

    bahn = datenbank.lokale_bahnen(db, lauf_id)[0]
    assert bahn["zeit_laeufer1"] is None   # erst 4 NEUE Events, das alte zaehlt nicht mit


def test_unbelegte_bahn_bleibt_leer(db):
    datenbank.lokalen_lauf_starten(
        db, bezeichnung="Test", team_nummern={1: "12"},   # Bahn 2 nicht belegt
        aktiviert_um="2026-08-17T10:00:00+00:00")

    for i in range(5):
        _ereignis(db, 2, f"2026-08-17T10:00:0{i}+00:00")
        zuordnung_pruefen(db, 2)

    # keine Bahn 2 angelegt -> darf nicht abstuerzen, nichts zu pruefen


def test_bereits_vollstaendige_bahn_wird_nicht_ueberschrieben(db):
    lauf_id = datenbank.lokalen_lauf_starten(
        db, bezeichnung="Test", team_nummern={1: "12"},
        aktiviert_um="2026-08-17T10:00:00+00:00")
    bahn = datenbank.lokale_bahnen(db, lauf_id)[0]
    datenbank.lokale_bahn_zeiten_setzen(db, bahn["id"], [1.0, 2.0, 3.0, 4.0])

    for t in ["2026-08-17T10:00:01+00:00", "2026-08-17T10:00:02+00:00",
             "2026-08-17T10:00:03+00:00", "2026-08-17T10:00:04+00:00",
             "2026-08-17T10:00:05+00:00"]:
        _ereignis(db, 1, t)
        zuordnung_pruefen(db, 1)

    aktualisiert = datenbank.lokale_bahnen(db, lauf_id)[0]
    assert aktualisiert["zeit_laeufer1"] == pytest.approx(1.0)
