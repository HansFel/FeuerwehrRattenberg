"""Legt 20 Test-Mannschaften mit je 4 Teilnehmern (Fantasienamen) sowie eine
Beispiel-Speisekarte (Essen &amp; Getränke) an.

Aufruf:  python seed_testdaten.py
Idempotent: bereits vorhandene Namen werden übersprungen.
NUR für Test-/Demodaten gedacht – nicht in Produktion ausführen.
"""
import random

from app import create_app
from app.models import (db, Team, Mitglied, Artikel, KATEGORIE_ESSEN,
                        KATEGORIE_GETRAENK)

TEAM_NAMEN = [
    "Die Löschdrachen", "Feuerteufel Rattenberg", "Wasserratten",
    "Schlauchpiraten", "Die Funkenflieger", "Hydranten-Helden",
    "Rote Blitze", "Die Spritzenmeister", "Flammenjäger", "Die Nassmacher",
    "Kübelspritzen-Kommando", "Die Glutstürmer", "Sirenenzwerge",
    "Steigrohr-Rebellen", "Pumpen-Power", "Die Rauchmelder",
    "Feuersalamander", "Die Schaumschläger", "Blaulicht-Bande",
    "Die Funkenmariechen",
]

VORNAMEN = [
    "Anna", "Bernd", "Clara", "Dieter", "Emil", "Franziska", "Georg",
    "Hannah", "Ingo", "Julia", "Klaus", "Lena", "Moritz", "Nina", "Otto",
    "Petra", "Quirin", "Rosa", "Stefan", "Theresa", "Udo", "Verena",
    "Werner", "Xaver", "Yvonne", "Zeno",
]
NACHNAMEN = [
    "Huber", "Maier", "Gruber", "Bauer", "Steiner", "Moser", "Wagner",
    "Pichler", "Hofer", "Berger", "Fuchs", "Egger", "Brunner", "Lechner",
    "Wimmer", "Aigner", "Ebner", "Reiter", "Schwarz", "Winkler",
]
SPITZNAMEN = [
    "Blitz", "Turbo", "Schorsch", "Hexe", "Bär", "Flitzer", "Locke",
    "Zwerg", "Hammer", "Sepp", "Fux", "Riese", "Motte", "Racker", "Brummi",
    "Pfeil", "Wuchtel", "Spatz", "Goliath", "Floh",
]


SPEISEKARTE = [
    # (Name, Kategorie, Preis in €, Punkte fürs Team pro Einheit)
    ("Bier (Krügerl)", KATEGORIE_GETRAENK, 4.00, 2),
    ("Bier (Seidel)", KATEGORIE_GETRAENK, 2.50, 1),
    ("Almdudler", KATEGORIE_GETRAENK, 2.50, 1),
    ("Cola / Fanta / Sprite", KATEGORIE_GETRAENK, 2.50, 1),
    ("Mineralwasser", KATEGORIE_GETRAENK, 2.00, 1),
    ("Apfelsaft gespritzt", KATEGORIE_GETRAENK, 2.50, 1),
    ("Roter Spritzer", KATEGORIE_GETRAENK, 3.00, 1),
    ("Obstler (2cl)", KATEGORIE_GETRAENK, 2.00, 3),
    ("Grillhendl (halb)", KATEGORIE_ESSEN, 8.00, 2),
    ("Bratwurst mit Brot", KATEGORIE_ESSEN, 4.50, 1),
    ("Leberkässemmel", KATEGORIE_ESSEN, 3.50, 1),
    ("Gulasch mit Brot", KATEGORIE_ESSEN, 7.00, 1),
    ("Käsekrainer", KATEGORIE_ESSEN, 4.00, 1),
    ("Pommes", KATEGORIE_ESSEN, 3.00, 1),
    ("Kuchen (Stück)", KATEGORIE_ESSEN, 2.50, 1),
    ("Eis (Kugel)", KATEGORIE_ESSEN, 1.50, 0),
]


def _telefon(rng: random.Random) -> str:
    vorwahl = rng.choice(["0660", "0664", "0676", "0699"])
    return f"{vorwahl} {rng.randint(100, 999)} {rng.randint(1000, 9999)}"


def teams_anlegen() -> int:
    rng = random.Random(120)          # fester Seed → reproduzierbar
    angelegt = 0
    for nr, teamname in enumerate(TEAM_NAMEN, start=1):
        if Team.query.filter_by(name=teamname).first():
            continue
        team = Team(name=teamname, wehr="Rattenberg", startnummer=nr)
        vornamen = rng.sample(VORNAMEN, 4)
        nachnamen = rng.sample(NACHNAMEN, 4)
        spitznamen = rng.sample(SPITZNAMEN, 4)
        for pos in range(4):
            vn, nn = vornamen[pos], nachnamen[pos]
            team.mitglieder.append(Mitglied(
                vorname=vn, nachname=nn, spitzname=spitznamen[pos],
                telefon=_telefon(rng), alter=rng.randint(16, 58),
                position=pos + 1, name=f"{vn} {nn}"))
        db.session.add(team)
        angelegt += 1
    db.session.commit()
    return angelegt


def speisekarte_anlegen() -> int:
    angelegt = 0
    for reihenfolge, (name, kategorie, preis, punkte) in enumerate(SPEISEKARTE):
        if Artikel.query.filter_by(name=name).first():
            continue
        db.session.add(Artikel(name=name, kategorie=kategorie, preis=preis,
                               punkte_pro_einheit=punkte, aktiv=True,
                               reihenfolge=reihenfolge))
        angelegt += 1
    db.session.commit()
    return angelegt


def hauptteil() -> None:
    teams = teams_anlegen()
    print(f"{teams} Test-Teams angelegt. Teams gesamt: {Team.query.count()}")
    artikel = speisekarte_anlegen()
    print(f"{artikel} Speisekarten-Artikel angelegt. "
         f"Artikel gesamt: {Artikel.query.count()}")


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        hauptteil()
