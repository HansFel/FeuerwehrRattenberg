"""Lokaler SQLite-Puffer für Kontaktereignisse.

Jedes vom Arduino Mega empfangene Ereignis wird SOFORT hier gespeichert,
bevor überhaupt ein Sync-Versuch zur Webapp unternommen wird - Priorität:
keine Messung geht verloren, auch bei Stromausfall direkt danach. WAL-Modus
für Robustheit bei einem harten Absturz/Stromausfall mitten im Schreiben."""
from __future__ import annotations

import sqlite3
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS ereignis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bahn INTEGER NOT NULL,
    geraet_millis INTEGER,
    empfangen_um TEXT NOT NULL,
    client_event_id TEXT NOT NULL UNIQUE,
    sync_status TEXT NOT NULL DEFAULT 'ausstehend',
    sync_versucht_um TEXT,
    server_id INTEGER
);
CREATE INDEX IF NOT EXISTS idx_ereignis_sync_status ON ereignis (sync_status);

-- Lokale Team-Bahn-Zuordnung + automatische Zuordnung, falls die Webapp
-- beim Start des Laufs nicht erreichbar ist (siehe lauf_import_worker.py).
-- Team wird nur per eingetippter Startnummer referenziert (kein Team-Lookup
-- offline möglich) - der Abgleich mit dem echten Team passiert erst beim
-- Import in der Webapp (app/blueprints/notfall.py:api_importieren).
CREATE TABLE IF NOT EXISTS lokaler_lauf (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bezeichnung TEXT NOT NULL DEFAULT '',
    aktiv INTEGER NOT NULL DEFAULT 1,
    aktiviert_um TEXT NOT NULL,
    sync_status TEXT NOT NULL DEFAULT 'ausstehend',
    server_lauf_id INTEGER,
    sync_versucht_um TEXT
);
CREATE TABLE IF NOT EXISTS lokale_bahn (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lauf_id INTEGER NOT NULL REFERENCES lokaler_lauf(id),
    bahn_nr INTEGER NOT NULL,
    team_nummer TEXT NOT NULL,
    zeit_laeufer1 REAL,
    zeit_laeufer2 REAL,
    zeit_laeufer3 REAL,
    zeit_laeufer4 REAL
);
"""


def verbinden(db_pfad: str) -> sqlite3.Connection:
    Path(db_pfad).parent.mkdir(parents=True, exist_ok=True)
    verbindung = sqlite3.connect(db_pfad, check_same_thread=False)
    verbindung.execute("PRAGMA journal_mode=WAL")
    verbindung.row_factory = sqlite3.Row
    verbindung.executescript(_SCHEMA)
    verbindung.commit()
    return verbindung


def ereignis_hinzufuegen(verbindung: sqlite3.Connection, *, bahn: int, geraet_millis: int,
                         empfangen_um: str, client_event_id: str) -> int:
    cursor = verbindung.execute(
        "INSERT INTO ereignis (bahn, geraet_millis, empfangen_um, client_event_id) "
        "VALUES (?, ?, ?, ?)",
        (bahn, geraet_millis, empfangen_um, client_event_id),
    )
    verbindung.commit()
    return cursor.lastrowid


def ausstehende_ereignisse(verbindung: sqlite3.Connection, limit: int = 50) -> list[sqlite3.Row]:
    return verbindung.execute(
        "SELECT * FROM ereignis WHERE sync_status = 'ausstehend' "
        "ORDER BY id ASC LIMIT ?", (limit,)
    ).fetchall()


def als_gesendet_markieren(verbindung: sqlite3.Connection, ereignis_id: int,
                            server_id: int | None, versucht_um: str) -> None:
    verbindung.execute(
        "UPDATE ereignis SET sync_status = 'gesendet', server_id = ?, "
        "sync_versucht_um = ? WHERE id = ?",
        (server_id, versucht_um, ereignis_id),
    )
    verbindung.commit()


def versuch_vermerken(verbindung: sqlite3.Connection, ereignis_id: int, versucht_um: str) -> None:
    """Vermerkt einen fehlgeschlagenen Sync-Versuch (Status bleibt 'ausstehend' -
    wird beim nächsten Sync-Zyklus erneut versucht)."""
    verbindung.execute(
        "UPDATE ereignis SET sync_versucht_um = ? WHERE id = ?",
        (versucht_um, ereignis_id),
    )
    verbindung.commit()


def anzahl_ausstehend(verbindung: sqlite3.Connection) -> int:
    zeile = verbindung.execute(
        "SELECT COUNT(*) AS anzahl FROM ereignis WHERE sync_status = 'ausstehend'"
    ).fetchone()
    return zeile["anzahl"]


def letzte_ereignisse(verbindung: sqlite3.Connection, limit: int = 20) -> list[sqlite3.Row]:
    return verbindung.execute(
        "SELECT * FROM ereignis ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()


def alle_loeschen(verbindung: sqlite3.Connection) -> int:
    """Löscht ALLE lokal gepufferten Ereignisse (z.B. nach einem Testlauf,
    bevor der echte Wettkampf beginnt). Betrifft NUR den lokalen Puffer,
    NICHT die bereits synchronisierten Zeilen in der Webapp-Datenbank -
    dafür den bestehenden 'Löschen'-Knopf unter /zeitmessung/ verwenden."""
    cursor = verbindung.execute("DELETE FROM ereignis")
    verbindung.commit()
    return cursor.rowcount


# ── Lokale Team-Bahn-Zuordnung (Offline-Fallback ohne Webapp-Verbindung) ──

def lokalen_lauf_starten(verbindung: sqlite3.Connection, *, bezeichnung: str,
                         team_nummern: dict[int, str], aktiviert_um: str) -> int:
    """Startet einen neuen lokalen Lauf und deaktiviert einen vorher aktiven
    (analog zu notfall.aktivieren() auf dem Server - immer nur einer
    gleichzeitig aktiv). team_nummern: {bahn_nr: team_nummer}, nur belegte
    Bahnen übergeben."""
    verbindung.execute("UPDATE lokaler_lauf SET aktiv = 0 WHERE aktiv = 1")
    cursor = verbindung.execute(
        "INSERT INTO lokaler_lauf (bezeichnung, aktiv, aktiviert_um) VALUES (?, 1, ?)",
        (bezeichnung, aktiviert_um),
    )
    lauf_id = cursor.lastrowid
    for bahn_nr, team_nummer in team_nummern.items():
        verbindung.execute(
            "INSERT INTO lokale_bahn (lauf_id, bahn_nr, team_nummer) VALUES (?, ?, ?)",
            (lauf_id, bahn_nr, team_nummer),
        )
    verbindung.commit()
    return lauf_id


def aktiver_lokaler_lauf(verbindung: sqlite3.Connection) -> sqlite3.Row | None:
    return verbindung.execute(
        "SELECT * FROM lokaler_lauf WHERE aktiv = 1 LIMIT 1"
    ).fetchone()


def lokale_bahnen(verbindung: sqlite3.Connection, lauf_id: int) -> list[sqlite3.Row]:
    return verbindung.execute(
        "SELECT * FROM lokale_bahn WHERE lauf_id = ? ORDER BY bahn_nr", (lauf_id,)
    ).fetchall()


def lokale_bahn_zeiten_setzen(verbindung: sqlite3.Connection, bahn_id: int,
                              zeiten: list[float]) -> None:
    verbindung.execute(
        "UPDATE lokale_bahn SET zeit_laeufer1 = ?, zeit_laeufer2 = ?, "
        "zeit_laeufer3 = ?, zeit_laeufer4 = ? WHERE id = ?",
        (*zeiten, bahn_id),
    )
    verbindung.commit()


def offene_lokale_laeufe(verbindung: sqlite3.Connection) -> list[sqlite3.Row]:
    """Lokale Läufe, die noch nicht (vollständig) an die Webapp gemeldet
    wurden - der Import-Worker versucht es bei jedem Zyklus erneut."""
    return verbindung.execute(
        "SELECT * FROM lokaler_lauf WHERE sync_status = 'ausstehend' ORDER BY id"
    ).fetchall()


def lokalen_lauf_als_gesendet_markieren(verbindung: sqlite3.Connection, lauf_id: int,
                                        server_lauf_id: int, versucht_um: str) -> None:
    verbindung.execute(
        "UPDATE lokaler_lauf SET sync_status = 'gesendet', server_lauf_id = ?, "
        "sync_versucht_um = ? WHERE id = ?",
        (server_lauf_id, versucht_um, lauf_id),
    )
    verbindung.commit()


def lokalen_lauf_versuch_vermerken(verbindung: sqlite3.Connection, lauf_id: int,
                                   server_lauf_id: int | None, versucht_um: str) -> None:
    """Vermerkt einen Sync-Versuch, ohne den Lauf schon als vollständig
    gesendet zu markieren - z.B. wenn erst manche Bahnen fertig zugeordnet
    sind. server_lauf_id wird trotzdem gespeichert (idempotente Updates bei
    künftigen Versuchen), Status bleibt 'ausstehend'."""
    verbindung.execute(
        "UPDATE lokaler_lauf SET server_lauf_id = ?, sync_versucht_um = ? WHERE id = ?",
        (server_lauf_id, versucht_um, lauf_id),
    )
    verbindung.commit()
