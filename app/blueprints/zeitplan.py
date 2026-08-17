"""Startlisten / Zeitplan je Disziplin."""
import random
from datetime import datetime, timedelta

from flask import (Blueprint, flash, redirect, render_template, request,
                   url_for)

from ..models import db, Team, Disziplin, Startplatz
from ..auth import darf, rolle_noetig

bp = Blueprint("zeitplan", __name__, url_prefix="/zeitplan")

BAHNEN = 4


@bp.route("/")
def uebersicht():
    disziplinen = Disziplin.query.order_by(Disziplin.reihenfolge,
                                            Disziplin.name).all()
    return render_template("zeitplan/uebersicht.html", disziplinen=disziplinen)


@bp.route("/disziplin/<int:disziplin_id>/rangliste", methods=["GET", "POST"])
@rolle_noetig("startrichter", "organisator")
def rangliste(disziplin_id: int):
    """Automatische Rangliste aus den erfassten Zeiten einer Runde (z.B.
    "Vorrunde"), plus die Möglichkeit, daraus gezielt Teams für die nächste
    Runde (Halbfinale, Platzierungslauf, Finale, ...) zu einem neuen Lauf
    zusammenzustellen. Die genaue Einteilung (z.B. welche Plätze gegeneinander
    laufen) bestimmt der Organisator selbst - die App liefert nur die
    Rangliste."""
    disziplin = db.get_or_404(Disziplin, disziplin_id)
    praefix = request.args.get("quelle", "Vorrunde").strip() or "Vorrunde"

    if request.method == "POST":
        team_ids = [_int_or_none(t) for t in request.form.getlist("team_id")]
        team_ids = [t for t in team_ids if t]
        neuer_heat = request.form.get("neuer_heat", "").strip()
        if not team_ids or not neuer_heat:
            flash("Bitte mindestens ein Team und einen Namen für den neuen "
                  "Lauf angeben.", "error")
        elif len(team_ids) > BAHNEN:
            flash(f"Ein Lauf hat maximal {BAHNEN} Bahnen - bitte höchstens "
                  f"{BAHNEN} Teams auswählen.", "error")
        else:
            for lane, team_id in enumerate(team_ids, start=1):
                db.session.add(Startplatz(
                    team_id=team_id, disziplin_id=disziplin.id,
                    startnummer=lane, heat=neuer_heat))
            db.session.commit()
            flash(f"Lauf „{neuer_heat}“ mit {len(team_ids)} Team(s) angelegt.", "ok")
        return redirect(url_for("zeitplan.rangliste", disziplin_id=disziplin.id,
                                quelle=praefix))

    platzierungen = _rangliste_berechnen(disziplin, praefix)
    vorhandene_praefixe = sorted({
        sp.heat.rsplit(" ", 1)[0] for sp in disziplin.startplaetze if sp.heat
    })
    return render_template("zeitplan/rangliste.html", disziplin=disziplin,
                           platzierungen=platzierungen, praefix=praefix,
                           vorhandene_praefixe=vorhandene_praefixe)


@bp.route("/startplatz/<int:startplatz_id>/loeschen", methods=["POST"])
@rolle_noetig("startrichter", "organisator")
def startplatz_loeschen(startplatz_id: int):
    sp = db.get_or_404(Startplatz, startplatz_id)
    disziplin_id = sp.disziplin_id
    db.session.delete(sp)
    db.session.commit()
    flash("Startplatz gelöscht.", "ok")
    return redirect(url_for("zeitplan.disziplin", disziplin_id=disziplin_id))


