"""Hilfslogik für die seriellen Port-Dropdowns im Einstellungsdialog.

Bewusst Qt-frei und rein, damit die Kollisionsvermeidung - Mega- und
DMX-Port bezeichnen nicht denselben Arduino - ohne GUI testbar ist
(siehe hauptfenster.py:EinstellungenDialog und AGENTS.md, Abschnitt
"DMX-Bahnbeleuchtung").

Hintergrund: der Zeitmessungs-Mega 2560 und der DMX-Uno sind BEIDE
CH340-basiert und daher in der reinen Portliste nicht unterscheidbar.
Ohne Synchronisation der beiden Dropdowns kann man versehentlich
denselben Port beiden Feldern zuordnen - die App öffnet dann denselben
Arduino zweimal (Kollision, siehe AGENTS.md). Diese Logik blendet den im
einen Feld gewählten Port im jeweils anderen aus.
"""
from __future__ import annotations

import serial.tools.list_ports


def erkannte_ports() -> list[str]:
    """Alle aktuell angeschlossenen seriellen Ports mit echter USB-Hardware-ID.

    Auf Linux liefert comports() zusaetzlich alle 32 Legacy-UARTs
    /dev/ttyS0-31 (hwid "n/a"), die ohne echte Hardware immer "vorhanden"
    sind - die werden hier ausgefiltert, damit nur wirklich angeschlossene
    Geraete zur Auswahl stehen (gleiche Begründung wie zuvor in
    hauptfenster.py:_com_ports_aktualisieren).
    """
    return [p.device for p in serial.tools.list_ports.comports()
            if p.hwid and p.hwid != "n/a"]


def port_auswahl(
    aktueller_wert: str,
    *,
    erkannt: list[str] | None = None,
    leer_option: bool = False,
    gesperrt: set[str] | None = None,
) -> list[str]:
    """Bestimmt die Eintraege fuer ein Port-Dropdown (in Anzeigereihenfolge).

    Parameter:
        aktueller_wert: aktuell gespeicherter/ausgewaehlter Port DIESES
            Feldes. Wird IMMER mit angeboten, auch wenn das Geraet gerade
            nicht angesteckt ist - AUSNAHME: er steht in `gesperrt` (dann
            gehoert er dem ANDEREN Arduino und darf hier nicht waehlbar
            sein, das ist gerade die zu vermeidende Kollision).
        erkannt: erkannte Ports (Default: erkannte_ports()). Injizierbar
            fuer Tests.
        leer_option: True fuer das DMX-Feld - fuegt einen leeren Eintrag
            ("aus/deaktiviert") an den Anfang. Fuer den Mega (Pflicht)
            nicht gesetzt.
        gesperrt: Ports, die dem jeweils ANDEREN Arduino zugeordnet sind
            und hier ausgeblendet werden.

    Duplikate werden entfernt; die Reihenfolge der erkannten Ports bleibt
    erhalten, der gerettete eigene Wert rutscht direkt hinter die
    Leeroption (bzw. an den Anfang).
    """
    if erkannt is None:
        erkannt = erkannte_ports()
    gesperrt = gesperrt or set()
    eintraege: list[str] = []
    if leer_option:
        eintraege.append("")
    for port in erkannt:
        if port in gesperrt:
            continue
        if port not in eintraege:
            eintraege.append(port)
    # Eigenen gespeicherten Wert retten - ausser er ist gerade gesperrt
    # (dann gehoert er dem anderen Geraet, siehe oben).
    if (aktueller_wert
            and aktueller_wert not in gesperrt
            and aktueller_wert not in eintraege):
        eintraege.insert(1 if leer_option else 0, aktueller_wert)
    return eintraege


def kollision_aufloesen(com_wert: str, dmx_wert: str) -> str:
    """Loest eine Kollision auf: derselbe Port darf nicht beiden Geraeten
    zugeordnet sein. Der Mega (Zeitmessung) hat Vorrang - der DMX-Port wird
    in diesem Fall auf "" (aus) zurueckgesetzt. Liefert den korrigierten
    dmx_wert (com_wert bleibt unveraendert, siehe Aufrufer).

    Leerstrings sind erlaubt (DMX = optional); "" kollidiert nie.
    """
    if dmx_wert and dmx_wert == com_wert:
        return ""
    return dmx_wert