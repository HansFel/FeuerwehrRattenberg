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
    "kellner": "Kellner",
    "ausschank": "Ausschank",
    "moderator": "Moderator",
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


class Nachricht(db.Model):
    """Mitteilung eines Administrators an andere Personen der
    Organisator-Mannschaft (z.B. worüber sie nachdenken sollen)."""
    __tablename__ = "nachricht"

    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.Text, nullable=False)
    absender = db.Column(db.String(80), default="")
    # Ziel: entweder eine Rolle (an alle mit dieser Rolle), eine bestimmte
    # Person, oder beides leer = an alle.
    ziel_rolle = db.Column(db.String(40))
    ziel_benutzer_id = db.Column(db.Integer, db.ForeignKey("benutzer.id"))
    erstellt = db.Column(db.DateTime, default=_jetzt)

    ziel_benutzer = db.relationship("Benutzer", foreign_keys=[ziel_benutzer_id])
    gelesen_von = db.relationship("NachrichtGelesen", back_populates="nachricht",
                                  cascade="all, delete-orphan")

    def richtet_sich_an(self, benutzer: "Benutzer") -> bool:
        if self.ziel_benutzer_id:
            return self.ziel_benutzer_id == benutzer.id
        if self.ziel_rolle:
            return self.ziel_rolle in benutzer.rollen_namen
        return True   # kein Ziel gesetzt = an alle

    def ist_gelesen_von(self, benutzer_id: int) -> bool:
        return any(g.benutzer_id == benutzer_id for g in self.gelesen_von)

    def __repr__(self) -> str:
        return f"<Nachricht {self.id} von {self.absender!r}>"


class NachrichtGelesen(db.Model):
    __tablename__ = "nachricht_gelesen"

    id = db.Column(db.Integer, primary_key=True)
    nachricht_id = db.Column(db.Integer, db.ForeignKey("nachricht.id"),
                             nullable=False)
    benutzer_id = db.Column(db.Integer, db.ForeignKey("benutzer.id"),
                            nullable=False)
    gelesen_am = db.Column(db.DateTime, default=_jetzt)

    nachricht = db.relationship("Nachricht", back_populates="gelesen_von")

    __table_args__ = (
        db.UniqueConstraint("nachricht_id", "benutzer_id",
                            name="uq_nachricht_gelesen"),
    )


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
    motto = db.Column(db.String(200), default="")
    lieblingslied = db.Column(db.String(200), default="")
    kontakt = db.Column(db.String(120), default="")
    notiz = db.Column(db.Text, default="")
    getraenk = db.Column(db.String(20), default="")        # Pflichtgetränk (Bier/Spritzer)
    bezahlt = db.Column(db.Boolean, default=False)
    haftungsausschluss = db.Column(db.Boolean, default=False)
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
    name = db.Column(db.String(200), default="")      # Anzeigename (auto)
    vorname = db.Column(db.String(120), default="")
    nachname = db.Column(db.String(120), default="")
    spitzname = db.Column(db.String(120), default="")
    telefon = db.Column(db.String(60), default="")
    alter = db.Column("alter", db.Integer)            # Lebensalter in Jahren
    position = db.Column(db.Integer, default=1)       # 1..4
    haftungsausschluss = db.Column(db.Boolean, default=False)
    ausweis_kontrolliert = db.Column(db.Boolean, default=False)
    einverstaendniserklaerung = db.Column(db.Boolean, default=False)

    team = db.relationship("Team", back_populates="mitglieder")

    def voller_name(self) -> str:
        return f"{self.vorname} {self.nachname}".strip() or self.name

    def anzeige(self) -> str:
        """Anzeigename inkl. Spitzname, falls vorhanden."""
        voll = self.voller_name()
        if self.spitzname and voll:
            return f"{voll} „{self.spitzname}“"
        return self.spitzname or voll

    @property
    def ist_minderjaehrig(self) -> bool:
        return self.alter is not None and self.alter < 18

    def __repr__(self) -> str:
        return f"<Mitglied {self.voller_name()!r}>"


