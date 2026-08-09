"""Datenmodell für die Wettbewerbs-Organisation.

Kernbegriffe:
- Team:       eine teilnehmende Mannschaft (z.B. eine Wehr oder Gruppe)
- Disziplin:  eine Station/Aufgabe (Löschangriff, Staffellauf, ...)
- Ergebnis:   die Wertung eines Teams in einer Disziplin (Zeit + Fehlerpunkte)
- Startplatz: Startreihenfolge/Zeitplan eines Teams in einer Disziplin
"""
from __future__ import annotations

from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def _jetzt() -> datetime:
    return datetime.now(timezone.utc)


# Wertungsart einer Disziplin
WERTUNG_ZEIT = "zeit"      # niedrigste (Netto-)Zeit gewinnt
WERTUNG_PUNKTE = "punkte"  # höchste Punktzahl gewinnt


class Team(db.Model):
    __tablename__ = "team"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    wehr = db.Column(db.String(120), default="")          # Ort / Feuerwehr
    startnummer = db.Column(db.Integer)                    # optionale feste Nummer
    kontakt = db.Column(db.String(120), default="")
    notiz = db.Column(db.Text, default="")
    erstellt = db.Column(db.DateTime, default=_jetzt)

    ergebnisse = db.relationship("Ergebnis", back_populates="team",
                                 cascade="all, delete-orphan")
    startplaetze = db.relationship("Startplatz", back_populates="team",
                                   cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Team {self.name!r}>"


class Disziplin(db.Model):
    __tablename__ = "disziplin"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    beschreibung = db.Column(db.Text, default="")
    wertungsart = db.Column(db.String(20), default=WERTUNG_ZEIT)
    # Sekunden pro Fehlerpunkt (nur bei Zeit-Wertung relevant)
    strafsekunden_pro_fehler = db.Column(db.Float, default=0.0)
    reihenfolge = db.Column(db.Integer, default=0)         # Sortierung im Ablauf

    ergebnisse = db.relationship("Ergebnis", back_populates="disziplin",
                                 cascade="all, delete-orphan")
    startplaetze = db.relationship("Startplatz", back_populates="disziplin",
                                   cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Disziplin {self.name!r}>"


class Ergebnis(db.Model):
    __tablename__ = "ergebnis"

    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey("team.id"), nullable=False)
    disziplin_id = db.Column(db.Integer, db.ForeignKey("disziplin.id"),
                             nullable=False)

    zeit_sekunden = db.Column(db.Float)      # gestoppte Rohzeit
    punkte = db.Column(db.Float)             # bei Punkte-Wertung
    fehlerpunkte = db.Column(db.Integer, default=0)
    disqualifiziert = db.Column(db.Boolean, default=False)
    notiz = db.Column(db.String(200), default="")
    erfasst = db.Column(db.DateTime, default=_jetzt)

    team = db.relationship("Team", back_populates="ergebnisse")
    disziplin = db.relationship("Disziplin", back_populates="ergebnisse")

    __table_args__ = (
        db.UniqueConstraint("team_id", "disziplin_id", name="uq_team_disziplin"),
    )

    @property
    def nettozeit(self) -> float | None:
        """Zeit inkl. Strafsekunden für Fehlerpunkte."""
        if self.zeit_sekunden is None:
            return None
        strafe = (self.fehlerpunkte or 0) * (
            self.disziplin.strafsekunden_pro_fehler or 0.0)
        return self.zeit_sekunden + strafe


class Startplatz(db.Model):
    __tablename__ = "startplatz"

    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey("team.id"), nullable=False)
    disziplin_id = db.Column(db.Integer, db.ForeignKey("disziplin.id"),
                             nullable=False)
    startnummer = db.Column(db.Integer)      # Reihenfolge innerhalb der Disziplin
    startzeit = db.Column(db.String(20), default="")  # z.B. "10:30"
    heat = db.Column(db.String(40), default="")

    team = db.relationship("Team", back_populates="startplaetze")
    disziplin = db.relationship("Disziplin", back_populates="startplaetze")
