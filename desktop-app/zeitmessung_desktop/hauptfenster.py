"""PySide6-Hauptfenster: Verbindungsstatus (seriell/Webapp/Sicherung),
Einstellungsdialog und Live-Liste der letzten Ereignisse - bewusst auch
ohne Netzverbindung nutzbar, damit vor Ort sichtbar bleibt, dass die
Zeitmessung läuft, selbst wenn der Sync gerade nicht durchkommt."""
from __future__ import annotations

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from . import datenbank, einstellungen as einstellungen_modul
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
        self._feld_hinzufuegen(layout, "baudrate", "Baudrate", aktuelle.baudrate)
        self._feld_hinzufuegen(layout, "webapp_url", "Webapp-URL", aktuelle.webapp_url)
        self._feld_hinzufuegen(layout, "api_key", "API-Key", aktuelle.api_key)
        self._feld_hinzufuegen(layout, "instance_name", "Instanzname", aktuelle.instance_name)
        self._feld_hinzufuegen(layout, "sync_intervall_s", "Sync-Intervall (s)",
                               aktuelle.sync_intervall_s)
        self._feld_hinzufuegen(layout, "backup_intervall_min", "Backup-Intervall (Min)",
                               aktuelle.backup_intervall_min)
        self._feld_hinzufuegen(layout, "backup_ordner", "Backup-Ordner", aktuelle.backup_ordner)

        knopfzeile = QHBoxLayout()
        speichern_knopf = QPushButton("Speichern")
        speichern_knopf.clicked.connect(self.accept)
        abbrechen_knopf = QPushButton("Abbrechen")
        abbrechen_knopf.clicked.connect(self.reject)
        knopfzeile.addWidget(speichern_knopf)
        knopfzeile.addWidget(abbrechen_knopf)
        layout.addRow(knopfzeile)

    def _feld_hinzufuegen(self, layout: QFormLayout, name: str, beschriftung: str, wert) -> None:
        if isinstance(wert, int):
            feld = QSpinBox()
            feld.setRange(1, 86400)
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

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Zeitmessung Siloplanen-Race – Desktop")
        self.resize(720, 640)

        self.einstellungen = einstellungen_modul.laden()
        self.db = datenbank.verbinden(self.einstellungen.db_pfad)

        self._seriell_worker: SeriellWorker | None = None
        self._sync_worker: SyncWorker | None = None
        self._sicherung_worker: SicherungWorker | None = None
        self._lauf_worker: LaufWorker | None = None

        self._aufbauen()
        self.ereignis_empfangen.connect(self._auf_ereignis)
        self.lauf_aktualisiert.connect(self._lauf_anzeigen)
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

        self.lauf_label = QLabel("Aktiver Lauf: –")
        layout.addWidget(self.lauf_label)

        self.lauf_tabelle = QTableWidget(0, 4)
        self.lauf_tabelle.setHorizontalHeaderLabels(
            ["Bahn", "Team", "Läuferzeiten (s, ms)", "Summe"])
        self.lauf_tabelle.horizontalHeader().setStretchLastSection(True)
        self.lauf_tabelle.setMaximumHeight(160)
        layout.addWidget(self.lauf_tabelle)

        self.ereignis_tabelle = QTableWidget(0, 3)
        self.ereignis_tabelle.setHorizontalHeaderLabels(["Bahn", "Empfangen", "Sync-Status"])
        self.ereignis_tabelle.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.ereignis_tabelle)

        self._tabelle_neu_laden()

    def _worker_starten(self) -> None:
        for worker in (self._seriell_worker, self._sync_worker, self._sicherung_worker,
                      self._lauf_worker):
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
        )
        self._lauf_worker.start()

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

    def _status_aktualisieren(self) -> None:
        ausstehend = datenbank.anzahl_ausstehend(self.db)
        self.sync_status_label.setText(f"Webapp: {ausstehend} ausstehend")

    def _tabelle_neu_laden(self) -> None:
        zeilen = datenbank.letzte_ereignisse(self.db, limit=50)
        self.ereignis_tabelle.setRowCount(len(zeilen))
        for row, zeile in enumerate(zeilen):
            self.ereignis_tabelle.setItem(row, 0, QTableWidgetItem(str(zeile["bahn"])))
            self.ereignis_tabelle.setItem(row, 1, QTableWidgetItem(zeile["empfangen_um"]))
            self.ereignis_tabelle.setItem(row, 2, QTableWidgetItem(zeile["sync_status"]))

    def closeEvent(self, event) -> None:
        for worker in (self._seriell_worker, self._sync_worker, self._sicherung_worker,
                      self._lauf_worker):
            if worker is not None:
                worker.stoppen()
        super().closeEvent(event)
