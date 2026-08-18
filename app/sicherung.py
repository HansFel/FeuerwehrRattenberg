"""Datensicherung – unterstützt PostgreSQL (Produktion) und SQLite (lokal).

Übernimmt die MGRSoftware-Backup-Logik:
- PostgreSQL: ``pg_dump`` → gzip (.sql.gz); Wiederherstellung per ``psql``
  nach Schema-Reset.
- SQLite: gzip-Kopie der Datenbankdatei (.sqlite.gz); Wiederherstellung
  durch Ersetzen der Datei.

Beide mit SHA-256-Prüfsumme, Metadaten in der Tabelle ``sicherung``,
automatischer Vorher-Sicherung bei Wiederherstellung und Aufbewahrungsgrenze.
"""
from __future__ import annotations

import gzip
import hashlib
import os
import shutil
import subprocess
from datetime import datetime
from urllib.parse import urlparse

from flask import current_app
from werkzeug.utils import secure_filename

from .models import (db, Sicherung, Zeitereignis, NotfallLauf, NotfallBahn,
                     Bestellung, BestellPosition, Strafe, Ergebnis, Startplatz)

MAX_SICHERUNGEN = 30


def _verzeichnis() -> str:
    pfad = os.path.join(current_app.instance_path, "sicherungen")
    os.makedirs(pfad, exist_ok=True)
    return pfad


def _ist_postgres() -> bool:
    return db.engine.dialect.name == "postgresql"


def _endung() -> str:
    return ".sql.gz" if _ist_postgres() else ".sqlite.gz"


def _instanzname() -> str:
    """Kurzname der Instanz für Sicherungsdateien (z.B. 'silo', 'ffrattenberg').

    Mehrere Sicherungen aus verschiedenen Apps/Instanzen landen oft im selben
    Download-Ordner – der Dateiname muss allein erkennen lassen, wozu sie
    gehört. Konvention aus MGRSoftware übernommen (siehe globale CLAUDE.md).
    """
    roh = current_app.config.get("INSTANCE_NAME", "app")
    sicher = "".join(c if c.isalnum() else "-" for c in roh.lower()).strip("-")
    return sicher or "app"


def _db_datei() -> str:
    """Pfad der aktiven SQLite-Datei."""
    return db.engine.url.database


def _sha256(pfad: str) -> str:
    h = hashlib.sha256()
    with open(pfad, "rb") as f:
        for block in iter(lambda: f.read(8192), b""):
            h.update(block)
    return h.hexdigest()


def _pg_params() -> dict:
    p = urlparse(current_app.config["SQLALCHEMY_DATABASE_URI"])
    return {
        "host": p.hostname or "localhost",
        "port": str(p.port or 5432),
        "user": p.username or "",
        "password": p.password or "",
        "dbname": (p.path or "").lstrip("/"),
    }


# ── Erstellen ────────────────────────────────────────────────────────────────

def erstellen(typ: str = "manuell", von: str = "") -> Sicherung:
    db.session.commit()                       # offenen Stand festschreiben
    # Mikrosekunden, damit zwei Sicherungen derselben Sekunde nicht kollidieren
    zeitstempel = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    dateiname = f"{_instanzname()}_sicherung_{zeitstempel}{_endung()}"
    ziel = os.path.join(_verzeichnis(), dateiname)

    if _ist_postgres():
        _pg_dump(ziel)
    else:
        _sqlite_kopieren(ziel)

    s = Sicherung(dateiname=dateiname, dateigroesse=os.path.getsize(ziel),
                  checksum=_sha256(ziel), typ=typ, erstellt_von=von)
    db.session.add(s)
    db.session.commit()
    aufraeumen()
    return s


