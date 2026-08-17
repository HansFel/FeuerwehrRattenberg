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
