"""Lokale Nachbildung der Server-Automatik (siehe
app/blueprints/zeitmessung.py:_automatische_zuordnung_pruefen) für den Fall,
dass die Webapp beim Start eines Laufs nicht erreichbar ist: die Desktop-App
ordnet Teams dann per eingetippter Startnummer den Bahnen zu (siehe
datenbank.py:lokalen_lauf_starten) und berechnet die Läuferzeiten selbst,
identisch zur Server-Logik (1.-4. Auslösung = Läufer-Start, 5. = Ziel).
Wird vom SeriellWorker nach jedem EVENT aufgerufen."""
from __future__ import annotations

import sqlite3
from datetime import datetime

from . import datenbank


def zuordnung_pruefen(verbindung: sqlite3.Connection, bahn: int) -> None:
    lauf = datenbank.aktiver_lokaler_lauf(verbindung)
    if lauf is None:
        return
    ziel_bahn = next((b for b in datenbank.lokale_bahnen(verbindung, lauf["id"])
                      if b["bahn_nr"] == bahn), None)
    if ziel_bahn is None or ziel_bahn["zeit_laeufer4"] is not None:
        return   # Bahn nicht belegt oder schon vollständig zugeordnet

    zeilen = verbindung.execute(
        "SELECT empfangen_um FROM ereignis WHERE bahn = ? AND empfangen_um >= ? "
        "ORDER BY id ASC LIMIT 5",
        (bahn, lauf["aktiviert_um"]),
    ).fetchall()
    if len(zeilen) < 5:
        return

    zeitstempel = [datetime.fromisoformat(z["empfangen_um"]) for z in zeilen]
    zeiten = [(zeitstempel[i + 1] - zeitstempel[i]).total_seconds() for i in range(4)]
    datenbank.lokale_bahn_zeiten_setzen(verbindung, ziel_bahn["id"], zeiten)
