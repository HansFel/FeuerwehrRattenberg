"""Einmaliges Aufräumen: entfernt die alten Seed-/Testartikel der Speisekarte
(aus seed_testdaten.py), nachdem die echte Preisliste (siehe
import_speisekarte.py) importiert wurde.

Löscht jeden Artikel, dessen Name NICHT in der echten Preisliste
(import_speisekarte.ARTIKEL) vorkommt. Bereits erfasste Bestellpositionen
bleiben als Datensatz erhalten (Name/Preis sind pro Position eingefroren,
Snapshot-Pattern) - nur die Referenz auf den gelöschten Artikel wird auf
NULL gesetzt, exakt wie beim manuellen Löschen über /speisekarte/<id>/loeschen.

Nutzung:
    python entferne_alte_speisekarte.py [--commit]

Ohne --commit ist es ein Trockenlauf.
"""
import argparse

from app import create_app
from app.models import db, Artikel, BestellPosition
from import_speisekarte import ARTIKEL

NEUE_NAMEN = {name for name, *_ in ARTIKEL}


def aufraeumen(commit: bool):
    app = create_app()
    with app.app_context():
        alte = Artikel.query.filter(~Artikel.name.in_(NEUE_NAMEN)).all()
        if not alte:
            print("Keine alten Artikel gefunden.")
            return

        for a in alte:
            n_pos = BestellPosition.query.filter_by(artikel_id=a.id).count()
            print(f"# LÖSCHEN: {a.name!r} ({a.kategorie}, {a.preis:.2f}€) "
                  f"- {n_pos} Bestellposition(en) werden entkoppelt")
            if commit:
                BestellPosition.query.filter_by(artikel_id=a.id).update(
                    {"artikel_id": None})
                db.session.delete(a)

        if commit:
            db.session.commit()
            print(f"\n{len(alte)} alte Artikel gelöscht. Gespeichert.")
        else:
            print(f"\nTROCKENLAUF: {len(alte)} alte Artikel würden gelöscht. "
                  "Nichts gespeichert (--commit fehlt).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", action="store_true",
                        help="Ohne diesen Schalter nur Trockenlauf")
    args = parser.parse_args()
    aufraeumen(args.commit)