class Disziplin(db.Model):
    __tablename__ = "disziplin"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    beschreibung = db.Column(db.Text, default="")
    wertungsart = db.Column(db.String(20), default=WERTUNG_ZEIT)
    # Sekunden pro Fehlerpunkt (nur bei Zeit-Wertung relevant)
    strafsekunden_pro_fehler = db.Column(db.Float, default=0.0)
    reihenfolge = db.Column(db.Integer, default=0)         # Sortierung im Ablauf
    # Fuer automatische Startzeit-Berechnung (Zeitplan):
    dauer_pro_lauf_min = db.Column(db.Float, default=7.0)  # inkl. Puffer
    startzeit_erster_lauf = db.Column(db.String(20), default="")

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
    startnummer = db.Column(db.Integer)      # Bahn/Reihenfolge innerhalb des Laufs
    startzeit = db.Column(db.String(20), default="")  # z.B. "10:30"
    heat = db.Column(db.String(40), default="")
    # Erzielte Zeit dieses Teams in GENAU diesem Lauf/Heat (nicht die
    # Startzeit!) - Grundlage für die automatische Rangliste je Runde
    # (z.B. Vorrunde-Gesamtzeit = Summe über die 2 Vorrunden-Läufe eines
    # Teams), aus der die nächste Runde ausgelost werden kann.
    ergebnis_sekunden = db.Column(db.Float)

    team = db.relationship("Team", back_populates="startplaetze")
    disziplin = db.relationship("Disziplin", back_populates="startplaetze")


class ModeratorStatus(db.Model):
    """Vom Organisator gepflegte Live-Informationen für die Moderation.

    Es wird genau ein Datensatz mit ID 1 verwendet. Der aktuelle Lauf
    verweist bewusst auf Disziplin + Heat-Bezeichnung statt auf einzelne
    Startplätze, damit alle Bahnen gemeinsam angezeigt werden.
    """
    __tablename__ = "moderator_status"

    id = db.Column(db.Integer, primary_key=True, default=1)
    disziplin_id = db.Column(db.Integer, db.ForeignKey("disziplin.id"))
    heat = db.Column(db.String(120), default="")
    publikumsinfo = db.Column(db.Text, default="")
    sponsoren = db.Column(db.Text, default="")
    aktualisiert = db.Column(db.DateTime, default=_jetzt, onupdate=_jetzt)
    aktualisiert_von = db.Column(db.String(80), default="")

    disziplin = db.relationship("Disziplin")


KONTAKT_START = "start"
KONTAKT_ZIEL = "ziel"
# Aktuelle Hardware hat nur noch einen Kontakt pro Bahn (kein separater
# Ziel-Kontakt mehr) - jede Auslösung wird als "kontakt" gemeldet, die
# Zuordnung Start/Ziel passiert später anhand der Reihenfolge in der
# Auswertung. KONTAKT_START/KONTAKT_ZIEL bleiben für historische
# Datenbestände aus der alten 8-Kontakte-Verkabelung erhalten.
KONTAKT_KONTAKT = "kontakt"


class Zeitereignis(db.Model):
    """Ein roher Kontakt-Auslöser der ESP32-Zeitmessung (Start/Ziel je Bahn).

    Wird von der Firmware ohne Bezug zu einem Lauf gemeldet; die Zuordnung
    zu einem Wettkampf-Lauf/Team erfolgt später in der Auswertung. Dient bis
    dahin auch als Live-Protokoll, um die Hardware vor Ort zu testen.
    """
    __tablename__ = "zeitereignis"

    id = db.Column(db.Integer, primary_key=True)
    geraet_id = db.Column(db.String(80), nullable=False)
    bahn = db.Column(db.Integer, nullable=False)             # 1-4
    kontakt = db.Column(db.String(10), nullable=False)        # start/ziel
    geraet_millis = db.Column(db.BigInteger)                  # millis() des ESP32/Mega
    geraet_zeit_iso = db.Column(db.String(40), default="")    # NTP-Zeit, falls synchron
    server_empfangen = db.Column(db.DateTime, default=_jetzt)
    # Optionale, vom SENDER vergebene ID (z.B. Desktop-App/Arduino-Mega bei
    # gepufferten Ereignissen) - macht wiederholtes Senden desselben
    # Ereignisses nach einem Sync-Timeout idempotent (siehe
    # app/blueprints/zeitmessung.py:event_empfangen). Der ESP32 setzt das
    # Feld nicht. BEWUSST ohne DB-UNIQUE-Constraint (SQLite erlaubt keine
    # UNIQUE-Spalte über ALTER TABLE ADD COLUMN, siehe
    # app/__init__.py:_schema_migrieren) - Eindeutigkeit wird stattdessen in
    # event_empfangen() per Abfrage vor dem Einfügen sichergestellt.
    client_event_id = db.Column(db.String(64))

    def __repr__(self) -> str:
        return f"<Zeitereignis Bahn {self.bahn} {self.kontakt}>"