@bp.route("/disziplin/<int:disziplin_id>", methods=["GET", "POST"])
def disziplin(disziplin_id: int):
    disziplin = db.get_or_404(Disziplin, disziplin_id)

    if request.method == "POST":
        if not darf("startrichter", "organisator"):
            flash("Zum Ändern der Startliste brauchst du die Rolle "
                  "Startrichter oder Organisator (oder Administrator).", "error")
            return redirect(url_for("auth.login",
                                    next=url_for("zeitplan.disziplin",
                                                 disziplin_id=disziplin.id)))
        aktion = request.form.get("aktion")
        if aktion == "auto":
            _startliste_automatisch(disziplin)
            flash("Startliste aus allen Mannschaften erzeugt.", "ok")
        elif aktion == "auslosen":
            anzahl_heats = _vorrunde_auslosen(disziplin)
            flash(f"Vorrunde neu ausgelost: {anzahl_heats} Läufe für alle "
                  "Mannschaften (bisherige Startliste dieser Disziplin wurde "
                  "ersetzt).", "ok")
        elif aktion == "hinzufuegen":
            _startplatz_hinzufuegen(disziplin)
            flash("Startplatz hinzugefügt.", "ok")
        elif aktion == "speichern":
            _startzeiten_speichern(disziplin)
            flash("Startliste gespeichert.", "ok")
        elif aktion == "einstellungen":
            dauer = _float_or_none(request.form.get("dauer_pro_lauf_min"))
            disziplin.dauer_pro_lauf_min = dauer if dauer and dauer > 0 else 7.0
            disziplin.startzeit_erster_lauf = request.form.get(
                "startzeit_erster_lauf", "").strip()
            db.session.commit()
            flash("Zeitplan-Einstellungen gespeichert.", "ok")
        elif aktion == "startzeiten_auto":
            _startzeiten_automatisch_berechnen(disziplin)
        elif aktion == "startzeiten_anpassen":
            _startzeiten_anpassen(disziplin)
        return redirect(url_for("zeitplan.disziplin", disziplin_id=disziplin.id))

    startplaetze = (Startplatz.query
                    .filter_by(disziplin_id=disziplin.id)
                    .order_by(Startplatz.heat, Startplatz.startnummer).all())
    teams = Team.query.order_by(Team.startnummer, Team.name).all()
    return render_template("zeitplan/disziplin.html", disziplin=disziplin,
                           startplaetze=startplaetze, teams=teams)


def _startliste_automatisch(disziplin: Disziplin) -> None:
    """Legt für jedes Team ohne Startplatz einen an (fortlaufende Nummer)."""
    vorhanden = {sp.team_id for sp in disziplin.startplaetze}
    naechste = (max((sp.startnummer or 0 for sp in disziplin.startplaetze),
                    default=0) + 1)
    for team in Team.query.order_by(Team.startnummer, Team.name):
        if team.id in vorhanden:
            continue
        db.session.add(Startplatz(team_id=team.id, disziplin_id=disziplin.id,
                                  startnummer=naechste))
        naechste += 1
    db.session.commit()


def _startzeiten_speichern(disziplin: Disziplin) -> None:
    for sp in disziplin.startplaetze:
        sp.startnummer = _int_or_none(request.form.get(f"nr_{sp.id}"))
        sp.startzeit = request.form.get(f"zeit_{sp.id}", "").strip()
        sp.heat = request.form.get(f"heat_{sp.id}", "").strip()
        sp.ergebnis_sekunden = _float_or_none(
            request.form.get(f"erg_{sp.id}", ""))
    db.session.commit()


def _startplatz_hinzufuegen(disziplin: Disziplin) -> None:
    """Fügt manuell einen einzelnen Startplatz hinzu (z.B. um ein Team
    einem weiteren Lauf zuzuordnen oder eine Auslosung von Hand zu
    ergänzen)."""
    team_id = _int_or_none(request.form.get("team_id"))
    if not team_id:
        return
    db.session.add(Startplatz(
        team_id=team_id, disziplin_id=disziplin.id,
        startnummer=_int_or_none(request.form.get("neu_nr")),
        startzeit=request.form.get("neu_zeit", "").strip(),
        heat=request.form.get("neu_heat", "").strip(),
    ))
    db.session.commit()


