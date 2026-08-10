"""Datenmodell für die Wettbewerbs-Organisation.

Kernbegriffe:
- Team:       eine teilnehmende Mannschaft (z.B. eine Wehr oder Gruppe)
- Disziplin:  eine Station/Aufgabe (Löschangriff, Staffellauf, ...)
- Ergebnis:   die Wertung eines Teams in einer Disziplin (Zeit + Fehlerpunkte)
- Startplatz: Startreihenfolge/Zeitplan eines Teams in einer Disziplin
"""
from __future__ import annotations

from datetime import datetime, timezone

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


def _jetzt() -> datetime:
    return datetime.now(timezone.utc)


# Rollen der Organisator-Mannschaft (Konzept aus MGRSoftware übernommen).
# Der Administrator hat implizit alle Rechte.
ROLLEN = {
    "administrator": "Administrator",
    "organisator": "Organisator",
    "startrichter": "Startrichter",
    "punkterichter": "Punkterichter",
}


class Benutzer(UserMixin, db.Model):
    """Mitglied der Organisator-Mannschaft mit Login und Rollen."""
    __tablename__ = "benutzer"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    name = db.Column(db.String(120), default="")      # Anzeigename
    password_hash = db.Column(db.String(255))
    aktiv = db.Column(db.Boolean, default=True)
    erstellt = db.Column(db.DateTime, default=_jetzt)
    letzter_login = db.Column(db.DateTime)

    rollen = db.relationship("BenutzerRolle", back_populates="benutzer",
                             cascade="all, delete-orphan")

    def set_password(self, passwort: str) -> None:
        self.password_hash = generate_password_hash(passwort)

    def check_password(self, passwort: str) -> bool:
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, passwort)

    @property
    def rollen_namen(self) -> list[str]:
        return [r.rolle for r in self.rollen]

    def ist_admin(self) -> bool:
        return "administrator" in self.rollen_namen

    def darf(self, *erlaubte_rollen: str) -> bool:
        """True, wenn Administrator oder eine der erlaubten Rollen vorhanden."""
        if self.ist_admin():
            return True
        return any(r in self.rollen_namen for r in erlaubte_rollen)

    def __repr__(self) -> str:
        return f"<Benutzer {self.username!r}>"


class Anforderung(db.Model):
    """Wunsch/Regel/Anforderung der Administratoren für die Weiterentwicklung."""
    __tablename__ = "anforderung"

    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.Text, nullable=False)
    autor = db.Column(db.String(80), default="")
    erledigt = db.Column(db.Boolean, default=False)
    erstellt = db.Column(db.DateTime, default=_jetzt)

    def __repr__(self) -> str:
        return f"<Anforderung {self.id} erledigt={self.erledigt}>"


class Sicherung(db.Model):
    """Metadaten einer Datensicherung (gzip-Kopie der SQLite-Datenbank)."""
    __tablename__ = "sicherung"

    id = db.Column(db.Integer, primary_key=True)
    dateiname = db.Column(db.String(200), nullable=False)
    dateigroesse = db.Column(db.Integer, default=0)
    checksum = db.Column(db.String(64))               # SHA-256
    typ = db.Column(db.String(30), default="manuell")  # manuell/vor-wiederherstellung/upload
    erstellt_von = db.Column(db.String(80), default="")  # Benutzername
    erstellt = db.Column(db.DateTime, default=_jetzt)

    @property
    def groesse_formatiert(self) -> str:
        größe = self.dateigroesse or 0
        if größe < 1024:
            return f"{größe} B"
        if größe < 1024 * 1024:
            return f"{größe / 1024:.1f} KB"
        return f"{größe / (1024 * 1024):.1f} MB"

    def __repr__(self) -> str:
        return f"<Sicherung {self.dateiname!r}>"


class BenutzerRolle(db.Model):
    __tablename__ = "benutzer_rolle"

    id = db.Column(db.Integer, primary_key=True)
    benutzer_id = db.Column(db.Integer, db.ForeignKey("benutzer.id"),
                            nullable=False)
    rolle = db.Column(db.String(40), nullable=False)

    benutzer = db.relationship("Benutzer", back_populates="rollen")

    __table_args__ = (
        db.UniqueConstraint("benutzer_id", "rolle", name="uq_benutzer_rolle"),
    )


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
    mitglieder = db.relationship("Mitglied", back_populates="team",
                                 cascade="all, delete-orphan",
                                 order_by="Mitglied.position")

    def __repr__(self) -> str:
        return f"<Team {self.name!r}>"


class Mitglied(db.Model):
    """Eine Person eines Teams. Ein Team hat bis zu 4 Mitglieder."""
    __tablename__ = "mitglied"

    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey("team.id"), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    position = db.Column(db.Integer, default=1)   # 1..4

    team = db.relationship("Team", back_populates="mitglieder")

    def __repr__(self) -> str:
        return f"<Mitglied {self.name!r}>"


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