class ZeitmessungAbonnent(db.Model):
    """Andere Instanz (z.B. test1/test2/generalprobe), die sich selbst als
    Weiterleitungs-Ziel für ESP32-Zeitmessung-Ereignisse angemeldet hat
    (siehe app/blueprints/zeitmessung.py:abonnieren).

    Bewusst in der DB statt im Prozessspeicher: Gunicorn läuft mit mehreren
    Worker-PROZESSEN (nicht nur Threads), die sich KEINEN Speicher teilen -
    ein In-Memory-Dict wäre nur im jeweils zufällig treffenden Worker
    sichtbar. Meldet sich periodisch neu an (ablauf verlängert sich);
    abgelaufene Einträge werden bei der Weiterleitung einfach ignoriert,
    kein separates Aufräumen nötig.
    """
    __tablename__ = "zeitmessung_abonnent"

    id = db.Column(db.Integer, primary_key=True)
    ziel_url = db.Column(db.String(300), unique=True, nullable=False)
    api_key = db.Column(db.String(200), nullable=False)
    ablauf = db.Column(db.DateTime, nullable=False)


# ── Notfall-Zeiterfassung (inkl. automatischer Zuordnung) ────────────────────
# Der Startrichter/Organisator traegt vorab die Team-Besetzung je Bahn ein.
# Ist der Lauf ANSCHLIESSEND als "aktiv" markiert, ordnet
# app/blueprints/zeitmessung.py:_automatische_zuordnung_pruefen() eingehende
# Zeitmessung-Ereignisse (ESP32 oder Desktop-App/Arduino-Mega, egal welche
# Quelle) automatisch dieser Bahn zu und fuellt zeit_laeufer1-4 selbst aus,
# sobald 5 Ausloesungen seit der Aktivierung vorliegen. Bleibt ein Lauf ohne
# Aktivierung (oder faellt die automatische Zuordnung aus), tippt der
# Startrichter dieselben Felder stattdessen von Hand ein (z.B. abgelesen von
# der eigenstaendigen Weboberflaeche des ESP32, die auch bei App-Ausfall
# unabhaengig weiterlaeuft) - "Notfall" im Namen bezieht sich auf diesen
# Handeingabe-Fallback, nicht auf die Automatik selbst.

class NotfallLauf(db.Model):
    __tablename__ = "notfall_lauf"

    id = db.Column(db.Integer, primary_key=True)
    bezeichnung = db.Column(db.String(120), default="")
    erstellt = db.Column(db.DateTime, default=_jetzt)
    erstellt_von = db.Column(db.String(80), default="")
    aktiv = db.Column(db.Boolean, nullable=False, default=False)
    aktiviert_um = db.Column(db.DateTime)

    bahnen = db.relationship("NotfallBahn", back_populates="lauf",
                             cascade="all, delete-orphan",
                             order_by="NotfallBahn.bahn_nr")

    def __repr__(self) -> str:
        return f"<NotfallLauf {self.bezeichnung!r}>"


class NotfallBahn(db.Model):
    """Eine Bahn eines Notfall-Laufs: ein Team mit seinen (bis zu 4) Läufern
    aus Team.mitglieder (Reihenfolge = Startreihenfolge) und den manuell
    erfassten Teilzeiten je Läufer."""
    __tablename__ = "notfall_bahn"

    id = db.Column(db.Integer, primary_key=True)
    lauf_id = db.Column(db.Integer, db.ForeignKey("notfall_lauf.id"), nullable=False)
    bahn_nr = db.Column(db.Integer, nullable=False)      # 1..4
    team_id = db.Column(db.Integer, db.ForeignKey("team.id"))
    # Gesetzt, wenn dieser Lauf über "Zeitmessung freigeben" aus der
    # Startliste (Startplatz, siehe moderator.py:_laufende_teams) erzeugt
    # wurde - dient dazu, das Ergebnis nach Abschluss automatisch in
    # Startplatz.ergebnis_sekunden zurückzuschreiben (siehe
    # app/blueprints/zeitmessung.py:_automatische_zuordnung_pruefen).
    # NULL bei manuell/per Notfall-Handeingabe angelegten Läufen.
    startplatz_id = db.Column(db.Integer, db.ForeignKey("startplatz.id"))

    zeit_laeufer1 = db.Column(db.Float)   # Sekunden
    zeit_laeufer2 = db.Column(db.Float)
    zeit_laeufer3 = db.Column(db.Float)
    zeit_laeufer4 = db.Column(db.Float)

    lauf = db.relationship("NotfallLauf", back_populates="bahnen")
    team = db.relationship("Team")
    startplatz = db.relationship("Startplatz")

    @property
    def zeiten(self) -> list:
        return [self.zeit_laeufer1, self.zeit_laeufer2,
                self.zeit_laeufer3, self.zeit_laeufer4]

    @property
    def gesamtzeit(self):
        werte = [z for z in self.zeiten if z is not None]
        if len(werte) != 4:
            return None
        return sum(werte)

    def __repr__(self) -> str:
        return f"<NotfallBahn Bahn {self.bahn_nr} Lauf {self.lauf_id}>"