def _sqlite_kopieren(ziel: str) -> None:
    quelle = _db_datei()
    if not quelle or not os.path.exists(quelle):
        raise FileNotFoundError("Keine SQLite-Datei zum Sichern gefunden.")
    with open(quelle, "rb") as f_in, gzip.open(ziel, "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)


def _pg_dump(ziel: str) -> None:
    pg = _pg_params()
    env = os.environ.copy()
    env["PGPASSWORD"] = pg["password"]
    cmd = ["pg_dump", "-h", pg["host"], "-p", pg["port"], "-U", pg["user"],
           "-d", pg["dbname"], "--no-owner", "--no-acl"]
    proc = subprocess.run(cmd, env=env, capture_output=True, timeout=300)
    if proc.returncode != 0:
        raise RuntimeError("pg_dump fehlgeschlagen: "
                           + proc.stderr.decode("utf-8", "replace"))
    with gzip.open(ziel, "wb") as f:
        f.write(proc.stdout)


# ── Wiederherstellen ─────────────────────────────────────────────────────────

def wiederherstellen(sicherung_id: int) -> None:
    s = db.get_or_404(Sicherung, sicherung_id)
    quelle = os.path.join(_verzeichnis(), s.dateiname)
    if not os.path.exists(quelle):
        raise FileNotFoundError(f"Sicherungsdatei fehlt: {s.dateiname}")
    if s.checksum and _sha256(quelle) != s.checksum:
        raise RuntimeError("Prüfsumme stimmt nicht – Datei evtl. beschädigt.")
    if s.dateiname.endswith(_endung()) is False:
        erwartet = "PostgreSQL (.sql.gz)" if _ist_postgres() else "SQLite (.sqlite.gz)"
        gefunden = "PostgreSQL (.sql.gz)" if s.dateiname.endswith(".sql.gz") else "SQLite (.sqlite.gz)"
        raise RuntimeError(
            f"Diese Sicherung ist im Format {gefunden}, diese Instanz "
            f"nutzt aber {erwartet}. Wiederherstellung nicht möglich – "
            "die Formate sind nicht kompatibel.")

    # Aktuellen Stand vor dem Zurückspielen sichern
    erstellen(typ="vor-wiederherstellung", von=s.erstellt_von)

    if _ist_postgres():
        _pg_restore(quelle)
    else:
        _sqlite_restore(quelle)

    # Nach der Wiederherstellung spiegelt die (mit-wiederhergestellte)
    # Sicherungs-Liste einen alten Stand wider – mit den Dateien auf der
    # Platte abgleichen, damit alle vorhandenen Sicherungen sichtbar bleiben.
    synchronisiere()


def synchronisiere() -> None:
    """Gleicht die Sicherungs-Tabelle mit den Dateien im Verzeichnis ab."""
    verzeichnis = _verzeichnis()
    dateien = {f for f in os.listdir(verzeichnis)
               if f.endswith((".sqlite.gz", ".sql.gz"))}
    bekannt = {s.dateiname for s in Sicherung.query.all()}

    for f in dateien - bekannt:                # fehlende Metadaten ergänzen
        pfad = os.path.join(verzeichnis, f)
        typ = "upload" if "_upload_" in f else "manuell"
        db.session.add(Sicherung(dateiname=f, dateigroesse=os.path.getsize(pfad),
                                 checksum=_sha256(pfad), typ=typ))
    for s in Sicherung.query.all():            # verwaiste Metadaten entfernen
        if s.dateiname not in dateien:
            db.session.delete(s)
    db.session.commit()


def _sqlite_restore(quelle: str) -> None:
    ziel = _db_datei()
    db.session.remove()
    db.engine.dispose()                       # Datei-Sperre lösen
    with gzip.open(quelle, "rb") as f_in, open(ziel, "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)


def _pg_restore(quelle: str) -> None:
    pg = _pg_params()
    env = os.environ.copy()
    env["PGPASSWORD"] = pg["password"]
    with gzip.open(quelle, "rb") as f:
        sql = f.read()

    db.session.remove()
    db.engine.dispose()

    cmd = ["psql", "-h", pg["host"], "-p", pg["port"], "-U", pg["user"],
           "-d", pg["dbname"]]
    reset = (b"DROP SCHEMA IF EXISTS public CASCADE;"
             b"CREATE SCHEMA public;GRANT ALL ON SCHEMA public TO public;")
    r = subprocess.run(cmd, input=reset, env=env, capture_output=True,
                       timeout=120)
    if r.returncode != 0:
        raise RuntimeError("Schema-Reset fehlgeschlagen: "
                           + r.stderr.decode("utf-8", "replace"))
    p = subprocess.run(cmd, input=sql, env=env, capture_output=True,
                       timeout=300)
    if p.returncode != 0:
        fehler = p.stderr.decode("utf-8", "replace")
        if "ERROR" in fehler and "already exists" not in fehler:
            raise RuntimeError("psql-Restore fehlgeschlagen: " + fehler)


# ── Verwaltung ───────────────────────────────────────────────────────────────

def loeschen(sicherung_id: int) -> None:
    s = db.get_or_404(Sicherung, sicherung_id)
    pfad = os.path.join(_verzeichnis(), s.dateiname)
    if os.path.exists(pfad):
        os.remove(pfad)
    db.session.delete(s)
    db.session.commit()


def liste() -> list[Sicherung]:
    return Sicherung.query.order_by(Sicherung.erstellt.desc()).all()


def pfad_fuer(sicherung_id: int) -> tuple[Sicherung, str]:
    s = db.get_or_404(Sicherung, sicherung_id)
    return s, os.path.join(_verzeichnis(), s.dateiname)


def hochladen(datei, von: str = "") -> Sicherung:
    if not datei or not datei.filename:
        raise ValueError("Keine Datei ausgewählt.")
    if not (datei.filename.endswith(".sqlite.gz")
            or datei.filename.endswith(".sql.gz")):
        raise ValueError("Nur .sqlite.gz- oder .sql.gz-Dateien sind erlaubt.")

    endung = ".sql.gz" if datei.filename.endswith(".sql.gz") else ".sqlite.gz"

    # Ursprünglichen Dateinamen behalten (z.B. von einer anderen Instanz
    # heruntergeladen, "lokal_sicherung_...") – so ist in der Liste weiterhin
    # erkennbar, welche Datei hochgeladen wurde. Nur bei einem echten
    # Namenskonflikt auf einen generischen, garantiert eindeutigen Namen
    # ausweichen.
    dateiname = secure_filename(datei.filename)
    ziel = os.path.join(_verzeichnis(), dateiname)
    if not dateiname or os.path.exists(ziel):
        zeitstempel = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        dateiname = f"{_instanzname()}_upload_{zeitstempel}{endung}"
        ziel = os.path.join(_verzeichnis(), dateiname)
    datei.save(ziel)

    try:
        with gzip.open(ziel, "rb") as f:
            f.read(16)
    except OSError:
        os.remove(ziel)
        raise ValueError("Datei ist kein gültiges gzip-Archiv.")

    s = Sicherung(dateiname=dateiname, dateigroesse=os.path.getsize(ziel),
                  checksum=_sha256(ziel), typ="upload", erstellt_von=von)
    db.session.add(s)
    db.session.commit()
    return s


def aufraeumen(max_sicherungen: int = MAX_SICHERUNGEN) -> int:
    alle = Sicherung.query.order_by(Sicherung.erstellt.desc()).all()
    geloescht = 0
    for s in alle[max_sicherungen:]:
        pfad = os.path.join(_verzeichnis(), s.dateiname)
        if os.path.exists(pfad):
            os.remove(pfad)
        db.session.delete(s)
        geloescht += 1
    if geloescht:
        db.session.commit()
    return geloescht


def testdaten_loeschen() -> dict[str, int]:
    """Löscht Zeitmessung, Bestellungen (inkl. Sympathiepunkte) und
    vergebene Strafen/Ergebnisse aus Testläufen – behält aber Teams,
    Mitglieder und die Speisekarte (Preise) unverändert.

    Löschreihenfolge beachtet Fremdschlüssel (Kind vor Eltern). Aufrufer
    ist dafür verantwortlich, vorher eine Sicherung anzulegen (siehe
    Blueprint-Route) – diese Funktion selbst sichert nichts.
    """
    anzahl = {
        "bestellpositionen": BestellPosition.query.delete(),
        "bestellungen": Bestellung.query.delete(),
        "notfallbahnen": NotfallBahn.query.delete(),
        "notfalllaeufe": NotfallLauf.query.delete(),
        "zeitereignisse": Zeitereignis.query.delete(),
        "strafen": Strafe.query.delete(),
        "ergebnisse": Ergebnis.query.delete(),
    }
    # Gemessene Zeiten im Zeitplan zurücksetzen, die Startplätze (Team/
    # Disziplin/Bahn/Startzeit) selbst bleiben als Planungsdaten erhalten.
    anzahl["startplaetze_zurueckgesetzt"] = Startplatz.query.filter(
        Startplatz.ergebnis_sekunden.isnot(None)
    ).update({"ergebnis_sekunden": None})
    db.session.commit()
    return anzahl
