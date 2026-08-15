"""Einmaliger Import der Teilnehmer-/Teamliste aus einer Excel-Datei.

Erwartet die Blätter "Teams" und "Läufer" wie in der vom User gepflegten
Anmeldeliste. Importiert nur Teams mit genau 4 zugeordneten Läufern
(per Startnummer abgeglichen, nicht per Namens-String - die Schreibweisen
weichen zwischen den Blättern teils ab). Reine Goldsponsor-Zeilen sowie
Teams ohne vollständige Läuferliste werden übersprungen.

Nutzung:
    python import_teilnehmer.py <pfad_zur_xlsx> [--event-datum YYYY-MM-DD] [--commit]

Ohne --commit ist es ein Trockenlauf (zeigt nur, was importiert würde, ohne
etwas in der Datenbank zu ändern). Bereits vorhandene Teams (gleiche
Startnummer) werden übersprungen, damit ein erneuter Lauf keine Duplikate
erzeugt.
"""
import argparse
import datetime
from collections import defaultdict

import openpyxl

from app import create_app
from app.models import db, Team, Mitglied

HAKEN = "☑"


def lade_teams_und_laeufer(pfad: str):
    wb = openpyxl.load_workbook(pfad, data_only=True)
    teams_ws = wb["Teams"]
    laeufer_ws = wb["Läufer"]

    teams = [r for r in teams_ws.iter_rows(min_row=2, values_only=True)
             if any(c is not None for c in r)]
    laeufer = [r for r in laeufer_ws.iter_rows(min_row=2, values_only=True)
               if any(c is not None for c in r)]

    laeufer_je_nummer = defaultdict(list)
    for r in laeufer:
        laeufer_je_nummer[r[0]].append(r)

    paare = []
    for t in teams:
        nummer, name, status = t[0], t[1], t[8]
        if not isinstance(nummer, int):
            continue                       # z.B. die "Reserve"-Zeile
        if status == "Goldsponsor":
            continue                       # kein startendes Team
        runner_rows = laeufer_je_nummer.get(nummer, [])
        # Manche Teams haben zwar 4 Zeilen reserviert, aber nicht alle mit
        # echtem Vor-/Nachnamen befüllt (z.B. nur der Kapitän eingetragen) -
        # das zählt NICHT als vollständige Laufliste.
        echte = [r for r in runner_rows if (r[3] or r[4])]
        if len(runner_rows) != 4 or len(echte) != 4:
            print(f"# {nummer} {name!r}: unvollständige Laufliste "
                  f"({len(echte)}/4 mit Namen) -> übersprungen")
            continue
        paare.append((t, runner_rows))
    return paare


def alter_am(geburtsdatum, stichtag: datetime.date):
    if not isinstance(geburtsdatum, datetime.datetime):
        return None
    g = geburtsdatum.date()
    return stichtag.year - g.year - ((stichtag.month, stichtag.day) < (g.month, g.day))


def importieren(pfad: str, stichtag: datetime.date, commit: bool):
    paare = lade_teams_und_laeufer(pfad)
    app = create_app()
    with app.app_context():
        neu, uebersprungen = 0, 0
        for t, runners in paare:
            nummer, name = t[0], t[1]
            if Team.query.filter_by(startnummer=nummer).first():
                print(f"# {nummer} {name!r}: Startnummer existiert schon, übersprungen")
                uebersprungen += 1
                continue

            telefon = (t[7] or "").strip()
            email = (t[6] or "").strip()
            kontakt = " · ".join(x for x in (telefon, email) if x)

            team = Team(
                name=name,
                startnummer=nummer,
                kontakt=kontakt,
                getraenk=(t[5] or "").strip(),
                bezahlt=(t[8] == "bezahlt"),
                haftungsausschluss=(t[9] == HAKEN),
            )
            for r in sorted(runners, key=lambda r: r[2] or 0):
                pos, vorname, nachname, geb = r[2], r[3], r[4], r[5]
                vorname, nachname = (vorname or "").strip(), (nachname or "").strip()
                team.mitglieder.append(Mitglied(
                    vorname=vorname, nachname=nachname,
                    name=f"{vorname} {nachname}".strip(),
                    alter=alter_am(geb, stichtag),
                    position=pos,
                    haftungsausschluss=(r[7] == HAKEN),
                    ausweis_kontrolliert=(r[8] == HAKEN),
                    einverstaendniserklaerung=(r[9] == HAKEN),
                ))
            minderjaehrige = [m.voller_name() for m in team.mitglieder if m.ist_minderjaehrig]
            hinweis = f"  -- MINDERJÄHRIG: {', '.join(minderjaehrige)}" if minderjaehrige else ""
            print(f"# {nummer} {name!r}: {len(team.mitglieder)} Läufer{hinweis}")

            if commit:
                db.session.add(team)
            neu += 1

        if commit:
            db.session.commit()
            print(f"\n{neu} Teams importiert, {uebersprungen} übersprungen "
                  "(Startnummer schon vorhanden). Gespeichert.")
        else:
            print(f"\nTROCKENLAUF: {neu} Teams würden importiert, "
                  f"{uebersprungen} übersprungen. Nichts gespeichert (--commit fehlt).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("xlsx_pfad")
    parser.add_argument("--event-datum", default="2026-08-22",
                        help="Stichtag für die Altersberechnung (YYYY-MM-DD)")
    parser.add_argument("--commit", action="store_true",
                        help="Ohne diesen Schalter nur Trockenlauf")
    args = parser.parse_args()
    importieren(args.xlsx_pfad, datetime.date.fromisoformat(args.event_datum), args.commit)
