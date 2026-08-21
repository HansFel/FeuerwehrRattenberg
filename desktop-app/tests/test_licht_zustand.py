import pytest

from zeitmessung_desktop.licht_zustand import laufquelle_bestimmen, zustand_bestimmen


def test_aktiver_serverlauf_hat_vorrang_vor_altem_lokalen_lauf():
    assert laufquelle_bestimmen(True, True) == "server"


def test_lokaler_lauf_uebernimmt_nur_ohne_aktiven_serverlauf():
    assert laufquelle_bestimmen(False, True) == "lokal"


def test_ohne_lauf_gibt_es_keine_lichtquelle():
    assert laufquelle_bestimmen(False, False) is None


def test_kein_lauf_ergibt_aus():
    assert zustand_bestimmen(lauf_aktiv=False, aktiviert=False, hat_kontakt=False) == "aus"


def test_kein_lauf_ergibt_aus_auch_bei_inkonsistenten_flags():
    """Wenn lauf_aktiv=False ist, spielen die anderen Flags keine Rolle -
    reale Aufrufer sollten das nie liefern, aber die Funktion soll sich
    trotzdem nicht in einen unsinnigen Zustand bringen lassen."""
    assert zustand_bestimmen(lauf_aktiv=False, aktiviert=True, hat_kontakt=True) == "aus"


def test_lauf_ohne_freigabe_ergibt_vorbereitung():
    assert zustand_bestimmen(lauf_aktiv=True, aktiviert=False, hat_kontakt=False) == "vorbereitung"


def test_freigegeben_ohne_kontakt_ergibt_start_gruen():
    """Sobald der Organisator die Zeitmessung freigibt (aktiviert, noch kein
    Kontakt), schaltet das Licht auf GRUEN ("start") - nicht erst beim 1.
    Kontakt. Genau das verlangt der User (Build 80). Das fruehere blaue
    "bereit" entfaellt bewusst."""
    assert zustand_bestimmen(lauf_aktiv=True, aktiviert=True, hat_kontakt=False) == "start"


def test_freigegeben_mit_kontakt_bleibt_start():
    assert zustand_bestimmen(lauf_aktiv=True, aktiviert=True, hat_kontakt=True) == "start"


@pytest.mark.parametrize("lauf_aktiv,aktiviert,hat_kontakt,erwartet", [
    (True, False, False, "vorbereitung"),
    (True, True, False, "start"),
    (True, True, True, "start"),
    (False, False, False, "aus"),
])
def test_alle_erreichbaren_zustaende(lauf_aktiv, aktiviert, hat_kontakt, erwartet):
    assert zustand_bestimmen(lauf_aktiv, aktiviert, hat_kontakt) == erwartet


# ---- fertig (ROT) bei vollstaendigem Lauf ---------------------------------

def test_vollstaendiger_lauf_ergibt_fertig_auch_mit_kontakt():
    """Lauf abgeschlossen -> ROT ("fertig"), selbst wenn Kontakte vorliegen
    (sonst wuerde ein fertiger, noch aktivierter Lauf irrtuemlich gruen
    "start" bleiben). Genau der Fall, den das Feature beheben soll."""
    assert zustand_bestimmen(lauf_aktiv=True, aktiviert=True,
                            hat_kontakt=True, vollstaendig=True) == "fertig"


def test_vollstaendig_uebersteuert_bereit():
    assert zustand_bestimmen(lauf_aktiv=True, aktiviert=True,
                            hat_kontakt=False, vollstaendig=True) == "fertig"


def test_vollstaendig_ohne_freigabe_bleibt_vorbereitung():
    """Nicht freigegebene Laeufe sind nie "fertig" - erst freigeben, dann
    messen, dann ROT."""
    assert zustand_bestimmen(lauf_aktiv=True, aktiviert=False,
                            hat_kontakt=False, vollstaendig=True) == "vorbereitung"


def test_kein_lauf_mit_vollstaendig_bleibt_aus():
    assert zustand_bestimmen(lauf_aktiv=False, aktiviert=False,
                            hat_kontakt=False, vollstaendig=True) == "aus"


def test_vollstaendig_default_false_laesst_alte_zustaende_unberuehrt():
    """vollstaendig ist optional - ohne es verhaelt sich die Funktion wie
    ein freigegebener Lauf: GRUEN ("start"), egal ob schon Kontakt da ist
    (das fruehere blaue "bereit" entfaellt, siehe Build 80)."""
    assert zustand_bestimmen(True, True, True) == "start"
    assert zustand_bestimmen(True, True, False) == "start"
