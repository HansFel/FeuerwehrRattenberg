"""Tests für die additive Schema-Migration (_spalten_ergaenzen).

Deckt genau das Szenario ab, das auf dem NAS zu einem 500er führte: eine
Tabelle (z.B. "artikel") existiert bereits aus einem früheren Deploy, ohne
die neu hinzugekommenen Spalten (z.B. "pfand_pro_einheit"). db.create_all()
legt bei bereits vorhandenen Tabellen KEINE fehlenden Spalten nach – das
muss die eigene Migration übernehmen, für SQLite und PostgreSQL gleichermaßen.
"""
import sqlite3

from sqlalchemy import text

from app import create_app
from app.models import db, Artikel, BestellPosition


def test_migration_ergaenzt_fehlende_spalten_in_bestehender_tabelle(tmp_path):
    """Simuliert eine alte DB-Datei, in der 'artikel' und 'bestellposition'
    noch ohne die Pfand-Spalten angelegt wurden (alter Codestand)."""
    dbdatei = tmp_path / "alt.sqlite"

    con = sqlite3.connect(str(dbdatei))
    con.execute("""
        CREATE TABLE artikel (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            kategorie TEXT,
            preis REAL NOT NULL,
            punkte_pro_einheit INTEGER,
            aktiv BOOLEAN,
            reihenfolge INTEGER
        )
    """)
    con.execute("""
        CREATE TABLE bestellposition (
            id INTEGER PRIMARY KEY,
            bestellung_id INTEGER NOT NULL,
            artikel_id INTEGER,
            artikel_name TEXT NOT NULL,
            einzelpreis REAL NOT NULL,
            menge INTEGER NOT NULL,
            team_id INTEGER,
            punkte_gesamt INTEGER
        )
    """)
    con.execute("INSERT INTO artikel (name, kategorie, preis, punkte_pro_einheit, "
               "aktiv, reihenfolge) VALUES ('Altes Bier', 'getraenk', 3.0, 0, 1, 0)")
    con.commit()
    con.close()

    # create_app() muss die fehlenden Spalten ergänzen, ohne abzustürzen.
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{dbdatei}",
        "ADMIN_STARTPASSWORT": "admin",
    })
    with app.app_context():
        # Altes Datum blieb erhalten …
        alt = Artikel.query.filter_by(name="Altes Bier").first()
        assert alt is not None
        # … und die neue Spalte ist jetzt da, mit sinnvollem Default.
        assert alt.pfand_pro_einheit == 0.0

        # Und ein Insert mit den neuen Feldern funktioniert.
        db.session.add(BestellPosition(
            bestellung_id=1, artikel_name="Test", einzelpreis=1.0, menge=1,
            pfand_pro_einheit=2.0, pfand_zurueckgegeben=0,
        ))
        db.session.commit()
        pos = BestellPosition.query.first()
        assert pos.pfand_pro_einheit == 2.0


def test_migration_ist_idempotent(tmp_path):
    """Zweimaliger Aufruf (z.B. durch Neustart) darf nicht fehlschlagen."""
    dbdatei = tmp_path / "zweimal.sqlite"
    app1 = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{dbdatei}",
        "ADMIN_STARTPASSWORT": "admin",
    })
    with app1.app_context():
        db.session.remove()
        db.engine.dispose()

    # Zweiter Start auf derselben Datei – darf nicht crashen.
    app2 = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{dbdatei}",
        "ADMIN_STARTPASSWORT": "admin",
    })
    with app2.app_context():
        assert Artikel.query.count() == 0