# ── Essen & Getränke (Gäste-Bestellsystem) ───────────────────────────────────

KATEGORIE_ESSEN = "essen"
KATEGORIE_GETRAENK = "getraenk"
KATEGORIEN = {KATEGORIE_ESSEN: "Essen", KATEGORIE_GETRAENK: "Getränk"}


class Artikel(db.Model):
    """Ein Essens- oder Getränke-Artikel der Speisekarte (vom Organisator
    gepflegt)."""
    __tablename__ = "artikel"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    kategorie = db.Column(db.String(20), default=KATEGORIE_GETRAENK)
    preis = db.Column(db.Float, nullable=False, default=0.0)
    # Punkte, die ein Wettkampfteam pro bestellter Einheit bekommt
    punkte_pro_einheit = db.Column(db.Integer, default=0)
    # Pfand pro Einheit (z.B. Mehrweg-Becher/-Gläser); 0 = kein Pfand
    pfand_pro_einheit = db.Column(db.Float, nullable=False, default=0.0)
    aktiv = db.Column(db.Boolean, default=True)
    reihenfolge = db.Column(db.Integer, default=0)

    def __repr__(self) -> str:
        return f"<Artikel {self.name!r}>"


class Bestellung(db.Model):
    """Eine (Sammel-)Bestellung an einem Tisch – von einem Gast per QR-Code
    selbst aufgegeben oder von einem Kellner erfasst."""
    __tablename__ = "bestellung"

    id = db.Column(db.Integer, primary_key=True)
    tisch_nummer = db.Column(db.Integer, nullable=False)
    erstellt = db.Column(db.DateTime, default=_jetzt)
    # Kellner-Benutzername, falls vom Personal erfasst; leer = Gast-Selbstbestellung
    erfasst_von = db.Column(db.String(80), default="")
    bezahlt = db.Column(db.Boolean, default=False)
    bezahlt_am = db.Column(db.DateTime)

    positionen = db.relationship("BestellPosition", back_populates="bestellung",
                                 cascade="all, delete-orphan")

    @property
    def gesamtbetrag(self) -> float:
        """Zu zahlender Gesamtbetrag inkl. Pfand (wird bei Rückgabe erstattet)."""
        return sum(p.zwischensumme + p.pfand_summe for p in self.positionen)

    @property
    def gesamtpunkte(self) -> int:
        return sum(p.punkte_gesamt or 0 for p in self.positionen)

    @property
    def pfand_gesamt(self) -> float:
        """Insgesamt kassiertes Pfand dieser Bestellung (unabhängig davon,
        ob schon (teilweise) zurückgegeben wurde)."""
        return sum(p.pfand_summe for p in self.positionen)

    @property
    def pfand_offen_betrag(self) -> float:
        """Noch nicht zurückerstattetes Pfand dieser Bestellung."""
        return sum(p.pfand_offen_betrag for p in self.positionen)

    def __repr__(self) -> str:
        return f"<Bestellung Tisch {self.tisch_nummer}>"


