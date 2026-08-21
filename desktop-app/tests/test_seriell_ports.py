"""Tests fuer die kollisionsfreie Port-Auswahllogik (Qt-frei) - siehe
seriell_ports.py und hauptfenster.py:EinstellungenDialog.

Hintergrund: Mega (Zeitmessung) und DMX-Uno (Bahnbeleuchtung) sind
beide CH340 und an den Ports nicht unterscheidbar. Die beiden
Port-Dropdowns muessen deshalb gekoppelt sein, damit nicht
versehentlich derselbe Port beiden Geraeten zugeordnet (und damit
derselbe Arduino zweimal geoeffnet) wird.
"""
from zeitmessung_desktop.seriell_ports import kollision_aufloesen, port_auswahl


# ---- port_auswahl --------------------------------------------------------

def test_port_auswahl_ohne_geraete_zeigt_gespeicherten_wert():
    # Geraet nicht angesteckt - gespeicherter Wert bleibt trotzdem waehlbar.
    eintraege = port_auswahl("COM7", erkannt=[], leer_option=False)
    assert eintraege == ["COM7"]


def test_port_auswahl_mit_leer_option_hat_leeren_eintrag_zuerst():
    eintraege = port_auswahl("", erkannt=["COM3", "COM5"], leer_option=True)
    assert eintraege[0] == ""        # "aus/deaktiviert" als erste Wahl
    assert "COM3" in eintraege and "COM5" in eintraege


def test_port_auswahl_ohne_leer_option_kein_leerer_eintrag():
    # Mega-Port ist Pflicht - keine "aus"-Option.
    eintraege = port_auswahl("COM3", erkannt=["COM3"], leer_option=False)
    assert "" not in eintraege


def test_port_auswahl_schliesst_gesperrten_port_aus():
    # COM3 ist dem MEGA zugeordnet -> im DMX-Dropdown ausgeblendet.
    eintraege = port_auswahl("", erkannt=["COM3", "COM5"], leer_option=True,
                             gesperrt={"COM3"})
    assert "COM3" not in eintraege
    assert "COM5" in eintraege


def test_port_auswahl_eigener_wert_bleibt_trotz_sperre_eines_anderen():
    # DMX steht auf COM5, Mega auf COM3 -> COM3 wird ausgeblendet, COM5
    # (der eigene Wert) bleibt natuerlich sichtbar.
    eintraege = port_auswahl("COM5", erkannt=["COM3", "COM5"], leer_option=True,
                             gesperrt={"COM3"})
    assert "COM3" not in eintraege
    assert "COM5" in eintraege


def test_port_auswahl_eigener_wert_wird_gerettet_wenn_nicht_erkannt():
    # Gespeicherter DMX-Port COM9 ist gerade nicht angesteckt - trotzdem
    # waehlbar (hinter der Leeroption), damit der Wert nicht verloren geht.
    eintraege = port_auswahl("COM9", erkannt=["COM3"], leer_option=True)
    assert eintraege == ["", "COM9", "COM3"]


def test_port_auswahl_eigener_wert_ist_gesperrt_wird_nicht_gerettet():
    # Wuerde die Kollision aufweichen: eigener Wert gehoert laut Sperre dem
    # anderen Geraet -> bewusst NICHT retten.
    eintraege = port_auswahl("COM3", erkannt=["COM5"], gesperrt={"COM3"})
    assert "COM3" not in eintraege
    assert "COM5" in eintraege


def test_port_auswahl_keine_duplikate():
    eintraege = port_auswahl("COM3", erkannt=["COM3", "COM3", "COM5"])
    assert eintraege.count("COM3") == 1
    assert eintraege.count("COM5") == 1


# ---- kollision_aufloesen -------------------------------------------------

def test_kollision_wird_aufgeloest_dmx_geht_auf_aus():
    # Derselbe Port beiden Geraeten -> Mega hat Vorrang, DMX auf "" (aus).
    assert kollision_aufloesen("COM3", "COM3") == ""


def test_keine_kollision_bleibt_unveraendert():
    assert kollision_aufloesen("COM3", "COM5") == "COM5"


def test_leerer_dmx_kollidiert_nie():
    assert kollision_aufloesen("COM3", "") == ""
    assert kollision_aufloesen("", "") == ""


def test_kollision_unabhaengig_von_leeren_com():
    # COM leer, DMX gesetzt -> keine Kollision (leerer Mega = nichts
    # zugeordnet), DMX bleibt.
    assert kollision_aufloesen("", "COM5") == "COM5"