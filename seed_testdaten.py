"""Legt 20 Test-Mannschaften mit je 4 Teilnehmern (Fantasienamen) an.

Aufruf:  python seed_testdaten.py
Idempotent: bereits vorhandene Team-Namen werden übersprungen.
NUR für Test-/Demodaten gedacht – nicht in Produktion ausführen.
"""
import random

from app import create_app
from app.models import db, Team, Mitglied

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


def _telefon(rng: random.Random) -> str:
    vorwahl = rng.choice(["0660", "0664", "0676", "0699"])
    return f"{vorwahl} {rng.randint(100, 999)} {rng.randint(1000, 9999)}"


def hauptteil() -> None:
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
    print(f"{angelegt} Test-Teams angelegt. Teams gesamt: {Team.query.count()}")


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        hauptteil()