class BestellPosition(db.Model):
    """Eine Zeile einer Bestellung: ein Artikel in einer Menge, optional mit
    Team-Punkten. Preis/Punkte werden zum Bestellzeitpunkt eingefroren
    (Schnappschuss), damit spätere Änderungen an der Speisekarte bereits
    aufgegebene Bestellungen nicht rückwirkend verändern."""
    __tablename__ = "bestellposition"

    id = db.Column(db.Integer, primary_key=True)
    bestellung_id = db.Column(db.Integer, db.ForeignKey("bestellung.id"),
                              nullable=False)
    artikel_id = db.Column(db.Integer, db.ForeignKey("artikel.id"))
    artikel_name = db.Column(db.String(120), nullable=False)   # Schnappschuss
    einzelpreis = db.Column(db.Float, nullable=False, default=0.0)  # Schnappschuss
    menge = db.Column(db.Integer, nullable=False, default=1)
    team_id = db.Column(db.Integer, db.ForeignKey("team.id"))
    punkte_gesamt = db.Column(db.Integer, default=0)           # Schnappschuss * Menge
    # Pfand: Schnappschuss (bleibt bei späteren Preisänderungen stabil) und
    # wie viele Einheiten davon schon zurückgegeben wurden (Teilrückgaben
    # möglich – nicht immer kommt alles zurück).
    pfand_pro_einheit = db.Column(db.Float, nullable=False, default=0.0)
    pfand_zurueckgegeben = db.Column(db.Integer, nullable=False, default=0)

    bestellung = db.relationship("Bestellung", back_populates="positionen")
    artikel = db.relationship("Artikel")
    team = db.relationship("Team")

    @property
    def zwischensumme(self) -> float:
        return self.einzelpreis * self.menge

    @property
    def pfand_summe(self) -> float:
        return self.pfand_pro_einheit * self.menge

    @property
    def pfand_offen_anzahl(self) -> int:
        """Wie viele Einheiten noch nicht zurückgegeben wurden."""
        return max(0, self.menge - (self.pfand_zurueckgegeben or 0))

    @property
    def pfand_offen_betrag(self) -> float:
        return self.pfand_offen_anzahl * self.pfand_pro_einheit

# ── Strafenkatalog Siloplanenrace ────────────────────────────────────────────
# Fest definierter Katalog fuer die Startrichter - nicht in der DB editierbar,
# nur die vergebenen Strafen werden gespeichert. Jede Regel hat entweder eine
# feste Sekundenzahl ('sekunden') oder einen variablen Betrag
# ('sekunden_pro_einheit' mit 'einheit'-Bezeichnung, z.B. Gramm).

STRAFKATALOG = [
    {"nr": "1",   "regel": "Getränk wird weggeschüttet",                    "sekunden": 60},
    {"nr": "2.1", "regel": "Getränk rinnt am Mund vorbei – Small",          "sekunden": 5},
    {"nr": "2.2", "regel": "Getränk rinnt am Mund vorbei – Medium",         "sekunden": 10},
    {"nr": "2.3", "regel": "Getränk rinnt am Mund vorbei – Large",          "sekunden": 20},
    {"nr": "2.4", "regel": "Getränk rinnt am Mund vorbei – XL",             "sekunden": 30},
    {"nr": "3.1", "regel": "Nicht vollständig ausgetrunken – pro 1 Gramm",
     "sekunden_pro_einheit": 1, "einheit": "Gramm"},
    {"nr": "3.2", "regel": "Nicht vollständig ausgetrunken – pro 2 Gramm",
     "sekunden_pro_einheit": 2, "einheit": "Gramm"},
    {"nr": "4",   "regel": "Frühstart",                                      "sekunden": 5},
    {"nr": "5",   "regel": "Laufen auf der Bahn",                            "sekunden": 10},
    {"nr": "6",   "regel": "Behinderung des Gegners",                        "sekunden": 5},
    {"nr": "7",   "regel": "Kotzen der Laufenden",                           "sekunden": 10},
    {"nr": "7.1", "regel": "Kotzen ins Wasserbecken",                        "sekunden": 999},
    {"nr": "8",   "regel": "Austausch von Teammitgliedern (nur mit Absprache)",
     "sekunden": 0},
]

STRAFKATALOG_NACH_NR = {e["nr"]: e for e in STRAFKATALOG}


class Strafe(db.Model):
    """Eine vom Startrichter vergebene Strafe aus dem Strafenkatalog.

    Wird einem Team zugewiesen; die Sekunden fliessen in die Gesamt-Strafzeit
    des Teams ein. Der Katalog selbst ist fest im Code (STRAFKATALOG), hier
    wird nur die vergaberelevante Snapshot-Info gespeichert.
    """
    __tablename__ = "strafe"

    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey("team.id"), nullable=False)
    regel_nr = db.Column(db.String(10), nullable=False)
    regel_text = db.Column(db.String(200), default="")
    sekunden = db.Column(db.Float, nullable=False, default=0.0)
    notiz = db.Column(db.String(200), default="")
    erfasst_von = db.Column(db.String(80), default="")
    erstellt = db.Column(db.DateTime, default=_jetzt)

    team = db.relationship("Team")

    def __repr__(self):
        return f"<Strafe Team {self.team_id} {self.regel_nr} {self.sekunden}s>"
