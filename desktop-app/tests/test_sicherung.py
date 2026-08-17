from datetime import datetime

from zeitmessung_desktop import datenbank, sicherung


def test_sicherung_dateiname_enthaelt_instanzname():
    name = sicherung.sicherung_dateiname("zeitmessung-laptop1", datetime(2026, 8, 16, 14, 30, 5))
    assert name == "zeitmessung-laptop1_sicherung_20260816_143005.sqlite"


def test_sicherung_durchfuehren_erstellt_konsistente_kopie(tmp_path):
    db_pfad = tmp_path / "quelle.sqlite"
    db = datenbank.verbinden(str(db_pfad))
    datenbank.ereignis_hinzufuegen(db, bahn=1, geraet_millis=1, empfangen_um="t1",
                                   client_event_id="a")

    ziel_ordner = tmp_path / "sicherungen"
    ziel_datei = sicherung.sicherung_durchfuehren(
        str(db_pfad), str(ziel_ordner), "zeitmessung-laptop1",
        zeitpunkt=datetime(2026, 8, 16, 12, 0, 0))

    assert ziel_datei.exists()
    assert ziel_datei.name == "zeitmessung-laptop1_sicherung_20260816_120000.sqlite"

    kopie = datenbank.verbinden(str(ziel_datei))
    zeilen = datenbank.letzte_ereignisse(kopie)
    assert len(zeilen) == 1
    assert zeilen[0]["client_event_id"] == "a"
