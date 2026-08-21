"""Einmaliger Import der echten Speisekarte/Preisliste (120 Jahre FF
Rattenberg) aus der vom Veranstalter gelieferten PDF-Preisliste.

Gleicht per Artikel-NAME ab: existiert der Name schon (Seed-/Testdaten oder
vorheriger Import), werden Preis/Kategorie/Reihenfolge aktualisiert; sonst
wird ein neuer Artikel angelegt. `pfand_pro_einheit` und `aktiv` bestehender
Artikel werden NICHT angetastet (Pfand wird laut AGENTS.md separat vom
Organisator/per SQL gepflegt).

Nutzung:
    python import_speisekarte.py [--commit]

Ohne --commit ist es ein Trockenlauf (zeigt nur, was sich ändern würde).
"""
import argparse

from app import create_app
from app.models import db, Artikel, KATEGORIE_ESSEN, KATEGORIE_GETRAENK

# (name, kategorie, preis, reihenfolge) - Reihenfolge = Position auf der
# Preisliste innerhalb der Kategorie.
ARTIKEL = [
    # Getränke
    ("Apfelsaft/Cappy 0,25L", KATEGORIE_GETRAENK, 3.00, 1),
    ("Apfelsaft/Cappy gespritzt/Wasser 0,25L", KATEGORIE_GETRAENK, 3.00, 2),
    ("Limo 0,25L", KATEGORIE_GETRAENK, 3.00, 3),
    ("Mineralwasser 0,25L", KATEGORIE_GETRAENK, 3.00, 4),
    ("Red Bull", KATEGORIE_GETRAENK, 4.00, 5),
    ("Bier Radler 0,5L", KATEGORIE_GETRAENK, 4.50, 6),
    ("Bier Radler 0,33L", KATEGORIE_GETRAENK, 3.50, 7),
    ("Weiße Mischung", KATEGORIE_GETRAENK, 3.50, 8),
    ("Süße Mischung", KATEGORIE_GETRAENK, 3.50, 9),
    ("1/8 Wein", KATEGORIE_GETRAENK, 3.50, 10),
    ("Silowasser", KATEGORIE_GETRAENK, 4.50, 11),
    ("Vodka Bull/Cappy", KATEGORIE_GETRAENK, 4.50, 12),
    ("Barcardi/Whiskey Cola/Bull", KATEGORIE_GETRAENK, 4.50, 13),
    ("Skiwasser", KATEGORIE_GETRAENK, 4.50, 14),
    ("Flying Hirsch", KATEGORIE_GETRAENK, 4.50, 15),
    ("Jägermeister/Berliner Luft/Klopfer", KATEGORIE_GETRAENK, 3.50, 16),
    # Speisen
    ("½ Grillhendl mit Gebäck", KATEGORIE_ESSEN, 12.00, 1),
    ("Kotelette mit Kartoffelsalat", KATEGORIE_ESSEN, 15.00, 2),
    ("Bratwurst mit Gebäck", KATEGORIE_ESSEN, 7.00, 3),
    ("Portion Kartoffelsalat", KATEGORIE_ESSEN, 2.00, 4),
    ("Leberkäsesemmel (ab 19 Uhr)", KATEGORIE_ESSEN, 3.00, 5),
    # Kaffee/Kuchen
    ("Kaffee", KATEGORIE_ESSEN, 3.00, 6),
    ("Kuchen", KATEGORIE_ESSEN, 3.00, 7),
]


def importieren(commit: bool):
    app = create_app()
    with app.app_context():
        neu, aktualisiert, unveraendert = 0, 0, 0
        for name, kategorie, preis, reihenfolge in ARTIKEL:
            a = Artikel.query.filter_by(name=name).first()
            if a is None:
                print(f"# NEU: {name!r} ({kategorie}, {preis:.2f}€)")
                if commit:
                    db.session.add(Artikel(
                        name=name, kategorie=kategorie, preis=preis,
                        reihenfolge=reihenfolge,
                        punkte_pro_einheit=1 if kategorie == KATEGORIE_GETRAENK else 0,
                    ))
                neu += 1
            elif (a.kategorie, a.preis, a.reihenfolge) != (kategorie, preis, reihenfolge):
                print(f"# ÄNDERUNG: {name!r} "
                      f"{a.kategorie}/{a.preis:.2f}€/{a.reihenfolge} -> "
                      f"{kategorie}/{preis:.2f}€/{reihenfolge}")
                if commit:
                    a.kategorie = kategorie
                    a.preis = preis
                    a.reihenfolge = reihenfolge
                    a.punkte_pro_einheit = 1 if kategorie == KATEGORIE_GETRAENK else 0
                aktualisiert += 1
            else:
                unveraendert += 1

        if commit:
            db.session.commit()
            print(f"\n{neu} neu angelegt, {aktualisiert} aktualisiert, "
                  f"{unveraendert} unverändert. Gespeichert.")
        else:
            print(f"\nTROCKENLAUF: {neu} neu, {aktualisiert} würden aktualisiert, "
                  f"{unveraendert} unverändert. Nichts gespeichert (--commit fehlt).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", action="store_true",
                        help="Ohne diesen Schalter nur Trockenlauf")
    args = parser.parse_args()
    importieren(args.commit)
