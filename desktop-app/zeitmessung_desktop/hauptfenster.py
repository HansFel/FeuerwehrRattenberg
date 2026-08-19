"""PySide6-Hauptfenster: Verbindungsstatus (seriell/Webapp/Sicherung),
Einstellungsdialog und Live-Liste der letzten Ereignisse - bewusst auch
ohne Netzverbindung nutzbar, damit vor Ort sichtbar bleibt, dass die
Zeitmessung läuft, selbst wenn der Sync gerade nicht durchkommt."""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QPushButton, QSpinBox, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from . import datenbank, einstellungen as einstellungen_modul
from .lauf_import_worker import LaufImportWorker
from .lauf_worker import LaufWorker
from .seriell_worker import SeriellWorker
from .sicherung import SicherungWorker
from .sync_worker import SyncWorker


class EinstellungenDialog(QDialog):
    def __init__(self, aktuelle: einstellungen_modul.Einstellungen, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Einstellungen")
        self._felder: dict[str, QLineEdit | QSpinBox] = {}

        layout = QFormLayout(self)
        self._feld_hinzufuegen(layout, "com_port", "COM-Port", aktuelle.com_port)
        self._feld_hinzufuegen(layout, "baudrate", "Baudrate", aktuelle.baudrate,
                               bereich=(1200, 2_000_000))
        self._feld_hinzufuegen(layout, "webapp_url", "Webapp-URL", aktuelle.webapp_url)
        self._feld_hinzufuegen(layout, "api_key", "API-Key", aktuelle.api_key)
        self._feld_hinzufuegen(layout, "instance_name", "Instanzname", aktuelle.instance_name)
        self._feld_hinzufuegen(layout, "sync_intervall_s", "Sync-Intervall (s)",
                               aktuelle.sync_intervall_s, bereich=(1, 86400))
        self._feld_hinzufuegen(layout, "backup_intervall_min", "Backup-Intervall (Min)",
                               aktuelle.backup_intervall_min, bereich=(1, 86400))
        self._feld_hinzufuegen(layout, "backup_ordner", "Backup-Ordner", aktuelle.backup_ordner)

        knopfzeile = QHBoxLayout()
        speichern_knopf = QPushButton("Speichern")
        speichern_knopf.clicked.connect(self.accept)
        abbrechen_knopf = QPushButton("Abbrechen")
        abbrechen_knopf.clicked.connect(self.reject)
        knopfzeile.addWidget(speichern_knopf)
        knopfzeile.addWidget(abbrechen_knopf)
        layout.addRow(knopfzeile)

    def _feld_hinzufuegen(self, layout: QFormLayout, name: str, beschriftung: str, wert,
                          bereich: tuple[int, int] = (1, 86400)) -> None:
        if isinstance(wert, int):
            feld = QSpinBox()
            feld.setRange(*bereich)
            feld.setValue(wert)
        else:
            feld = QLineEdit(str(wert))
        self._felder[name] = feld
        layout.addRow(beschriftung, feld)

    def werte(self) -> dict:
        ergebnis = {}
        for name, feld in self._felder.items():
            ergebnis[name] = feld.value() if isinstance(feld, QSpinBox) else feld.text()
        return ergebnis


class Hauptfenster(QMainWindow):
    ereignis_empfangen = Signal(dict)
    lauf_aktualisiert = Signal(dict)
    lauf_status_geaendert = Signal(dict)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Zeitmessung Siloplanen-Race – Desktop")
        self.resize(760, 820)

        self.einstellungen = einstellungen_modul.laden()
        self.db = datenbank.verbinden(self.einstellungen.db_pfad)

        self._seriell_worker: SeriellWorker | None = None
        self._sync_worker: SyncWorker | None = None
        self._sicherung_worker: SicherungWorker | None = None
        self._lauf_worker: LaufWorker | None = None
        self._lauf_import_worker: LaufImportWorker | None = None

        self._aufbauen()
        self.ereignis_empfangen.connect(self._auf_ereignis)
        self.lauf_aktualisiert.connect(self._lauf_anzeigen)
        self.lauf_status_geaendert.connect(self._lauf_status_anzeigen)
        self._worker_starten()

        self._aktualisierungs_timer = QTimer(self)
        self._aktualisierungs_timer.timeout.connect(self._status_aktualisieren)
        self._aktualisierungs_timer.start(1000)

    def _aufbauen(self) -> None:
        zentral = QWidget()
        self.setCentralWidget(zentral)
        layout = QVBoxLayout(zentral)

        statuszeile = QHBoxLayout()
        self.seriell_status_label = QLabel("Seriell: –")
        self.sync_status_label = QLabel("Webapp: –")
        self.sicherung_status_label = QLabel("Sicherung: –")
        for label in (self.seriell_status_label, self.sync_status_label,
                     self.sicherung_status_label):
            statuszeile.addWidget(label)
        einstellungen_knopf = QPushButton("Einstellungen…")
        einstellungen_knopf.clicked.connect(self._einstellungen_oeffnen)
        statuszeile.addWidget(einstellungen_knopf)
        loeschen_knopf = QPushButton("Alle löschen")
        loeschen_knopf.clicked.connect(self._alle_loeschen)
        statuszeile.addWidget(loeschen_knopf)
        layout.addLayout(statuszeile)

        zustandszeile = QHBoxLayout()
        zustandszeile.addWidget(QLabel("Live-Zustand:"))
        self.zustand_labels: list[QLabel] = []
        for bahn in range(1, 5):
            label = QLabel(f"Bahn {bahn}: –")
            label.setMinimumWidth(110)
            self.zustand_labels.append(label)
            zustandszeile.addWidget(label)
        zustandszeile.addStretch()
        layout.addLayout(zustandszeile)

        lauf_kopfzeile = QHBoxLayout()
        self.lauf_label = QLabel("Aktiver Lauf: –")
        self.lauf_status_label = QLabel("Lauf-Abfrage: –")
        lauf_kopfzeile.addWidget(self.lauf_label)
        lauf_kopfzeile.addWidget(self.lauf_status_label)
        lauf_kopfzeile.addStretch()
        layout.addLayout(lauf_kopfzeile)

        self.lauf_tabelle = QTableWidget(0, 4)
        self.lauf_tabelle.setHorizontalHeaderLabels(
            ["Bahn", "Team", "Läuferzeiten (s, ms)", "Summe"])
        self.lauf_tabelle.horizontalHeader().setStretchLastSection(True)
        self.lauf_tabelle.setMaximumHeight(160)
        layout.addWidget(self.lauf_tabelle)

        # Manuelle Stopptasten (Fallback wenn Hardware-Kontakt aussetzt)
        stopp_box = QGroupBox("Manuelle Stopptaste (pro Bahn)")
        stopp_layout = QHBoxLayout(stopp_box)
        self.stopp_knoepfe: list[QPushButton] = []
        for bahn in range(1, 5):
            knopf = QPushButton(f"Bahn {bahn} STOPP")
            knopf.setMinimumHeight(60)
            knopf.setStyleSheet("font-size: 1.1rem; font-weight: bold;")
            knopf.clicked.connect(lambda checked=False, b=bahn: self._manuelles_event(b))
            self.stopp_knoepfe.append(knopf)
            stopp_layout.addWidget(knopf)
        stopp_layout.addStretch()
        layout.addWidget(stopp_box)

        manuell_box = QGroupBox("Manueller Modus (offline, ohne Webapp-Verbindung)")
        manuell_layout = QVBoxLayout(manuell_box)
        eingabe_zeile = QHBoxLayout()
        self.team_nummer_felder: list[QLineEdit] = []
        for bahn in range(1, 5):
            eingabe_zeile.addWidget(QLabel(f"Bahn {bahn} Team-Nr.:"))
            feld = QLineEdit()
            feld.setMaximumWidth(60)
            feld.setPlaceholderText("–")
            self.team_nummer_felder.append(feld)
            eingabe_zeile.addWidget(feld)
        start_knopf = QPushButton("Lokalen Lauf starten")
        start_knopf.clicked.connect(self._lokalen_lauf_starten)
        eingabe_zeile.addWidget(start_knopf)
        eingabe_zeile.addStretch()
        manuell_layout.addLayout(eingabe_zeile)

        self.lokaler_lauf_label = QLabel("Kein lokaler Lauf aktiv.")
        manuell_layout.addWidget(self.lokaler_lauf_label)

        self.lokale_lauf_tabelle = QTableWidget(0, 4)
        self.lokale_lauf_tabelle.setHorizontalHeaderLabels(
            ["Bahn", "Team-Nr.", "Läuferzeiten (s, ms)", "Sync"])
        self.lokale_lauf_tabelle.horizontalHeader().setStretchLastSection(True)
        self.lokale_lauf_tabelle.setMaximumHeight(120)
        manuell_layout.addWidget(self.lokale_lauf_tabelle)
        layout.addWidget(manuell_box)

        self.ereignis_tabelle = QTableWidget(0, 3)
        self.ereignis_tabelle.setHorizontalHeaderLabels(["Bahn", "Empfangen", "Sync-Status"])
        self.ereignis_tabelle.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.ereignis_tabelle)

        self._tabelle_neu_laden()

    def _worker_starten(self) -> None:
        for worker in (self._seriell_worker, self._sync_worker, self._sicherung_worker,
                      self._lauf_worker, self._lauf_import_worker):
            if worker is not None:
                worker.stoppen()

        self._seriell_worker = SeriellWorker(
            self.db, self.einstellungen.com_port, self.einstellungen.baudrate,
            auf_status_geaendert=lambda status: self.ereignis_empfangen.emit(status),
        )
        self._seriell_worker.start()

        self._sync_worker = SyncWorker(
            self.db, self.einstellungen.webapp_url, self.einstellungen.api_key,
            self.einstellungen.instance_name, self.einstellungen.sync_intervall_s,
        )
        self._sync_worker.start()

        self._sicherung_worker = SicherungWorker(
            self.einstellungen.db_pfad, self.einstellungen.backup_ordner,
            self.einstellungen.instance_name, self.einstellungen.backup_intervall_min,
        )
        self._sicherung_worker.start()

        self._lauf_worker = LaufWorker(
            self.einstellungen.webapp_url, self.einstellungen.api_key,
            self.einstellungen.sync_intervall_s,
            auf_lauf_aktualisiert=lambda daten: self.lauf_aktualisiert.emit(daten),
            auf_status_geaendert=lambda status: self.lauf_status_geaendert.emit(status),
        )
        self._lauf_worker.start()

        self._lauf_import_worker = LaufImportWorker(
            self.db, self.einstellungen.webapp_url, self.einstellungen.api_key,
            self.einstellungen.sync_intervall_s,
        )
        self._lauf_import_worker.start()

    def _einstellungen_oeffnen(self) -> None:
        dialog = EinstellungenDialog(self.einstellungen, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            werte = dialog.werte()
            werte["baudrate"] = int(werte["baudrate"])
            werte["sync_intervall_s"] = int(werte["sync_intervall_s"])
            werte["backup_intervall_min"] = int(werte["backup_intervall_min"])
            self.einstellungen = einstellungen_modul.Einstellungen(
                **{**self.einstellungen.als_dict(), **werte})
            einstellungen_modul.speichern(self.einstellungen)
            self._worker_starten()

    def _auf_ereignis(self, status: dict) -> None:
        if "verbunden" in status:
            self.seriell_status_label.setText(
                f"Seriell: {'verbunden' if status['verbunden'] else 'getrennt'}")
        if status.get("neues_ereignis"):
            self._tabelle_neu_laden()
        if status.get("zustaende") is not None:
            self._zustaende_anzeigen(status["zustaende"])

    def _zustaende_anzeigen(self, zustaende: list[int]) -> None:
        for bahn0, (label, zustand) in enumerate(zip(self.zustand_labels, zustaende)):
            bahn = bahn0 + 1
            if zustand:
                label.setText(f"Bahn {bahn}: AUSGELÖST")
                label.setStyleSheet("color: #b30000; font-weight: bold;")
            else:
                label.setText(f"Bahn {bahn}: bereit")
                label.setStyleSheet("color: #1a7a1a;")

    def _lauf_anzeigen(self, daten: dict) -> None:
        if not daten.get("aktiv"):
            self.lauf_label.setText("Aktiver Lauf: –")
            self.lauf_tabelle.setRowCount(0)
            return
        self.lauf_label.setText(f"Aktiver Lauf: {daten.get('bezeichnung') or daten['lauf_id']}")
        bahnen = daten.get("bahnen", [])
        self.lauf_tabelle.setRowCount(len(bahnen))
        for row, bahn in enumerate(bahnen):
            zeiten_text = "  ".join(
                f"L{l['nummer']}: {l['zeit']:.3f}" if l["zeit"] is not None
                else f"L{l['nummer']}: –"
                for l in bahn.get("laeufer", [])
            )
            summe = bahn.get("gesamtzeit")
            summe_text = f"{summe:.3f} s" if summe is not None else "–"
            self.lauf_tabelle.setItem(row, 0, QTableWidgetItem(str(bahn["bahn_nr"])))
            self.lauf_tabelle.setItem(row, 1, QTableWidgetItem(bahn.get("team_name") or "–"))
            self.lauf_tabelle.setItem(row, 2, QTableWidgetItem(zeiten_text or "–"))
            self.lauf_tabelle.setItem(row, 3, QTableWidgetItem(summe_text))

    def _lauf_status_anzeigen(self, status: dict) -> None:
        jetzt = datetime.now().strftime("%H:%M:%S")
        if status.get("erfolgreich"):
            self.lauf_status_label.setText(f"Lauf-Abfrage: OK ({jetzt})")
            self.lauf_status_label.setStyleSheet("")
        else:
            grund = status.get("fehler") or f"HTTP {status.get('status_code')}"
            self.lauf_status_label.setText(f"Lauf-Abfrage: Fehler ({jetzt}) – {grund}")
            self.lauf_status_label.setStyleSheet("color: #b30000;")

    def _alle_loeschen(self) -> None:
        """Löscht NUR den lokalen Puffer (z.B. nach einem Testlauf) - bereits
        synchronisierte Ereignisse in der Webapp-Datenbank bleiben davon
        unberührt, dafür den Knopf unter /zeitmessung/ in der Webapp
        verwenden."""
        antwort = QMessageBox.question(
            self, "Alle löschen",
            "Wirklich ALLE lokal gepufferten Ereignisse löschen?\n"
            "Betrifft nur diesen Rechner, nicht die Webapp-Datenbank.",
        )
        if antwort != QMessageBox.StandardButton.Yes:
            return
        anzahl = datenbank.alle_loeschen(self.db)
        self._tabelle_neu_laden()
        QMessageBox.information(self, "Alle löschen", f"{anzahl} Ereignis(se) gelöscht.")

    def _lokalen_lauf_starten(self) -> None:
        """Startet einen Lauf OHNE Webapp-Verbindung: Team-Nummern werden
        eingetippt statt aus der Webapp geladen, die Zuordnung passiert
        lokal (siehe lokale_zuordnung.py). Wird automatisch in die Webapp
        nachgereicht, sobald sie wieder erreichbar ist (siehe
        lauf_import_worker.py)."""
        team_nummern = {
            bahn: feld.text().strip()
            for bahn, feld in enumerate(self.team_nummer_felder, start=1)
            if feld.text().strip()
        }
        if not team_nummern:
            QMessageBox.warning(self, "Lokalen Lauf starten",
                                "Bitte mindestens eine Team-Nummer eintragen.")
            return
        aktiviert_um = datetime.now(timezone.utc).isoformat()
        datenbank.lokalen_lauf_starten(
            self.db, bezeichnung=f"Offline {aktiviert_um}",
            team_nummern=team_nummern, aktiviert_um=aktiviert_um,
        )
        for feld in self.team_nummer_felder:
            feld.clear()
        self._lokalen_lauf_anzeigen()

    def _lokalen_lauf_anzeigen(self) -> None:
        lauf = datenbank.aktiver_lokaler_lauf(self.db)
        if lauf is None:
            self.lokaler_lauf_label.setText("Kein lokaler Lauf aktiv.")
            self.lokale_lauf_tabelle.setRowCount(0)
            return
        self.lokaler_lauf_label.setText(
            f"Lokaler Lauf seit {lauf['aktiviert_um']} "
            f"({'noch nicht' if lauf['sync_status'] == 'ausstehend' else 'bereits'} "
            f"an Webapp gemeldet)")
        bahnen = datenbank.lokale_bahnen(self.db, lauf["id"])
        self.lokale_lauf_tabelle.setRowCount(len(bahnen))
        for row, bahn in enumerate(bahnen):
            zeiten_text = "  ".join(
                f"L{i}: {bahn[f'zeit_laeufer{i}']:.3f}" if bahn[f"zeit_laeufer{i}"] is not None
                else f"L{i}: –"
                for i in range(1, 5)
            )
            self.lokale_lauf_tabelle.setItem(row, 0, QTableWidgetItem(str(bahn["bahn_nr"])))
            self.lokale_lauf_tabelle.setItem(row, 1, QTableWidgetItem(bahn["team_nummer"]))
            self.lokale_lauf_tabelle.setItem(row, 2, QTableWidgetItem(zeiten_text))
            self.lokale_lauf_tabelle.setItem(row, 3, QTableWidgetItem(lauf["sync_status"]))

    def _status_aktualisieren(self) -> None:
        ausstehend = datenbank.anzahl_ausstehend(self.db)
        self.sync_status_label.setText(f"Webapp: {ausstehend} ausstehend")
        self._lokalen_lauf_anzeigen()

    def _tabelle_neu_laden(self) -> None:
        zeilen = datenbank.letzte_ereignisse(self.db, limit=50)
        self.ereignis_tabelle.setRowCount(len(zeilen))
        for row, zeile in enumerate(zeilen):
            self.ereignis_tabelle.setItem(row, 0, QTableWidgetItem(str(zeile["bahn"])))
            self.ereignis_tabelle.setItem(row, 1, QTableWidgetItem(zeile["empfangen_um"]))
            self.ereignis_tabelle.setItem(row, 2, QTableWidgetItem(zeile["sync_status"]))

    def _manuelles_event(self, bahn: int) -> None:
        """Erzeugt ein manuelles Kontaktereignis fuer die angegebene Bahn -
        aequivalent zu einem vom Arduino empfangenen EVENT, nur per Button-
        Klick statt Hardware-Kontakt. Geht durch dieselbe Pipeline:
        lokale SQLite -> lokale Zuordnung -> Sync zur Webapp."""
        client_event_id = uuid.uuid4().hex
        empfangen_um = datetime.now(timezone.utc).isoformat()
        geraet_millis = int(time.time() * 1000) % 1_000_000
        datenbank.ereignis_hinzufuegen(
            self.db, bahn=bahn, geraet_millis=geraet_millis,
            empfangen_um=empfangen_um, client_event_id=client_event_id,
        )
        from .lokale_zuordnung import zuordnung_pruefen
        zuordnung_pruefen(self.db, bahn)
        self._tabelle_neu_laden()
        self._auf_ereignis({"neues_ereignis": {"bahn": bahn},
                           "zustaende": [0, 0, 0, 0]})

    def closeEvent(self, event) -> None:
        for worker in (self._seriell_worker, self._sync_worker, self._sicherung_worker,
                      self._lauf_worker, self._lauf_import_worker):
            if worker is not None:
                worker.stoppen()
        super().closeEvent(event)