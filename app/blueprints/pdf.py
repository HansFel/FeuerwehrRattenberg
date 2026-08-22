"""PDF-Ausdrucke: Gesamtwertung, Einzelranglisten, Startlisten.

Erzeugt echte, herunterladbare PDF-Dateien (reportlab) für Aushang und
Siegerehrung.
"""
import io
import re
from datetime import date
from xml.sax.saxutils import escape

from flask import Blueprint, Response

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                Paragraph, Spacer)

from ..models import db, Team, Disziplin, Startplatz, WERTUNG_ZEIT
from ..wertung import (rangliste_disziplin, gesamtwertung_vollstaendig,
                       format_zeit, beste_einzelzeit)
from ..models import BestellPosition

bp = Blueprint("pdf", __name__, url_prefix="/pdf")

ROT = colors.HexColor("#c62828")
GRAU = colors.HexColor("#37474f")


def _dokument(titel: str, elemente: list, dateiname: str) -> Response:
    puffer = io.BytesIO()
    doc = SimpleDocTemplate(puffer, pagesize=A4,
                            topMargin=18 * mm, bottomMargin=18 * mm,
                            leftMargin=18 * mm, rightMargin=18 * mm,
                            title=titel)
    stile = getSampleStyleSheet()
    kopf = stile["Title"]
    kopf.textColor = ROT
    unter = stile["Normal"]

    story = [
        Paragraph("120 Jahre Feuerwehr Rattenberg", unter),
        Paragraph(titel, kopf),
        Paragraph(f"Stand: {date.today().strftime('%d.%m.%Y')}", unter),
        Spacer(1, 8 * mm),
    ]
    story.extend(elemente)
    doc.build(story)

    puffer.seek(0)
    return Response(
        puffer.getvalue(),
        mimetype="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{dateiname}"'},
    )


def _tabelle(daten: list[list], breiten: list[float],
              text_spalten: tuple[int, ...] = (1, 2)) -> Table:
    kopf_stil = ParagraphStyle(
        "Tabellenkopf", fontName="Helvetica-Bold", fontSize=8.5,
        leading=10, textColor=colors.white, alignment=TA_CENTER,
        splitLongWords=True,
    )
    text_stil = ParagraphStyle(
        "Tabellentext", fontName="Helvetica", fontSize=8,
        leading=9.5, textColor=colors.black, alignment=TA_LEFT,
        splitLongWords=True,
    )
    zentriert_stil = ParagraphStyle(
        "Tabellenwert", parent=text_stil, alignment=TA_CENTER,
    )

    # Paragraph statt nacktem String: lange Mannschafts-/Ortsnamen werden
    # innerhalb ihrer Spalte umgebrochen und können nie in die Nachbarspalte
    # hineinlaufen. Zahlen und kurze Werte werden mittig ausgerichtet.
    aufbereitet = []
    for zeilen_index, zeile in enumerate(daten):
        neue_zeile = []
        for spalten_index, wert in enumerate(zeile):
            stil = kopf_stil if zeilen_index == 0 else (
                text_stil if spalten_index in text_spalten else zentriert_stil)
            text = escape(str(wert if wert is not None else ""))
            neue_zeile.append(Paragraph(text, stil))
        aufbereitet.append(neue_zeile)

    t = Table(aufbereitet, colWidths=breiten, repeatRows=1,
              hAlign="CENTER")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), GRAU),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f2f2")]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


@bp.route("/gesamtwertung.pdf")
def gesamt():
    teams = Team.query.all()
    disziplinen = Disziplin.query.order_by(Disziplin.reihenfolge).all()
    daten = [["Rang", "Mannschaft"]]
    for z in gesamtwertung_vollstaendig(teams, disziplinen):
        rang = str(z["rang"]) + (" (vorl.)" if z["finaler_platz"] is None else "")
        daten.append([rang, z["team"].name])
    tabelle = _tabelle(daten, [25 * mm, 145 * mm])
    elemente = []
    einzelzeiten = beste_einzelzeit()
    if einzelzeiten:
        normal = getSampleStyleSheet()["Normal"]
        zeilen = []
        for rang, einzelzeit in enumerate(einzelzeiten, start=1):
            lauf_name = einzelzeit["lauf"].bezeichnung or (
                "Lauf " + str(einzelzeit["lauf"].id))
            zeilen.append(
                f"<b>{rang}.</b> {escape(einzelzeit['laeufer_name'])} · "
                f"{escape(einzelzeit['team'].name)} · "
                f"<b>{escape(format_zeit(einzelzeit['zeit']))}</b><br/>"
                f"{escape(lauf_name)} · Bahn {einzelzeit['bahn_nr']} · "
                f"Läufer {einzelzeit['laeufer_nr']}")
        elemente.extend([
            Paragraph(
                "<b>Die 3 besten Einzelzeiten:</b><br/>"
                f"<b>Bestzeit aus {escape(einzelzeiten[0]['rundenherkunft'])}</b><br/>" +
                "<br/>".join(zeilen), normal),
            Spacer(1, 5 * mm),
        ])
    elemente.append(tabelle)
    return _dokument("Gesamtwertung", elemente, "gesamtwertung.pdf")


