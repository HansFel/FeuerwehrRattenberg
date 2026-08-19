"""PDF-Ausdrucke: Gesamtwertung, Einzelranglisten, Startlisten.

Erzeugt echte, herunterladbare PDF-Dateien (reportlab) für Aushang und
Siegerehrung.
"""
import io
from datetime import date

from flask import Blueprint, Response

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                Paragraph, Spacer)

from ..models import db, Team, Disziplin, Startplatz, WERTUNG_ZEIT
from ..wertung import rangliste_disziplin, gesamtwertung_vollstaendig, format_zeit
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


def _tabelle(daten: list[list], breiten: list[float]) -> Table:
    t = Table(daten, colWidths=breiten, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), GRAU),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f2f2")]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


@bp.route("/gesamtwertung.pdf")
def gesamt():
    teams = Team.query.all()
    disziplinen = Disziplin.query.order_by(Disziplin.reihenfolge).all()
    daten = [["Rang", "Mannschaft", "Wehr / Ort", "Rangpunkte",
             "Getränkepunkte", "Strafsek.", "Gemessene Zeit", "Gesamtzeit"]]
    for z in gesamtwertung_vollstaendig(teams, disziplinen):
        rang = str(z["rang"]) + (" (vorl.)" if z["finaler_platz"] is None else "")
        daten.append([rang, z["team"].name, z["team"].wehr or "",
                      str(z["punkte"]), str(z["getraenkepunkte"]),
                      str(round(z["strafsekunden"])),
                      format_zeit(z["gemessene_zeit"]),
                      format_zeit(z["gesamtzeit"])])
    tabelle = _tabelle(daten, [20 * mm, 30 * mm, 26 * mm, 18 * mm,
                               20 * mm, 16 * mm, 22 * mm, 22 * mm])
    return _dokument("Gesamtwertung", [tabelle], "gesamtwertung.pdf")


@bp.route("/team_challenge.pdf")
def team_challenge():
    """Team Challenge als PDF: Getraenkepunkte + Fanpunkte je Team, gereiht."""
    teams = Team.query.order_by(Team.startnummer, Team.name).all()
    gp = {}
    for pos in BestellPosition.query.all():
        if pos.team_id and pos.punkte_gesamt:
            gp[pos.team_id] = gp.get(pos.team_id, 0) + pos.punkte_gesamt
    daten = [["Rang", "Mannschaft", "Wehr / Ort",
              "Getraenkepunkte", "Fanpunkte", "Gesamt"]]
    eintraege = []
    for t in teams:
        g = gp.get(t.id, 0)
        f = t.fanpunkte or 0
        eintraege.append((t, g, f, g + f))
    eintraege.sort(key=lambda e: e[3], reverse=True)
    for i, (t, g, f, ges) in enumerate(eintraege, start=1):
        daten.append([str(i), t.name, t.wehr or "",
                      str(g), str(f), str(ges)])
    tabelle = _tabelle(daten, [18 * mm, 35 * mm, 30 * mm,
                               25 * mm, 22 * mm, 20 * mm])
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
    startplaetze = (Startplatz.query.filter_by(disziplin_id=d.id)
                    .order_by(Startplatz.startnummer).all())
    daten = [["Start-Nr.", "Mannschaft", "Wehr / Ort", "Startzeit", "Heat"]]
    for sp in startplaetze:
        daten.append([str(sp.startnummer if sp.startnummer is not None else ""),
                      sp.team.name, sp.team.wehr or "", sp.startzeit or "",
                      sp.heat or ""])
    tabelle = _tabelle(daten, [20 * mm, 62 * mm, 50 * mm, 24 * mm, 18 * mm])
    return _dokument(f"Startliste – {d.name}", [tabelle],
                     f"startliste_{disziplin_id}.pdf")