def _vorrunde_auslosen(disziplin: Disziplin, bahnen: int = BAHNEN,
                       runden: int = 2) -> int:
    """Lost alle Mannschaften zufällig in Gruppen zu je `bahnen` Teams aus,
    jedes Team `runden`-mal (Standard: 2, passend zum Vorrunden-Format des
    Siloplanen-Race). Ersetzt eine vorhandene Startliste dieser Disziplin
    komplett. Versucht (bestmöglich, nicht garantiert), dass kein Team in
    beiden Runden auf dieselben Gegner trifft. Gibt die Anzahl erzeugter
    Läufe zurück.
    """
    teams = Team.query.order_by(Team.startnummer, Team.name).all()
    if len(teams) < 2:
        return 0

    Startplatz.query.filter_by(disziplin_id=disziplin.id).delete()

    bisherige_gegner = {t.id: set() for t in teams}
    heat_nr = 0

    for _runde in range(runden):
        gruppen = None
        for _versuch in range(50):
            gemischt = teams[:]
            random.shuffle(gemischt)
            kandidat = [gemischt[i:i + bahnen]
                       for i in range(0, len(gemischt), bahnen)]
            konflikte = sum(
                1
                for gruppe in kandidat
                for i, t1 in enumerate(gruppe)
                for t2 in gruppe[i + 1:]
                if t2.id in bisherige_gegner[t1.id]
            )
            if gruppen is None or konflikte == 0:
                gruppen = kandidat
            if konflikte == 0:
                break

        for gruppe in gruppen:
            for t1 in gruppe:
                bisherige_gegner[t1.id].update(
                    t2.id for t2 in gruppe if t2 is not t1)
            heat_nr += 1
            for lane, team in enumerate(gruppe, start=1):
                db.session.add(Startplatz(
                    team_id=team.id, disziplin_id=disziplin.id,
                    startnummer=lane, heat=f"Vorrunde {heat_nr}"))

    db.session.commit()
    return heat_nr


def _int_or_none(wert):
    try:
        return int(wert)
    except (TypeError, ValueError):
        return None


def _float_or_none(wert):
    try:
        wert = (wert or "").replace(",", ".").strip()
        return float(wert) if wert else None
    except (TypeError, ValueError):
        return None


def _rangliste_berechnen(disziplin: Disziplin, praefix: str) -> list[dict]:
    """Rangliste für alle Läufe einer Disziplin, deren Heat-Name mit
    `praefix` beginnt (z.B. "Vorrunde"): je Team die Summe der
    `ergebnis_sekunden` über alle passenden Läufe. Nur Teams, bei denen ALLE
    passenden Läufe eine erfasste Zeit haben, werden gerankt - andere
    erscheinen als "unvollständig" ohne Rang. Sortiert aufsteigend (schneller
    = besser).
    """
    passende = [sp for sp in disziplin.startplaetze
               if sp.heat and sp.heat.startswith(praefix)]
    je_team: dict[int, list[Startplatz]] = {}
    for sp in passende:
        je_team.setdefault(sp.team_id, []).append(sp)

    vollstaendig, unvollstaendig = [], []
    for team_id, eintraege in je_team.items():
        team = eintraege[0].team
        zeiten = [e.ergebnis_sekunden for e in eintraege]
        if all(z is not None for z in zeiten):
            vollstaendig.append({
                "team": team, "gesamtzeit": sum(zeiten),
                "laeufe": eintraege, "vollstaendig": True,
            })
        else:
            unvollstaendig.append({
                "team": team, "gesamtzeit": None,
                "laeufe": eintraege, "vollstaendig": False,
            })

    vollstaendig.sort(key=lambda e: e["gesamtzeit"])
    for i, e in enumerate(vollstaendig, start=1):
        e["rang"] = i
    for e in unvollstaendig:
        e["rang"] = None

    return vollstaendig + unvollstaendig

# ── Automatische Startzeit-Berechnung ─────────────────────────────────────────


def _parse_uhrzeit(text: str) -> datetime | None:
    """Parst 'HH:MM' -> datetime (heute + Uhrzeit). None bei Fehler."""
    text = (text or "").strip()
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    return None