@bp.route("/team_challenge.pdf")
def team_challenge():
    """Team Challenge als PDF: Getraenkepunkte + Fanpunkte je Team, gereiht."""
    teams = Team.query.order_by(Team.startnummer, Team.name).all()
    gp = {}
    for pos in BestellPosition.query.all():
        if pos.team_id and pos.punkte_gesamt:
            gp[pos.team_id] = gp.get(pos.team_id, 0) + pos.punkte_gesamt
    daten = [["Rang", "Mannschaft", "Wehr / Ort",
              "Getränkepunkte", "Fanpunkte", "Gesamt"]]
    eintraege = []
    for t in teams:
        g = gp.get(t.id, 0)
        f = t.fanpunkte or 0
        eintraege.append((t, g, f, g + f))
    eintraege.sort(key=lambda e: (
        -e[3], (e[0].name or "").casefold(),
        (e[0].wehr or "").casefold(),
    ))
    for i, (t, g, f, ges) in enumerate(eintraege, start=1):
        daten.append([str(i), t.name, t.wehr or "",
                      str(g), str(f), str(ges)])
    tabelle = _tabelle(daten, [18 * mm, 38 * mm, 34 * mm,
                               28 * mm, 24 * mm, 22 * mm])
    return _dokument("Team Challenge", [tabelle], "team_challenge.pdf")


@bp.route("/disziplin/<int:disziplin_id>.pdf")
def disziplin(disziplin_id: int):
    d = db.get_or_404(Disziplin, disziplin_id)
    ist_zeit = d.wertungsart == WERTUNG_ZEIT
    kopf = "Nettozeit" if ist_zeit else "Punkte"
    daten = [["Rang", "Mannschaft", "Wehr / Ort", kopf, "Fehler"]]
    for p in rangliste_disziplin(d):
        if p.ergebnis is None:
            continue
        if p.ergebnis.disqualifiziert:
            wert = "DSQ"
        elif ist_zeit:
            wert = format_zeit(p.wert)
        else:
            wert = "" if p.wert is None else str(p.wert)
        daten.append([str(p.rang or "–"), p.team.name, p.team.wehr or "",
                      wert, str(p.ergebnis.fehlerpunkte or 0)])
    tabelle = _tabelle(daten, [16 * mm, 62 * mm, 50 * mm, 30 * mm, 16 * mm])
    return _dokument(f"Rangliste – {d.name}", [tabelle],
                     f"rangliste_{disziplin_id}.pdf")


@bp.route("/startliste/<int:disziplin_id>.pdf")
def startliste(disziplin_id: int):
    d = db.get_or_404(Disziplin, disziplin_id)
    startplaetze = Startplatz.query.filter_by(disziplin_id=d.id).all()

    def sortierschluessel(sp):
        zahlen = tuple(int(z) for z in re.findall(r"\d+", sp.heat or ""))
        return (zahlen or (0,), sp.startnummer if sp.startnummer is not None else 999,
                (sp.team.name or "").casefold(),
                (sp.team.wehr or "").casefold())

    startplaetze.sort(key=sortierschluessel)
    daten = [["Lauf", "Startzeit", "Bahn", "Mannschaft", "Wehr / Ort"]]
    for sp in startplaetze:
        daten.append([sp.heat or "", sp.startzeit or "",
                      str(sp.startnummer if sp.startnummer is not None else ""),
                      sp.team.name, sp.team.wehr or ""])
    tabelle = _tabelle(daten, [38 * mm, 22 * mm, 14 * mm, 58 * mm, 42 * mm],
                       text_spalten=(3, 4))
    return _dokument(f"Startliste – {d.name}", [tabelle],
                     f"startliste_{disziplin_id}.pdf")