def _format_uhrzeit(dt: datetime) -> str:
    return dt.strftime("%H:%M")


def _heats_in_reihenfolge(disziplin: Disziplin) -> list[str]:
    """Einzigartige Heat-Namen in numerischer Reihenfolge (Vorrunde 1, 2, ...
    10, 11, ... – nicht alphabetisch)."""
    seen: dict[str, None] = {}
    for sp in (Startplatz.query
               .filter_by(disziplin_id=disziplin.id)
               .order_by(Startplatz.heat, Startplatz.startnummer).all()):
        key = sp.heat or ""
        if key not in seen:
            seen[key] = None
    heats = list(seen.keys())

    def _sort_key(name: str):
        import re
        zahlen = re.findall(r"\d+", name)
        return tuple(int(z) for z in zahlen) if zahlen else (0,)

    heats.sort(key=_sort_key)
    return heats


def _startzeiten_automatisch_berechnen(disziplin: Disziplin) -> None:
    """Berechnet Startzeiten fuer alle Heats dieser Disziplin anhand der
    Einstellungen dauer_pro_lauf_min und startzeit_erster_lauf."""
    start = _parse_uhrzeit(disziplin.startzeit_erster_lauf or "")
    if start is None:
        flash("Bitte zuerst eine Startzeit fuer den ersten Lauf eintragen "
              "(z.B. 10:00).", "error")
        return
    dauer = timedelta(minutes=float(disziplin.dauer_pro_lauf_min or 7.0))
    heats = _heats_in_reihenfolge(disziplin)
    if not heats:
        flash("Keine Laeufe vorhanden – zuerst Startliste erstellen.", "error")
        return
    for i, heat in enumerate(heats):
        zeit = _format_uhrzeit(start + i * dauer)
        for sp in Startplatz.query.filter_by(disziplin_id=disziplin.id,
                                              heat=heat).all():
            sp.startzeit = zeit
    db.session.commit()
    flash(f"Startzeiten automatisch berechnet: {len(heats)} Laeufe, "
          f"Start {heats[0]} um {_format_uhrzeit(start)}, "
          f"jeweils {disziplin.dauer_pro_lauf_min:.0f} Min Abstand.", "ok")


def _startzeiten_anpassen(disziplin: Disziplin) -> None:
    """Passt die Startzeiten ab einem bestimmten Lauf an. Der User gibt an:
    - ab_welchem_heat: Name des Laufs, ab dem angepasst wird
    - neue_startzeit: tatsaechliche/geplante Startzeit dieses Laufs
    Alle folgenden Laeufe bekommen neue_startzeit + n*dauer als Startzeit."""
    ab_heat = request.form.get("ab_welchem_heat", "").strip()
    neue_zeit = request.form.get("neue_startzeit", "").strip()
    start = _parse_uhrzeit(neue_zeit)
    if start is None:
        flash("Bitte eine gueltige neue Startzeit angeben (z.B. 11:15).",
              "error")
        return
    heats = _heats_in_reihenfolge(disziplin)
    if ab_heat not in heats:
        flash(f"Lauf '{ab_heat}' nicht gefunden. Verfuegbare Laeufe: "
              f"{', '.join(heats[:5])}", "error")
        return
    dauer = timedelta(minutes=float(disziplin.dauer_pro_lauf_min or 7.0))
    idx = heats.index(ab_heat)
    for i, heat in enumerate(heats[idx:], start=0):
        zeit = _format_uhrzeit(start + i * dauer)
        for sp in Startplatz.query.filter_by(disziplin_id=disziplin.id,
                                              heat=heat).all():
            sp.startzeit = zeit
    db.session.commit()
    angepasst = len(heats) - idx
    flash(f"Startzeiten angepasst: {angepasst} Lauf/Laeufe ab '{ab_heat}' "
          f"ab {_format_uhrzeit(start)} neu berechnet.", "ok")